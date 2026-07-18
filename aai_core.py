"""
AAI Prototype Core
===================
A runnable, simulation-data prototype of the AI Accountability Infrastructure (AAI)
described in the accompanying paper. This is NOT production code. It demonstrates,
with real cryptographic primitives operating on synthetic ("simulated") AI-transaction
data, that the mechanisms proposed (hash-chained ledger, threshold-style signing,
tamper detection, Merkle-based selective disclosure) are implementable and measurable.

Design choices made explicit for honesty:
- Threshold signing is implemented via Shamir's Secret Sharing (SSS) over a symmetric
  HMAC signing key, reconstructed only when k-of-n shares cooperate, then used to
  compute a real HMAC-SHA256 signature. This demonstrates the *access-control and
  quorum* property (no single share signs alone) using a simple, auditable
  construction. It is NOT a threshold Ed25519/BLS scheme (which would require a
  more complex distributed-key-generation protocol out of scope for a prototype) -
  we say so explicitly rather than overclaim.
- All "AI transactions" (inputs, retrieved context, tool calls, policy, output) are
  SYNTHETIC / SIMULATED. No real user data, and no real production AI pipeline, is
  involved. This lets us measure real latency/storage/tamper-detection behavior of
  the accountability mechanism itself, isolated from any specific AI system.
"""

import hashlib
import hmac
import json
import os
import random
import secrets
import string
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# ---------------------------------------------------------------------------
# 1. Shamir's Secret Sharing (finite field arithmetic over a large prime)
# ---------------------------------------------------------------------------

# NOTE: an earlier version of this file used 2**261 - 1 as "the prime" -- that
# value is NOT actually prime (261 = 9*29 is composite, so 2**261-1 is composite
# too), which silently broke Lagrange interpolation. Fixed by using a real,
# well-known prime (the secp256k1 field prime) that is comfortably larger than
# any 32-byte secret, and independently verified prime via sympy.isprime().
_PRIME = 2 ** 256 - 2 ** 32 - 977  # secp256k1 field prime (verified prime)


def _eval_poly(coeffs, x, prime=_PRIME):
    result = 0
    for c in reversed(coeffs):
        result = (result * x + c) % prime
    return result


def shamir_split(secret_int: int, n: int, k: int, prime=_PRIME):
    """Split secret_int into n shares, any k of which reconstruct it."""
    assert 0 <= secret_int < prime
    coeffs = [secret_int] + [secrets.randbelow(prime) for _ in range(k - 1)]
    shares = [(x, _eval_poly(coeffs, x, prime)) for x in range(1, n + 1)]
    return shares


def _mod_inverse(a, prime=_PRIME):
    return pow(a, prime - 2, prime)


def shamir_combine(shares, prime=_PRIME):
    """Lagrange-interpolate at x=0 to recover the secret from >=k shares."""
    secret = 0
    for i, (xi, yi) in enumerate(shares):
        num, den = 1, 1
        for j, (xj, _) in enumerate(shares):
            if i == j:
                continue
            num = (num * (-xj)) % prime
            den = (den * (xi - xj)) % prime
        term = (yi * num * _mod_inverse(den, prime)) % prime
        secret = (secret + term) % prime
    return secret % prime


# ---------------------------------------------------------------------------
# 2. Threshold signing service (simulated k-of-n quorum)
# ---------------------------------------------------------------------------

