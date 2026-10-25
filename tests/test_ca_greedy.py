"""Tests for Conflict-Aware Greedy (CA-GREEDY) heuristic (Milestone 5.3)."""

from rbp.algorithms.ca_greedy import solve_ca_greedy
from rbp.algorithms.naive_greedy import solve_naive_greedy
from rbp.algorithms.wis_dp import solve_wis_dp
from rbp.generation.extended import generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval
from rbp.validation.validator import validate_schedule
from tests.test_ca_terms import _make_fixture_f


def test_t53_01_fixture_f():
    """T5.3-01: Fixture F yields NAIVE=52, CA=73."""
    inst, _, _, _ = _make_fixture_f()
    res_naive = solve_naive_greedy(inst)
    res_ca = solve_ca_greedy(inst)

    assert res_naive.objective == 52
    assert res_ca.objective == 73


def test_t53_02_100_extended_valid():
    """T5.3-02: 100 extended instances pass validate_schedule."""
    for seed in range(100):
        inst = generate_extended(n=12, seed=seed)
        res = solve_ca_greedy(inst)
        report = validate_schedule(inst, res.schedule)
        assert report.valid, f"Seed {seed} produced invalid schedule: {report.violations}"


def test_t53_03_determinism():
    """T5.3-03: Multiple executions on the same instance yield identical results."""
    inst = generate_extended(n=25, seed=42)
    res1 = solve_ca_greedy(inst)
    res2 = solve_ca_greedy(inst)

    assert res1.objective == res2.objective
    assert res1.schedule.starts == res2.schedule.starts


def test_t53_04_lambdas_zero_matches_naive_without_deps():
    """T5.3-04: With all lambdas 0, CA matches NAIVE on dependency-free instances."""
    for seed in range(10):
        inst = generate_simplified(n=15, seed=seed)
        # All simplified instances have no dependencies
        res_naive = solve_naive_greedy(inst)
        res_ca = solve_ca_greedy(inst, lambda_b=0.0, lambda_r=0.0, lambda_c=0.0)

        assert res_ca.objective == res_naive.objective
        assert res_ca.schedule.starts == res_naive.schedule.starts


def test_t53_05_prerequisite_unblocks_heavier_dependent():
    """T5.3-05: Priority queue unblocks dependent with heavier weight than prerequisite."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    res = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))

    # Task 1 (Prereq): weight 11, [0, 100), duration 10
    task_p = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=100,
        duration=10,
        criticality=1,
        urgency=1,
        demands={},
        depends_on=(),
    )
    # Task 2 (Dependent): weight 99, [0, 100), duration 10, depends on Task 1
    task_d = Task(
        id=2,
        corridor_id=1,
        asset_id=2,
        window_start=0,
        window_end=100,
        duration=10,
        criticality=9,
        urgency=9,
        demands={},
        depends_on=(1,),
    )
    inst = Instance(
        tasks=(task_p, task_d),
        corridors=(corridor,),
        resources=(res,),
        timetable=(),
        horizon=1440,
    )

    res = solve_ca_greedy(inst)
    assert 1 in res.schedule.starts
    assert 2 in res.schedule.starts
    assert res.schedule.starts[2] >= res.schedule.starts[1] + task_p.duration
    assert res.objective == 11 + 99


def test_t53_06_infeasible_prerequisite_rejects_dependent():
    """T5.3-06: Infeasible prerequisite prevents dependent from ever being scheduled."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    res = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    # Train blocking entire corridor at [0, 50)
    tt = Timetable(corridor_id=1, intervals=(TrainInterval(0, 50),))

    # Task 1: cannot be placed because train completely blocks its window [0, 50)
    task_p = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=50,
        duration=30,
        criticality=1,
        urgency=1,
        demands={},
        depends_on=(),
    )
    # Task 2: valid window [50, 200), but depends on Task 1
    task_d = Task(
        id=2,
        corridor_id=1,
        asset_id=2,
        window_start=50,
        window_end=200,
        duration=30,
        criticality=9,
        urgency=9,
        demands={},
        depends_on=(1,),
    )
    inst = Instance(
        tasks=(task_p, task_d),
        corridors=(corridor,),
        resources=(res,),
        timetable=(tt,),
        horizon=1440,
    )

    res = solve_ca_greedy(inst)
    assert 1 not in res.schedule.starts
    assert 2 not in res.schedule.starts
    assert res.objective == 0


def test_t53_07_calibration_quality():
    """T5.3-07: Mean quality on calibration seeds 1000–1029: CA mean >= NAIVE mean."""
    naive_total = 0
    ca_total = 0
    wins = 0

    for seed in range(1000, 1030):
        inst = generate_extended(n=20, seed=seed)
        r_n = solve_naive_greedy(inst)
        r_c = solve_ca_greedy(inst)

        naive_total += r_n.objective
        ca_total += r_c.objective
        if r_c.objective > r_n.objective:
            wins += 1

    assert ca_total >= naive_total
    assert wins > 0


def test_t53_08_ca_le_wis_dp_on_simplified():
    """T5.3-08: CA objective <= WIS-DP optimal objective on simplified instances."""
    for seed in range(15):
        inst = generate_simplified(n=20, seed=seed)
        opt_res = solve_wis_dp(inst)
        ca_res = solve_ca_greedy(inst)

        assert ca_res.objective <= opt_res.objective


def test_t53_09_allow_skip_negative():
    """T5.3-09: allow_skip_negative=True skips task if max candidate score is negative."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res = Resource(type="crew", capacity=10, availability=(Interval(0, 1440),))

    # Two competing tasks on the same asset:
    # t1: w=20, id=1
    # t2: w=20, id=2
    # If lambda_b = 2.0, placing t1 blocks t2 (B=20) -> score = 20 - 2.0 * 20 = -20 < 0!
    t1 = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=10,
        duration=10,
        criticality=2,
        urgency=0,
        demands={},
        depends_on=(),
    )  # w=20, id=1
    t2 = Task(
        id=2,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=10,
        duration=10,
        criticality=2,
        urgency=0,
        demands={},
        depends_on=(),
    )  # w=20, id=2
    # If lambda_b = 2.0, placing t1 blocks t2 (B=20) -> score = 20 - 2.0 * 20 = -20 < 0!
    inst3 = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(res,),
        timetable=(),
        horizon=1440,
    )

    # With allow_skip_negative=True, t1 has negative score (-20), so it is skipped!
    # Then t2 is popped, has no remaining lookahead, score = 20 > 0, so t2 is placed!
    res_skip = solve_ca_greedy(inst3, lambda_b=2.0, allow_skip_negative=True)
    assert res_skip.meta["skipped_negative"] == 1
    assert 1 not in res_skip.schedule.starts
    assert 2 in res_skip.schedule.starts


def test_t53_10_metadata_contents():
    """T5.3-10: Metadata in AlgoResult contains required parameters and counters."""
    inst = generate_extended(n=10, seed=7)
    res = solve_ca_greedy(inst, lambda_b=1.2, lambda_r=0.4, lambda_c=0.6, lookahead_k=4)

    assert res.name == "ca_greedy"
    assert "runtime_s" in res.meta
    assert res.meta["n_tasks"] == 10
    assert "n_scheduled" in res.meta
    assert "skipped_infeasible" in res.meta
    assert "skipped_negative" in res.meta
    assert res.meta["lambda_b"] == 1.2
    assert res.meta["lambda_r"] == 0.4
    assert res.meta["lambda_c"] == 0.6
    assert res.meta["lookahead_k"] == 4
    assert res.meta["allow_skip_negative"] is False
