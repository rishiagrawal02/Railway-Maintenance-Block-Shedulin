"""Mandatory correctness gate tests: WIS-DP vs Brute-Force (Milestone 4.3)."""

import random

from rbp.algorithms.brute_force import solve_brute_force
from rbp.algorithms.wis_dp import solve_wis_dp
from rbp.generation.simplified import generate_simplified
from rbp.models import Corridor, Instance, Interval, Resource, Task
from rbp.validation import validate_schedule

# ---------------------------------------------------------------------------
# T4.3-01, T4.3-03, T4.3-04: 100 Random Gate Cases
# ---------------------------------------------------------------------------


def test_random_gate_100_cases():
    """T4.3-01, T4.3-03, T4.3-04: Across 100 seeds (0-99),

    WIS-DP equals Brute Force, schedules pass independent validator,
    and reported objective equals sum of scheduled task weights.
    """
    for seed in range(100):
        rng = random.Random(seed + 1000)
        n = rng.randint(1, 16)
        overlap = round(rng.uniform(0.1, 0.9), 2)

        inst = generate_simplified(n=n, seed=seed, overlap_factor=overlap)

        res_dp = solve_wis_dp(inst)
        res_bf = solve_brute_force(inst)

        # T4.3-01: Exact objective match
        assert res_dp.objective == res_bf.objective, (
            f"Seed {seed} objective mismatch: DP={res_dp.objective} != BF={res_bf.objective}"
        )

        # T4.3-03: DP schedule passes independent validator
        report = validate_schedule(inst, res_dp.schedule)
        assert report.valid is True, f"Seed {seed} DP schedule invalid: {report.violations}"

        # T4.3-04: Reported equals recomputed objective
        recomputed = sum(inst.task(tid).weight for tid in res_dp.schedule.starts)
        assert res_dp.objective == recomputed, (
            f"Seed {seed} reported {res_dp.objective} != recomputed {recomputed}"
        )


# ---------------------------------------------------------------------------
# T4.3-02: Adversarial Families (7 families x 5 sizes)
# ---------------------------------------------------------------------------


def _build_adversarial_family(family: str, size: int) -> Instance:
    """Construct an adversarial simplified instance family."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tasks: list[Task] = []

    if family == "all_overlapping":
        for i in range(1, size + 1):
            tasks.append(
                Task(
                    id=i,
                    corridor_id=1,
                    asset_id=1,
                    window_start=0,
                    window_end=100,
                    duration=100,
                    criticality=(i % 5) + 1,
                    urgency=1,
                    demands={"crew": 1},
                    depends_on=(),
                )
            )

    elif family == "chain_of_touching":
        for i in range(1, size + 1):
            s = (i - 1) * 20
            tasks.append(
                Task(
                    id=i,
                    corridor_id=1,
                    asset_id=1,
                    window_start=s,
                    window_end=s + 20,
                    duration=20,
                    criticality=(i % 5) + 1,
                    urgency=2,
                    demands={"crew": 1},
                    depends_on=(),
                )
            )

    elif family == "nested_intervals":
        for i in range(1, size + 1):
            s = (i - 1) * 5
            e = 500 - (i - 1) * 5
            tasks.append(
                Task(
                    id=i,
                    corridor_id=1,
                    asset_id=1,
                    window_start=s,
                    window_end=e,
                    duration=e - s,
                    criticality=3,
                    urgency=(i % 5) + 1,
                    demands={"crew": 1},
                    depends_on=(),
                )
            )

    elif family == "equal_end_times":
        for i in range(1, size + 1):
            s = (i - 1) * 10
            tasks.append(
                Task(
                    id=i,
                    corridor_id=1,
                    asset_id=1,
                    window_start=s,
                    window_end=500,
                    duration=500 - s,
                    criticality=(i % 5) + 1,
                    urgency=3,
                    demands={"crew": 1},
                    depends_on=(),
                )
            )

    elif family == "equal_weights":
        for i in range(1, size + 1):
            s = (i - 1) * 12
            tasks.append(
                Task(
                    id=i,
                    corridor_id=1,
                    asset_id=1,
                    window_start=s,
                    window_end=s + 20,
                    duration=20,
                    criticality=2,
                    urgency=1,
                    demands={"crew": 1},
                    depends_on=(),
                )
            )

    elif family == "identical_intervals":
        for i in range(1, size + 1):
            tasks.append(
                Task(
                    id=i,
                    corridor_id=1,
                    asset_id=1,
                    window_start=50,
                    window_end=150,
                    duration=100,
                    criticality=1,
                    urgency=(i % 5) + 1,
                    demands={"crew": 1},
                    depends_on=(),
                )
            )

    elif family == "long_low_vs_short_high":
        # 1 long low-weight task covering [0, size*30)
        tasks.append(
            Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=size * 30,
                 duration=size * 30, criticality=1, urgency=1, demands={"crew": 1}, depends_on=())
        )
        # size - 1 short high-weight tasks inside
        for i in range(2, size + 1):
            s = (i - 2) * 30
            tasks.append(
                Task(id=i, corridor_id=1, asset_id=1, window_start=s, window_end=s + 25,
                     duration=25, criticality=5, urgency=5, demands={"crew": 1}, depends_on=())
            )

    return Instance(
        tasks=tuple(tasks),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )


def test_adversarial_families():
    """T4.3-02: 7 adversarial families across 5 sizes (3, 5, 8, 12, 15) match brute force."""
    families = [
        "all_overlapping",
        "chain_of_touching",
        "nested_intervals",
        "equal_end_times",
        "equal_weights",
        "identical_intervals",
        "long_low_vs_short_high",
    ]
    sizes = [3, 5, 8, 12, 15]

    for fam in families:
        for size in sizes:
            inst = _build_adversarial_family(fam, size)
            res_dp = solve_wis_dp(inst)
            res_bf = solve_brute_force(inst)
            assert res_dp.objective == res_bf.objective, (
                f"Adversarial family '{fam}' size {size} failed: "
                f"DP={res_dp.objective} != BF={res_bf.objective}"
            )
            report = validate_schedule(inst, res_dp.schedule)
            assert report.valid is True
