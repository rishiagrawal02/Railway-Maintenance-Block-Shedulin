"""Tests for brute-force oracle solver (Milestone 4.2)."""

import time
from pathlib import Path

import pytest

from rbp.algorithms.brute_force import solve_brute_force
from rbp.generation.simplified import generate_simplified
from rbp.models import Corridor, Instance, Interval, Resource, Task
from rbp.validation import validate_schedule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hand_instance() -> Instance:
    """Hand fixture from Milestone 4.1."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tasks = (
        Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=3, duration=3,
             criticality=1, urgency=5, demands={"crew": 1}, depends_on=()),
        Task(id=2, corridor_id=1, asset_id=1, window_start=2, window_end=5, duration=3,
             criticality=2, urgency=1, demands={"crew": 1}, depends_on=()),
        Task(id=3, corridor_id=1, asset_id=1, window_start=4, window_end=7, duration=3,
             criticality=1, urgency=4, demands={"crew": 1}, depends_on=()),
        Task(id=4, corridor_id=1, asset_id=1, window_start=6, window_end=9, duration=3,
             criticality=2, urgency=3, demands={"crew": 1}, depends_on=()),
        Task(id=5, corridor_id=1, asset_id=1, window_start=8, window_end=10, duration=2,
             criticality=1, urgency=3, demands={"crew": 1}, depends_on=()),
    )
    return Instance(
        tasks=tasks,
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )


# ---------------------------------------------------------------------------
# T4.2-01: Hand example
# ---------------------------------------------------------------------------


def test_hand_example():
    """T4.2-01: Brute force matches hand example objective 44."""
    inst = _make_hand_instance()
    res = solve_brute_force(inst)
    assert res.objective == 44


# ---------------------------------------------------------------------------
# T4.2-02: Empty and single
# ---------------------------------------------------------------------------


def test_empty_and_single():
    """T4.2-02: n=0 returns 0; n=1 returns single task weight."""
    inst0 = generate_simplified(n=0, seed=1)
    res0 = solve_brute_force(inst0)
    assert res0.objective == 0
    assert len(res0.schedule.starts) == 0

    inst1 = generate_simplified(n=1, seed=42)
    res1 = solve_brute_force(inst1)
    assert res1.objective == inst1.tasks[0].weight
    assert res1.schedule.starts == {inst1.tasks[0].id: inst1.tasks[0].window_start}


# ---------------------------------------------------------------------------
# T4.2-03: All overlapping
# ---------------------------------------------------------------------------


def test_all_overlapping():
    """T4.2-03: 6 mutually overlapping tasks chooses only the maximum single weight."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tasks = tuple(
        Task(
            id=i,
            corridor_id=1,
            asset_id=1,
            window_start=0,
            window_end=10,
            duration=10,
            criticality=i,
            urgency=1,
            demands={"crew": 1},
            depends_on=(),
        )
        for i in range(1, 7)
    )
    inst = Instance(
        tasks=tasks,
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_brute_force(inst)
    assert res.objective == 61  # crit=6 not in 1-5, but 10*6+1=61
    assert len(res.schedule.starts) == 1


# ---------------------------------------------------------------------------
# T4.2-04: All disjoint
# ---------------------------------------------------------------------------


def test_all_disjoint():
    """T4.2-04: 6 disjoint tasks returns the sum of all weights."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tasks = tuple(
        Task(
            id=i,
            corridor_id=1,
            asset_id=1,
            window_start=i * 20,
            window_end=i * 20 + 10,
            duration=10,
            criticality=2,
            urgency=1,
            demands={"crew": 1},
            depends_on=(),
        )
        for i in range(1, 7)
    )
    inst = Instance(
        tasks=tasks,
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_brute_force(inst)
    assert res.objective == sum(t.weight for t in tasks)
    assert len(res.schedule.starts) == 6


# ---------------------------------------------------------------------------
# T4.2-05: Size limit enforcement
# ---------------------------------------------------------------------------


def test_size_limit_enforced():
    """T4.2-05: n=21 exceeds default max_n=20 and raises ValueError."""
    inst = generate_simplified(n=21, seed=1)
    with pytest.raises(ValueError, match="exceeds brute-force limit"):
        solve_brute_force(inst)


# ---------------------------------------------------------------------------
# T4.2-06: Touching intervals
# ---------------------------------------------------------------------------


def test_touching_intervals():
    """T4.2-06: Touching intervals [0,5) and [5,9) are both chosen."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    t1 = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=5, duration=5,
        criticality=1, urgency=1, demands={"crew": 1}, depends_on=(),
    )
    t2 = Task(
        id=2, corridor_id=1, asset_id=1, window_start=5, window_end=9, duration=4,
        criticality=1, urgency=1, demands={"crew": 1}, depends_on=(),
    )
    inst = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_brute_force(inst)
    assert res.objective == t1.weight + t2.weight
    assert set(res.schedule.starts.keys()) == {1, 2}


# ---------------------------------------------------------------------------
# T4.2-07: Output valid according to independent validator
# ---------------------------------------------------------------------------


def test_output_valid_30_instances():
    """T4.2-07: Brute force schedules on 30 instances (n <= 12) all pass independent validation."""
    for seed in range(1, 31):
        n = 5 + (seed % 8)  # between 5 and 12
        inst = generate_simplified(n=n, seed=seed)
        res = solve_brute_force(inst)
        report = validate_schedule(inst, res.schedule)
        assert report.valid is True


# ---------------------------------------------------------------------------
# T4.2-08: Runtime on n=16
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_runtime_n16():
    """T4.2-08: n=16 solves in well under 10 seconds."""
    inst = generate_simplified(n=16, seed=99)
    t0 = time.perf_counter()
    res = solve_brute_force(inst)
    elapsed = time.perf_counter() - t0
    assert res.objective > 0
    assert elapsed < 10.0


# ---------------------------------------------------------------------------
# Independence Check
# ---------------------------------------------------------------------------


def test_brute_force_independence():
    """Verify brute_force.py does not import wis_dp or constraints."""
    import ast

    source_file = (
        Path(__file__).parent.parent / "src" / "rbp" / "algorithms" / "brute_force.py"
    )
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "wis_dp" not in alias.name
                assert "constraints" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "wis_dp" not in node.module
                assert "constraints" not in node.module
