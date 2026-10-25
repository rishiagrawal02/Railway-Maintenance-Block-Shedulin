"""Tests for generator difficulty knobs and proxy metrics (Milestone 3.3)."""

from rbp.generation.extended import generate_extended
from rbp.models import Instance

# ---------------------------------------------------------------------------
# Proxy Metric Functions
# ---------------------------------------------------------------------------


def tightness_proxy(instance: Instance) -> float:
    """Mean duration over window length: higher means tighter windows."""
    if not instance.tasks:
        return 0.0
    ratios = [
        t.duration / (t.window_end - t.window_start)
        for t in instance.tasks
        if (t.window_end - t.window_start) > 0
    ]
    return sum(ratios) / len(ratios) if ratios else 0.0


def conflict_proxy(instance: Instance) -> float:
    """Same-asset window-overlap fraction: fraction of task pairs on same asset that overlap."""
    by_asset: dict[int, list] = {}
    for t in instance.tasks:
        by_asset.setdefault(t.asset_id, []).append(t)

    total_pairs = 0
    overlapping_pairs = 0
    for tasks in by_asset.values():
        n = len(tasks)
        if n < 2:
            continue
        for i in range(n):
            ti = tasks[i]
            for j in range(i + 1, n):
                tj = tasks[j]
                total_pairs += 1
                if max(ti.window_start, tj.window_start) < min(ti.window_end, tj.window_end):
                    overlapping_pairs += 1

    return overlapping_pairs / total_pairs if total_pairs > 0 else 0.0


def contention_proxy(instance: Instance) -> float:
    """Demand-minutes over capacity-minutes: higher means tighter resource capacity."""
    total_demand_minutes = 0
    for t in instance.tasks:
        for dem in t.demands.values():
            total_demand_minutes += t.duration * dem

    total_capacity_minutes = sum(r.capacity * instance.horizon for r in instance.resources)
    return total_demand_minutes / total_capacity_minutes if total_capacity_minutes > 0 else 0.0


def utilization_proxy(instance: Instance) -> float:
    """(Task plus train minutes) over corridor minutes: higher means busier corridors."""
    task_minutes = sum(t.duration for t in instance.tasks)
    train_minutes = sum(
        ti.end - ti.start
        for tt in instance.timetable
        for ti in tt.intervals
    )
    corridor_minutes = len(instance.corridors) * instance.horizon
    return (task_minutes + train_minutes) / corridor_minutes if corridor_minutes > 0 else 0.0


# ---------------------------------------------------------------------------
# T3.3-01: Slack knob
# ---------------------------------------------------------------------------


def test_slack_knob_moves_tightness():
    """T3.3-01: Tightness proxy decreases as window_slack_factor increases."""
    tightness_low_slack = []
    tightness_high_slack = []

    for seed in range(1, 21):
        inst_low = generate_extended(n=30, seed=seed, window_slack_factor=0.2)
        inst_high = generate_extended(n=30, seed=seed, window_slack_factor=2.5)
        tightness_low_slack.append(tightness_proxy(inst_low))
        tightness_high_slack.append(tightness_proxy(inst_high))

    mean_tight_low = sum(tightness_low_slack) / len(tightness_low_slack)
    mean_tight_high = sum(tightness_high_slack) / len(tightness_high_slack)
    assert mean_tight_low > mean_tight_high, (
        f"Expected low slack tightness ({mean_tight_low:.3f}) > high slack ({mean_tight_high:.3f})"
    )


# ---------------------------------------------------------------------------
# T3.3-02: Asset-count knob
# ---------------------------------------------------------------------------


def test_asset_count_knob_moves_conflict():
    """T3.3-02: Conflict proxy is higher with 2 assets per corridor than with 6."""
    conflicts_2_assets = []
    conflicts_6_assets = []

    for seed in range(1, 21):
        inst_2 = generate_extended(n=30, seed=seed, assets_per_corridor=2)
        inst_6 = generate_extended(n=30, seed=seed, assets_per_corridor=6)
        conflicts_2_assets.append(conflict_proxy(inst_2))
        conflicts_6_assets.append(conflict_proxy(inst_6))

    mean_c2 = sum(conflicts_2_assets) / len(conflicts_2_assets)
    mean_c6 = sum(conflicts_6_assets) / len(conflicts_6_assets)
    assert mean_c2 > mean_c6, (
        f"Expected 2-asset conflicts ({mean_c2:.3f}) > 6-asset conflicts ({mean_c6:.3f})"
    )


# ---------------------------------------------------------------------------
# T3.3-03: Capacity knob
# ---------------------------------------------------------------------------


def test_capacity_knob_moves_contention():
    """T3.3-03: Contention proxy is lower at resource_capacity_scale=2.0 than at 0.5."""
    contention_scale_05 = []
    contention_scale_20 = []

    for seed in range(1, 21):
        inst_05 = generate_extended(n=30, seed=seed, resource_capacity_scale=0.5)
        inst_20 = generate_extended(n=30, seed=seed, resource_capacity_scale=2.0)
        contention_scale_05.append(contention_proxy(inst_05))
        contention_scale_20.append(contention_proxy(inst_20))

    mean_05 = sum(contention_scale_05) / len(contention_scale_05)
    mean_20 = sum(contention_scale_20) / len(contention_scale_20)
    assert mean_05 > mean_20, (
        f"Expected scale 0.5 contention ({mean_05:.3f}) > scale 2.0 contention ({mean_20:.3f})"
    )


# ---------------------------------------------------------------------------
# T3.3-04: Load knob
# ---------------------------------------------------------------------------


def test_load_knob_moves_utilization():
    """T3.3-04: Utilization proxy is higher with corridor_load=1.8 than with 0.5."""
    util_low = []
    util_high = []

    for seed in range(1, 21):
        inst_low = generate_extended(n=30, seed=seed, corridor_load=0.5)
        inst_high = generate_extended(n=30, seed=seed, corridor_load=1.8)
        util_low.append(utilization_proxy(inst_low))
        util_high.append(utilization_proxy(inst_high))

    mean_low = sum(util_low) / len(util_low)
    mean_high = sum(util_high) / len(util_high)
    assert mean_high > mean_low, (
        f"Expected high load utilization ({mean_high:.3f}) > low load ({mean_low:.3f})"
    )
