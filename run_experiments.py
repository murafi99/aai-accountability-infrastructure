import json
import random
import time
import sys
import os
import copy
import statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aai_core import (
    ThresholdSigningService, Ledger, generate_synthetic_transaction,
    merkle_root, merkle_proof, verify_merkle_proof, canonicalize, sha256_hex
)

random.seed(42)

RESULTS = {}

# ---------------------------------------------------------------------------
# Experiment 1: Correctness — build a ledger of N synthetic transactions,
# verify the chain validates, then inject tampering and confirm detection.
# ---------------------------------------------------------------------------

def experiment_correctness_and_tamper_detection(n=500):
    signer = ThresholdSigningService(n=5, k=3, role_names=[
        "provider_ops", "independent_auditor", "regulator", "judicial_gateway", "escrow"
    ])
    quorum = ["provider_ops", "independent_auditor", "regulator"]  # 3-of-5
    ledger = Ledger(signer, quorum)

    for i in range(n):
        ledger.append(generate_synthetic_transaction(i))

    valid_before, _ = ledger.verify_chain()

    # Attempt to sign with an insufficient quorum (2-of-5) -- should be refused
    insufficient_quorum_refused = False
    try:
        bad_ledger = Ledger(signer, ["provider_ops", "independent_auditor"])  # only 2 shares
        bad_ledger.append(generate_synthetic_transaction(9999))
    except RuntimeError:
        insufficient_quorum_refused = True

    # Tamper with a mid-chain record's content directly (simulating an insider
    # attempting retroactive alteration) without re-signing
    tampered_ledger = copy.deepcopy(ledger)
    victim_index = n // 2
    tampered_ledger.records[victim_index].policy_set_id = "policy-FORGED"
    valid_after_naive_tamper, first_bad_idx_naive = tampered_ledger.verify_chain()

    # More sophisticated attack: tamper AND recompute record_hash, but attacker
    # does NOT have quorum to re-sign (no valid signature possible)
    tampered_ledger2 = copy.deepcopy(ledger)
    tampered_ledger2.records[victim_index].policy_set_id = "policy-FORGED"
    recomputed_hash = sha256_hex(canonicalize(tampered_ledger2.records[victim_index].content_for_hash()))
    tampered_ledger2.records[victim_index].record_hash = recomputed_hash
    # attacker leaves the OLD signature in place (cannot produce a new valid one
    # without k=3 quorum cooperation, which we assume the attacker lacks)
    valid_after_hash_fixed_tamper, first_bad_idx_fixed = tampered_ledger2.verify_chain()

    return {
        "n_records": n,
        "chain_valid_before_tamper": valid_before,
        "insufficient_quorum_signing_refused": insufficient_quorum_refused,
        "chain_valid_after_naive_tamper": valid_after_naive_tamper,
        "naive_tamper_detected_at_index": first_bad_idx_naive,
        "chain_valid_after_hash_recomputed_tamper_without_quorum": valid_after_hash_fixed_tamper,
        "hash_fixed_tamper_detected_at_index": first_bad_idx_fixed,
    }


# ---------------------------------------------------------------------------
# Experiment 2: Latency & storage overhead vs. transaction volume (REAL
# measurements on this machine, on synthetic data -- not fabricated numbers).
# ---------------------------------------------------------------------------

def experiment_overhead_scaling(volumes=(100, 500, 1000, 2000, 5000)):
    rows = []
    for n in volumes:
        signer = ThresholdSigningService(n=5, k=3, role_names=[
            "provider_ops", "independent_auditor", "regulator", "judicial_gateway", "escrow"
        ])
        quorum = ["provider_ops", "independent_auditor", "regulator"]
        ledger = Ledger(signer, quorum)

        per_record_latencies_ms = []
        t_start_total = time.perf_counter()
        for i in range(n):
            draft = generate_synthetic_transaction(i)
            t0 = time.perf_counter()
            ledger.append(draft)
            t1 = time.perf_counter()
            per_record_latencies_ms.append((t1 - t0) * 1000.0)
        t_end_total = time.perf_counter()

        total_time_s = t_end_total - t_start_total
        storage_bytes = sum(
            len(canonicalize(r.content_for_hash())) + len(r.signature) + len(r.record_id)
            for r in ledger.records
        )

        rows.append({
            "n": n,
            "total_time_s": total_time_s,
            "throughput_records_per_sec": n / total_time_s,
            "mean_latency_ms": statistics.mean(per_record_latencies_ms),
            "p50_latency_ms": statistics.median(per_record_latencies_ms),
            "p99_latency_ms": sorted(per_record_latencies_ms)[int(0.99 * n) - 1],
            "total_storage_bytes": storage_bytes,
            "bytes_per_record": storage_bytes / n,
        })
    return rows


# ---------------------------------------------------------------------------
# Experiment 3: Selective disclosure via Merkle proof over a batch of records
# (Property 4 / RQ3) -- prove one record's membership without revealing others.
# ---------------------------------------------------------------------------

def experiment_selective_disclosure(batch_size=256):
    signer = ThresholdSigningService(n=5, k=3)
    quorum = ["role_1", "role_2", "role_3"]
    ledger = Ledger(signer, quorum)
    for i in range(batch_size):
        ledger.append(generate_synthetic_transaction(i))

    leaves = [r.record_hash for r in ledger.records]
    root = merkle_root(leaves)

    target_index = batch_size // 3
    proof = merkle_proof(leaves, target_index)
    proof_valid = verify_merkle_proof(leaves[target_index], proof, root)

    # negative control: proof should NOT validate against a wrong leaf
    wrong_leaf_check = verify_merkle_proof(leaves[target_index + 1], proof, root)

    import math
    return {
        "batch_size": batch_size,
        "merkle_root": root,
        "proof_size_entries": len(proof),
        "theoretical_log2_n": math.log2(batch_size),
        "proof_valid_for_correct_leaf": proof_valid,
        "proof_incorrectly_validates_wrong_leaf": wrong_leaf_check,  # should be False
    }


if __name__ == "__main__":
    RESULTS["correctness_and_tamper_detection"] = experiment_correctness_and_tamper_detection(n=500)
    RESULTS["overhead_scaling"] = experiment_overhead_scaling()
    RESULTS["selective_disclosure"] = experiment_selective_disclosure()

    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "results.json"), "w") as f:
        json.dump(RESULTS, f, indent=2)

    print(json.dumps(RESULTS, indent=2))
