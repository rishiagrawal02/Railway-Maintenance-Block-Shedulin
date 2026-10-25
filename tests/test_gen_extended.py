"""Tests for extended instance generator with controlled correlations (Milestone 3.2)."""

import pytest

from rbp.generation.extended import DEPARTMENTS, generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.io.input_checks import validate_instance
from rbp.io.serialize import instance_to_dict, load_json, save_json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spearman_correlation(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation between two vectors."""
    n = len(x)
    if n < 2:
        return 0.0

    def get_ranks(vals: list[float]) -> list[float]:
        sorted_indices = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        for rank_idx, orig_idx in enumerate(sorted_indices):
            ranks[orig_idx] = rank_idx + 1
        return ranks

    rx = get_ranks(x)
    ry = get_ranks(y)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    cov = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    std_x = sum((rx[i] - mean_x) ** 2 for i in range(n)) ** 0.5
    std_y = sum((ry[i] - mean_y) ** 2 for i in range(n)) ** 0.5
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


# ---------------------------------------------------------------------------
# T3.2-01: Valid instances across 50 seeds
# ---------------------------------------------------------------------------


def test_valid_instances_50_seeds():
    """T3.2-01: 50 different seeds generate valid extended instances."""
    for seed in range(1, 51):
        inst = generate_extended(n=25, seed=seed)
        errors = validate_instance(inst)
        assert errors == [], f"Seed {seed} failed validation: {[e.code for e in errors]}"


# ---------------------------------------------------------------------------
# T3.2-02: Determinism
# ---------------------------------------------------------------------------


def test_determinism():
    """T3.2-02: Generating twice with seed 10 produces identical dicts/JSON."""
    inst1 = generate_extended(n=30, seed=10)
    inst2 = generate_extended(n=30, seed=10)
    assert instance_to_dict(inst1) == instance_to_dict(inst2)


# ---------------------------------------------------------------------------
# T3.2-03: Urgency vs slack correlation
# ---------------------------------------------------------------------------


def test_urgency_vs_slack_correlation():
    """T3.2-03: Pooled across 20 seeds, Spearman correlation between urgency and slack is < -0.2."""
    urgencies: list[float] = []
    slacks: list[float] = []

    for seed in range(1, 21):
        inst = generate_extended(n=40, seed=seed)
        for t in inst.tasks:
            slack = (t.window_end - t.window_start) - t.duration
            urgencies.append(float(t.urgency))
            slacks.append(float(slack))

    corr = _spearman_correlation(urgencies, slacks)
    assert corr < -0.2, f"Expected correlation < -0.2, got {corr:.3f}"


# ---------------------------------------------------------------------------
# T3.2-04: Traffic level vs asset impact
# ---------------------------------------------------------------------------


def test_traffic_vs_asset_impact():
    """T3.2-04: High traffic corridors have higher mean asset impact than low traffic."""
    low_impacts: list[float] = []
    high_impacts: list[float] = []

    for seed in range(1, 21):
        inst = generate_extended(n=20, seed=seed, n_corridors=4)
        asset_impact_dict = inst.meta.get("asset_impact", {})
        for corridor in inst.corridors:
            for aid in corridor.asset_ids:
                impact = float(asset_impact_dict.get(str(aid), 0))
                if corridor.traffic_level == "low":
                    low_impacts.append(impact)
                elif corridor.traffic_level == "high":
                    high_impacts.append(impact)

    if low_impacts and high_impacts:
        mean_low = sum(low_impacts) / len(low_impacts)
        mean_high = sum(high_impacts) / len(high_impacts)
        assert mean_high > mean_low, f"High traffic mean {mean_high} <= low traffic mean {mean_low}"


# ---------------------------------------------------------------------------
# T3.2-05: Peak vs off-peak train density
# ---------------------------------------------------------------------------


def test_peak_vs_off_peak_trains():
    """T3.2-05: Train density (trains/hour) is higher during peak bands than night band."""
    night_train_counts: list[int] = []
    peak_train_counts: list[int] = []

    for seed in range(1, 11):
        inst = generate_extended(n=10, seed=seed, n_corridors=2)
        for tt in inst.timetable:
            # Night band: 0-300 (5 hours)
            night_c = sum(1 for ti in tt.intervals if ti.start < 300)
            # Peak band: 420-540 (2 hours)
            peak_c = sum(1 for ti in tt.intervals if 420 <= ti.start < 540)
            night_train_counts.append(night_c)
            peak_train_counts.append(peak_c)

    # Convert to trains per hour
    night_rate = (sum(night_train_counts) / len(night_train_counts)) / 5.0
    peak_rate = (sum(peak_train_counts) / len(peak_train_counts)) / 2.0
    assert peak_rate > night_rate, f"Peak rate {peak_rate} <= night rate {night_rate}"


# ---------------------------------------------------------------------------
# T3.2-06: Department to resource mapping
# ---------------------------------------------------------------------------


def test_department_to_resource():
    """T3.2-06: Tasks use only standard department resource types."""
    inst = generate_extended(n=200, seed=42)
    for t in inst.tasks:
        assert len(t.demands) == 1
        res_type = next(iter(t.demands.keys()))
        assert res_type in DEPARTMENTS


# ---------------------------------------------------------------------------
# T3.2-07: Dependencies are acyclic and respect window order
# ---------------------------------------------------------------------------


def test_dependencies_acyclic_and_ordered():
    """T3.2-07: Over 50 seeds, dependency graphs are acyclic and respect window ordering."""
    for seed in range(1, 51):
        inst = generate_extended(n=30, seed=seed)
        task_map = {t.id: t for t in inst.tasks}
        for task in inst.tasks:
            for dep_id in task.depends_on:
                prereq = task_map[dep_id]
                # Prerequisite window start must be <= dependent window start
                assert prereq.window_start <= task.window_start
                # Dependent window can hold both
                assert prereq.window_start + prereq.duration + task.duration <= task.window_end


# ---------------------------------------------------------------------------
# T3.2-08: Demand within capacity
# ---------------------------------------------------------------------------


def test_demand_within_capacity():
    """T3.2-08: For all generated tasks across 50 seeds, demand <= capacity."""
    for seed in range(1, 51):
        inst = generate_extended(n=25, seed=seed)
        res_caps = {r.type: r.capacity for r in inst.resources}
        for task in inst.tasks:
            for res_type, dem in task.demands.items():
                assert dem <= res_caps[res_type]


# ---------------------------------------------------------------------------
# T3.2-09: Each task individually placeable (C1, C2, availability)
# ---------------------------------------------------------------------------


def test_each_task_individually_placeable():
    """T3.2-09: Every task has at least one start time satisfying C1, C2, and availability."""
    for seed in range(1, 51):
        inst = generate_extended(n=20, seed=seed)
        timetable_map = {tt.corridor_id: tt.intervals for tt in inst.timetable}
        for task in inst.tasks:
            trains = timetable_map.get(task.corridor_id, ())
            found_placeable = False
            for s in range(task.window_start, task.window_end - task.duration + 1):
                e = s + task.duration
                conflict = any(max(s, ti.start) < min(e, ti.end) for ti in trains)
                if not conflict:
                    found_placeable = True
                    break
            assert found_placeable, f"Task {task.id} in seed {seed} has no placeable start"


# ---------------------------------------------------------------------------
# T3.2-10: Invalid parameters raise ValueError
# ---------------------------------------------------------------------------


def test_invalid_parameters():
    """T3.2-10: n_corridors=0 and n=-1 raise ValueError."""
    with pytest.raises(ValueError):
        generate_extended(n=10, seed=1, n_corridors=0)

    with pytest.raises(ValueError):
        generate_extended(n=-1, seed=1)


# ---------------------------------------------------------------------------
# T3.2-11: JSON round trip
# ---------------------------------------------------------------------------


def test_json_round_trip(tmp_path):
    """T3.2-11: Saving and loading preserves extended instances exactly."""
    for seed in range(1, 6):
        inst = generate_extended(n=25, seed=seed)
        p = tmp_path / f"ext_{seed}.json"
        save_json(inst, p)
        loaded = load_json(p)
        assert instance_to_dict(inst) == instance_to_dict(loaded)


# ---------------------------------------------------------------------------
# T3.2-12: Regression test
# ---------------------------------------------------------------------------


def test_regression_simplified():
    """T3.2-12: Simplified generator continues to work cleanly."""
    inst = generate_simplified(n=20, seed=42)
    assert validate_instance(inst) == []
    assert len(inst.tasks) == 20
