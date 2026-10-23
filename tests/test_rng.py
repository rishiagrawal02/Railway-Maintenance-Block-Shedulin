"""Tests for seeded deterministic random number generator streams."""

from rbp.rng import make_rng


def test_rng_determinism():
    """T0.3-05: Same seed and stream produce identical sequence."""
    rng1 = make_rng(7, "tasks")
    rng2 = make_rng(7, "tasks")

    seq1 = [rng1.random() for _ in range(5)]
    seq2 = [rng2.random() for _ in range(5)]

    assert seq1 == seq2


def test_rng_stream_isolation():
    """T0.3-06: Same seed but different stream names produce distinct sequences."""
    rng_tasks = make_rng(7, "tasks")
    rng_trains = make_rng(7, "trains")

    seq_tasks = [rng_tasks.random() for _ in range(5)]
    seq_trains = [rng_trains.random() for _ in range(5)]

    assert seq_tasks != seq_trains
