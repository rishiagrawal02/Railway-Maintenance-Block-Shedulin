"""Tests verifying generated instances match pinned golden hashes (Milestone 3.3)."""

import hashlib
import json
from pathlib import Path

from rbp.generation.extended import generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.io.serialize import instance_to_dict

GOLDEN_PATH = Path(__file__).parent / "data" / "golden_hashes.json"


def _hash_instance(inst) -> str:
    data = instance_to_dict(inst)
    json_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


# ---------------------------------------------------------------------------
# T3.3-05: Golden hashes match stored
# ---------------------------------------------------------------------------


def test_golden_hashes_match():
    """T3.3-05: Generated instances for fixed seeds match stored SHA-256 golden hashes."""
    assert GOLDEN_PATH.exists(), f"Missing golden hash file: {GOLDEN_PATH}"
    golden_hashes = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    instances = {
        "simplified_n25_s1": generate_simplified(n=25, seed=1),
        "simplified_n50_s42": generate_simplified(n=50, seed=42),
        "extended_n25_s1": generate_extended(n=25, seed=1),
        "extended_n50_s42": generate_extended(n=50, seed=42),
    }

    for name, inst in instances.items():
        computed_hash = _hash_instance(inst)
        expected_hash = golden_hashes[name]
        assert computed_hash == expected_hash, (
            f"Hash mismatch for {name}:\n  computed: {computed_hash}\n  expected: {expected_hash}"
        )


# ---------------------------------------------------------------------------
# T3.3-06: Golden failure detection (negative test)
# ---------------------------------------------------------------------------


def test_golden_failure_detection():
    """T3.3-06: Any change in generator output produces a hash mismatch."""
    golden_hashes = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    # Alter seed
    tampered_inst = generate_simplified(n=25, seed=999)
    tampered_hash = _hash_instance(tampered_inst)
    assert tampered_hash != golden_hashes["simplified_n25_s1"]
