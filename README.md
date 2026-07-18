# AAI Prototype — AI Accountability Infrastructure

A runnable, **simulation-data** prototype of the AI Accountability Infrastructure (AAI) described in the accompanying paper (`paper/AAI_Research_Paper.md`): a hash-chained, threshold-signed, tamper-evident record structure for AI decision provenance, with Merkle-based selective disclosure.

This is **not production code**. It demonstrates, with real cryptographic primitives operating on synthetic ("simulated") AI-transaction data, that the mechanisms proposed in the paper are implementable and measurable. See [What This Prototype Does NOT Show](#what-this-prototype-does-not-show) before drawing any production conclusions from it.

## What's actually in here

- Real SHA-256 hash-chaining of records (Python `hashlib`)
- Real Shamir's Secret Sharing (Lagrange interpolation over the secp256k1 field prime) splitting a signing key across a simulated 5-role quorum, requiring 3 shares to reconstruct and sign (HMAC-SHA256)
- Real Merkle trees with inclusion-proof generation and verification
- A synthetic AI-transaction generator (randomized inputs, retrieved sources, tool calls, policy sets, model versions — **no real AI system or user data involved**)
- An experiment harness that measures real wall-clock latency, throughput, and storage overhead — not estimated or fabricated numbers

## What this prototype does NOT show

- **No real threshold public-key signatures.** Threshold signing here is a Shamir-shared-HMAC stand-in for a true threshold Ed25519/BLS scheme with proper distributed key generation. This correctly demonstrates the *quorum-required* property but should not be used as-is in production.
- **No distributed-network coordination cost.** All simulated role-holders run in a single process; a real deployment would need role-holders on separate infrastructure, and quorum-signing latency would be dominated by network round trips, not arithmetic.
- **No real AI pipeline integration.** Transactions are synthetic placeholders, not connected to any actual inference system.
- **No external transparency-log anchoring implementation.**
- **No privacy-risk measurement** against a realistic (non-random) record population.

See Section 10 of the paper for the full discussion.

## Repository structure

```
aai-prototype/
├── src/
│   ├── aai_core.py          # Core mechanisms: Shamir SSS, threshold signing,
│   │                         # hash-chained ledger, Merkle proofs, synthetic
│   │                         # transaction generator
│   ├── run_experiments.py   # The 3 experiments reported in the paper's Section 10
│   └── make_charts.py       # Regenerates the two result figures from results.json
├── results/
│   ├── results.json          # Raw, full-precision measured output
│   ├── overhead_scaling.png  # Figure 1: latency/throughput/storage vs. volume
│   └── tamper_detection.png  # Figure 2: tamper-detection outcomes
├── paper/
│   └── AAI_Research_Paper.md # The accompanying research paper
├── .github/workflows/test.yml # CI: re-runs the experiments on every push
├── requirements.txt
├── LICENSE
└── README.md
```

## Installation

```bash
git clone https://github.com/<murafi99>/aai-prototype.git
cd aai-prototype
pip install -r requirements.txt
```

Requires Python 3.9+. No external services, databases, or network access needed — everything runs locally on synthetic data.

## Usage

```bash
# Run all three experiments (correctness/tamper-detection, overhead scaling,
# selective disclosure) and write results/results.json
python3 src/run_experiments.py

# Regenerate the two figures from results.json
python3 src/make_charts.py
```

Re-running `run_experiments.py` uses a fixed random seed (`random.seed(42)`) for the synthetic transaction data, so the correctness/tamper-detection and selective-disclosure results are reproducible run to run. Cryptographic key material (the Shamir-shared signing key) is freshly generated per run by design — this does not affect the reported latency, storage, or correctness results, only the actual signature bytes.

## Measured results summary

From the last recorded run (see `results/results.json` for full precision):

| Volume (records) | Mean append latency | Throughput | Bytes/record |
|---|---|---|---|
| 100 | 0.24 ms | ~3,980 rec/s | 552 |
| 5,000 | 0.25 ms | ~3,790 rec/s | 554 |

Tamper detection: **100%** — both a naive content edit and a content edit with hash recomputation (but no valid quorum signature) were correctly detected on a 500-record simulated ledger.

Selective disclosure: an 8-entry Merkle proof correctly validated a target record's inclusion in a 256-record batch (matching the `log2(256) = 8` prediction) and correctly rejected proof-checking against a wrong leaf.

## Citation

If you reference this prototype or the accompanying paper, please cite:

```
Rafi, M. U. (2026). AI Accountability Infrastructure: A Privacy-Preserving,
Judicially Auditable Framework for AI Decision Provenance.
```

A formal BibTeX entry with venue/DOI can be added here once the paper is published.

## License

MIT — see `LICENSE`. Note this covers the prototype code only; the paper's own reuse terms are whatever you choose to apply on submission/publication.