class ThresholdSigningService:
    """
    Simulates Section 4.4 / 5.1's threshold signing: a symmetric key is split via
    Shamir SSS across n role-holders (e.g., provider-ops, independent auditor,
    regulator, judicial-gateway, escrow). Signing a record hash requires
    reconstructing the key from >=k shares (i.e., quorum cooperation) and computing
    an HMAC-SHA256 signature. No single share holder can sign alone.
    """

    def __init__(self, n=5, k=3, role_names=None):
        self.n = n
        self.k = k
        # Reduce mod the field prime so the secret is guaranteed representable
        # both as a field element and as exactly 32 bytes (prime < 2**256).
        secret_bytes = secrets.token_bytes(32)
        self._secret_int = int.from_bytes(secret_bytes, "big") % _PRIME
        secret_bytes = self._secret_int.to_bytes(32, "big")
        raw_shares = shamir_split(self._secret_int, n, k)
        self.role_names = role_names or [f"role_{i+1}" for i in range(n)]
        self.shares = {self.role_names[i]: raw_shares[i] for i in range(n)}
        # public verification: HMAC key derived deterministically from secret,
        # "public key" here is simulated as a commitment (hash) other parties can
        # check a signature against, without needing the secret itself.
        self._key_bytes = secret_bytes
        self.key_commitment = hashlib.sha256(secret_bytes).hexdigest()

    def sign(self, message: bytes, quorum_roles: List[str]) -> Optional[str]:
        if len(quorum_roles) < self.k:
            return None  # quorum not met; signing refused
        chosen = [self.shares[r] for r in quorum_roles[: self.k]]
        recovered_int = shamir_combine(chosen)
        recovered_bytes = recovered_int.to_bytes(32, "big")
        # sanity: in a real deployment the key holder would never see this
        # reconstruction happen outside a controlled quorum ceremony
        sig = hmac.new(recovered_bytes, message, hashlib.sha256).hexdigest()
        return sig

    def verify(self, message: bytes, signature: str) -> bool:
        expected = hmac.new(self._key_bytes, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# 3. Accountability Record + Hash-Chained Ledger
# ---------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class AccountabilityRecord:
    record_id: str
    timestamp: float
    model_version_id: str
    policy_set_id: str
    input_ref: str          # hash reference, not raw content (data minimization)
    output_ref: str
    retrieval_source_ids: List[str]
    tool_ids: List[str]
    safety_flags: List[str]
    prev_record_hash: str
    record_hash: str = ""
    signature: str = ""
    signer_quorum: List[str] = field(default_factory=list)

    def content_for_hash(self) -> dict:
        d = asdict(self)
        d.pop("record_hash")
        d.pop("signature")
        d.pop("signer_quorum")
        return d


class Ledger:
    """Append-only hash-chained ledger of AccountabilityRecords (Definitions 1-2)."""

    GENESIS_HASH = "0" * 64

    def __init__(self, signer: ThresholdSigningService, quorum_roles: List[str]):
        self.records: List[AccountabilityRecord] = []
        self.signer = signer
        self.quorum_roles = quorum_roles

    def append(self, draft: AccountabilityRecord) -> AccountabilityRecord:
        prev_hash = self.records[-1].record_hash if self.records else self.GENESIS_HASH
        draft.prev_record_hash = prev_hash
        content_hash = sha256_hex(canonicalize(draft.content_for_hash()))
        draft.record_hash = content_hash
        sig = self.signer.sign(content_hash.encode(), self.quorum_roles)
        if sig is None:
            raise RuntimeError("Quorum not met: record cannot be signed/appended")
        draft.signature = sig
        draft.signer_quorum = list(self.quorum_roles)
        self.records.append(draft)
        return draft

    def verify_chain(self):
        """Algorithm 2: VerifyChain. Returns (is_valid, first_invalid_index)."""
        prev_hash = self.GENESIS_HASH
        for i, rec in enumerate(self.records):
            if rec.prev_record_hash != prev_hash:
                return False, i
            recomputed = sha256_hex(canonicalize(rec.content_for_hash()))
            if recomputed != rec.record_hash:
                return False, i
            if not self.signer.verify(rec.record_hash.encode(), rec.signature):
                return False, i
            prev_hash = rec.record_hash
        return True, None


# ---------------------------------------------------------------------------
# 4. Merkle tree for selective disclosure (Property 4)
# ---------------------------------------------------------------------------

def merkle_root(leaves: List[str]) -> str:
    level = [sha256_hex(l.encode()) for l in leaves]
    if not level:
        return sha256_hex(b"")
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [sha256_hex((level[i] + level[i + 1]).encode()) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(leaves: List[str], index: int):
    level = [sha256_hex(l.encode()) for l in leaves]
    proof = []
    idx = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        pair_idx = idx + 1 if idx % 2 == 0 else idx - 1
        proof.append((level[pair_idx], idx % 2 == 0))  # (sibling_hash, is_left)
        level = [sha256_hex((level[i] + level[i + 1]).encode()) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_merkle_proof(leaf: str, proof, root: str) -> bool:
    h = sha256_hex(leaf.encode())
    for sibling, is_left in proof:
        h = sha256_hex((h + sibling).encode()) if is_left else sha256_hex((sibling + h).encode())
    return h == root


# ---------------------------------------------------------------------------
# 5. Synthetic ("simulated") AI-transaction generator
# ---------------------------------------------------------------------------

MODEL_VERSIONS = ["model-x-v4.1", "model-x-v4.2", "model-x-v4.3"]
POLICY_SETS = ["policy-2026-05-a", "policy-2026-06-a", "policy-2026-07-a"]
RETRIEVAL_SOURCES = ["kb-legal-2026", "kb-medical-2026", "kb-finance-2026", "kb-general-2026"]
TOOLS = ["calculator", "web_search", "code_exec", "unit_converter"]
SAFETY_FLAGS_POOL = ["none", "none", "none", "pii_detected", "policy_review"]


def _rand_id(n=12):
    return "".join(random.choices(string.hexdigits.lower()[:16], k=n))


def generate_synthetic_transaction(i: int) -> AccountabilityRecord:
    input_content = f"synthetic_user_input_{i}_{_rand_id(8)}"
    output_content = f"synthetic_model_output_{i}_{_rand_id(8)}"
    return AccountabilityRecord(
        record_id=f"aar_{_rand_id()}",
        timestamp=time.time(),
        model_version_id=random.choice(MODEL_VERSIONS),
        policy_set_id=random.choice(POLICY_SETS),
        input_ref=sha256_hex(input_content.encode()),
        output_ref=sha256_hex(output_content.encode()),
        retrieval_source_ids=random.sample(RETRIEVAL_SOURCES, k=random.randint(0, 2)),
        tool_ids=random.sample(TOOLS, k=random.randint(0, 2)),
        safety_flags=[random.choice(SAFETY_FLAGS_POOL)],
        prev_record_hash="",  # filled in by Ledger.append
    )
