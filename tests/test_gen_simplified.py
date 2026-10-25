"""Tests for simplified instance generator (Milestone 3.1)."""

import time

import pytest

from rbp.generation.simplified import generate_simplified
from rbp.io.input_checks import validate_instance
from rbp.io.serialize import instance_to_dict
from rbp.models import Corridor, Instance, Interval, Resource, Task, is_simplified

# ---------------------------------------------------------------------------
# T3.1-01: Determinism
# ---------------------------------------------------------------------------


def test_determinism():
    """T3.1-01: Generating twice with seed 5 produces identical dicts/JSON."""
    inst1 = generate_simplified(n=50, seed=5)
    inst2 = generate_simplified(n=50, seed=5)
    assert instance_to_dict(inst1) == instance_to_dict(inst2)


# ---------------------------------------------------------------------------
# T3.1-02: Different seeds produce different task sets
# ---------------------------------------------------------------------------


def test_different_seeds_differ():
    """T3.1-02: Seeds 5 and 6 produce different task sets."""
    inst1 = generate_simplified(n=20, seed=5)
    inst2 = generate_simplified(n=20, seed=6)
    tasks1 = [(t.window_start, t.duration) for t in inst1.tasks]
    tasks2 = [(t.window_start, t.duration) for t in inst2.tasks]
    assert tasks1 != tasks2


# ---------------------------------------------------------------------------
# T3.1-03: Valid and simplified across 50 seeds
# ---------------------------------------------------------------------------


def test_valid_and_simplified_50_seeds():
    """T3.1-03: 50 different seeds all pass validate_instance and is_simplified."""
    for seed in range(1, 51):
        inst = generate_simplified(n=25, seed=seed)
        assert validate_instance(inst) == []
        assert is_simplified(inst) is True


# ---------------------------------------------------------------------------
# T3.1-04: Window equals duration for all tasks
# ---------------------------------------------------------------------------


def test_window_equals_duration():
    """T3.1-04: Fixed-interval condition holds for all tasks."""
    inst = generate_simplified(n=100, seed=42)
    for t in inst.tasks:
        assert (t.window_end - t.window_start) == t.duration


# ---------------------------------------------------------------------------
# T3.1-05: Duration bounds
# ---------------------------------------------------------------------------


def test_duration_bounds():
    """T3.1-05: Task durations strictly lie within [dmin, dmax]."""
    dmin, dmax = 15, 75
    inst = generate_simplified(n=80, seed=123, dmin=dmin, dmax=dmax)
    for t in inst.tasks:
        assert dmin <= t.duration <= dmax


# ---------------------------------------------------------------------------
# T3.1-06: Edge cases n=0 and n=1
# ---------------------------------------------------------------------------


def test_edge_cases_n0_and_n1():
    """T3.1-06: n=0 and n=1 generate valid, simplified instances."""
    inst0 = generate_simplified(n=0, seed=1)
    assert len(inst0.tasks) == 0
    assert validate_instance(inst0) == []
    assert is_simplified(inst0) is True

    inst1 = generate_simplified(n=1, seed=1)
    assert len(inst1.tasks) == 1
    assert validate_instance(inst1) == []
    assert is_simplified(inst1) is True


# ---------------------------------------------------------------------------
# T3.1-07: Negative n raises ValueError
# ---------------------------------------------------------------------------


def test_negative_n_raises():
    """T3.1-07: n < 0 raises ValueError."""
    with pytest.raises(ValueError, match="n must be non-negative"):
        generate_simplified(n=-1, seed=1)


# ---------------------------------------------------------------------------
# T3.1-08: Overlap factor monotonic
# ---------------------------------------------------------------------------


def _pairwise_overlap_fraction(instance: Instance) -> float:
    tasks = list(instance.tasks)
    n = len(tasks)
    if n < 2:
        return 0.0
    overlaps = 0
    total = n * (n - 1) // 2
    for i in range(n):
        ti = tasks[i]
        for j in range(i + 1, n):
            tj = tasks[j]
            # Half-open overlap: max(starts) < min(ends)
            if max(ti.window_start, tj.window_start) < min(ti.window_end, tj.window_end):
                overlaps += 1
    return overlaps / total


def test_overlap_factor_monotonic():
    """T3.1-08: Mean pairwise overlap at 0.9 is higher than at 0.1 over 20 seeds."""
    overlaps_low = []
    overlaps_high = []
    for seed in range(1, 21):
        inst_low = generate_simplified(n=40, seed=seed, overlap_factor=0.1)
        inst_high = generate_simplified(n=40, seed=seed, overlap_factor=0.9)
        overlaps_low.append(_pairwise_overlap_fraction(inst_low))
        overlaps_high.append(_pairwise_overlap_fraction(inst_high))

    mean_low = sum(overlaps_low) / len(overlaps_low)
    mean_high = sum(overlaps_high) / len(overlaps_high)
    assert mean_high > mean_low


# ---------------------------------------------------------------------------
# T3.1-09: Scale test (n=10,000 generated in under 2s)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_scale_generation():
    """T3.1-09: Generating n=10,000 tasks takes under 2.0 seconds."""
    t0 = time.perf_counter()
    inst = generate_simplified(n=10000, seed=999)
    elapsed = time.perf_counter() - t0
    assert len(inst.tasks) == 10000
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# T3.1-10: Extended instance is not simplified
# ---------------------------------------------------------------------------


def test_extended_instance_is_not_simplified():
    """T3.1-10: Instance with 2 corridors is rejected by is_simplified."""
    c1 = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    c2 = Corridor(id=2, traffic_level="high", asset_ids=(2,))
    res = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    task = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=50,
        duration=50,
        criticality=1,
        urgency=1,
        demands={"crew": 1},
        depends_on=(),
    )
    inst = Instance(
        tasks=(task,),
        corridors=(c1, c2),
        resources=(res,),
        timetable=(),
        horizon=1440,
    )
    assert is_simplified(inst) is False
