"""Deterministic seeded RNG generation with stream isolation."""

import hashlib
import random


def make_rng(seed: int, stream: str) -> random.Random:
    """Create a deterministic random.Random instance for a specific seed and stream.

    Uses SHA-256 to hash the seed and stream string into a 64-bit integer seed,
    guaranteeing stream isolation and cross-platform determinism.
    """
    token = f"{seed}:{stream}".encode("utf-8")
    seed_int = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return random.Random(seed_int)
