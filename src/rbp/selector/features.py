"""Complexity features and score computation for adaptive algorithm selection (Milestone 8.1).

Computes 5 normalized complexity features in [0, 1]:
  - f1_size: min(1, n / n_ref), n_ref = 200
  - f2_conflict_density: overlapping-window pairs among same-asset pairs / same-asset pairs
  - f3_resource_contention: max over types of min(1, sum(demand * dur) / (cap * avail_mins))
  - f4_window_tightness: mean over tasks of duration / window_length
  - f5_corridor_utilization: mean over corridors of min(1, (task_mins + train_mins) / horizon)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rbp.models.instance import Instance
from rbp.models.task import Task

DEFAULT_N_REF = 200
DEFAULT_CONFIG_PATH = Path("config/threshold.json")


@dataclass(frozen=True, slots=True)
class Features:
    """Normalized complexity features for an instance in [0, 1]."""

    f1_size: float
    f2_conflict_density: float
    f3_resource_contention: float
    f4_window_tightness: float
    f5_corridor_utilization: float

    def as_tuple(self) -> tuple[float, float, float, float, float]:
        """Return features as a 5-tuple."""
        return (
            self.f1_size,
            self.f2_conflict_density,
            self.f3_resource_contention,
            self.f4_window_tightness,
            self.f5_corridor_utilization,
        )

    def as_dict(self) -> dict[str, float]:
        """Return features as a named dictionary."""
        return {
            "f1_size": self.f1_size,
            "f2_conflict_density": self.f2_conflict_density,
            "f3_resource_contention": self.f3_resource_contention,
            "f4_window_tightness": self.f4_window_tightness,
            "f5_corridor_utilization": self.f5_corridor_utilization,
        }


def feature_f1_size(instance: Instance, n_ref: int = DEFAULT_N_REF) -> float:
    """Compute f1 size feature: min(1.0, n / n_ref)."""
    n = len(instance.tasks)
    if n <= 0:
        return 0.0
    return min(1.0, n / float(n_ref))


def _count_overlapping_pairs_sweep(tasks: Sequence[Task]) -> int:
    """Count overlapping window pairs in O(m log m) time using a sweep-line."""
    if len(tasks) < 2:
        return 0

    # Events: order=0 for end, order=1 for start so that ends at time t are processed
    # before starts at time t (half-open intervals [start, end) do not overlap at boundary).
    events: list[tuple[int, int, int]] = []
    for t in tasks:
        events.append((t.window_start, 1, t.id))
        events.append((t.window_end, 0, t.id))

    events.sort(key=lambda e: (e[0], e[1]))

    active_count = 0
    overlap_count = 0
    for _time, order, _tid in events:
        if order == 1:
            overlap_count += active_count
            active_count += 1
        else:
            active_count -= 1

    return overlap_count


def _count_overlapping_pairs_reference(tasks: Sequence[Task]) -> int:
    """Reference O(m^2) count of overlapping pairs, used in verification tests."""
    count = 0
    m = len(tasks)
    for i in range(m):
        for j in range(i + 1, m):
            t1, t2 = tasks[i], tasks[j]
            if max(t1.window_start, t2.window_start) < min(t1.window_end, t2.window_end):
                count += 1
    return count


def feature_f2_conflict_density(instance: Instance) -> float:
    """Compute f2 conflict density.

    Ratio of overlapping-window pairs among same-asset pairs to total same-asset pairs.
    Returns 0.0 if there are no same-asset pairs.
    """
    if len(instance.tasks) < 2:
        return 0.0

    # Group tasks by asset_id
    asset_tasks: dict[int, list[Task]] = {}
    for t in instance.tasks:
        asset_tasks.setdefault(t.asset_id, []).append(t)

    total_pairs = 0
    overlapping_pairs = 0

    for tasks in asset_tasks.values():
        m = len(tasks)
        if m < 2:
            continue
        total_pairs += m * (m - 1) // 2
        overlapping_pairs += _count_overlapping_pairs_sweep(tasks)

    if total_pairs == 0:
        return 0.0
    return overlapping_pairs / float(total_pairs)


def feature_f3_resource_contention(instance: Instance) -> float:
    """Compute f3 resource contention.

    Max over resource types of min(1, sum(demand * dur) / (capacity * available_mins)).
    Returns 0.0 if no resources or no demand.
    Returns 1.0 if demand > 0 but available capacity or minutes is 0.
    """
    if not instance.resources or not instance.tasks:
        return 0.0

    max_contention = 0.0

    for res in instance.resources:
        # Compute available minutes
        avail_mins = sum(iv.end - iv.start for iv in res.availability)
        cap = res.capacity

        # Compute total demanded minutes for this resource type
        dem_mins = sum(t.demands.get(res.type, 0) * t.duration for t in instance.tasks)

        if cap * avail_mins <= 0:
            if dem_mins > 0:
                contention = 1.0
            else:
                contention = 0.0
        else:
            contention = min(1.0, dem_mins / float(cap * avail_mins))

        if contention > max_contention:
            max_contention = contention

    return max_contention


def feature_f4_window_tightness(instance: Instance) -> float:
    """Compute f4 time-window tightness: mean of duration / window_length over tasks.

    A value of 1.0 indicates fixed-interval tasks. Returns 0.0 if no tasks.
    """
    if not instance.tasks:
        return 0.0

    total_ratio = 0.0
    for t in instance.tasks:
        win_len = t.window_end - t.window_start
        if win_len <= 0:
            total_ratio += 1.0
        else:
            total_ratio += min(1.0, t.duration / float(win_len))

    return total_ratio / float(len(instance.tasks))


def feature_f5_corridor_utilization(instance: Instance) -> float:
    """Compute f5 corridor utilization.

    Mean over corridors of min(1, (task_minutes + train_minutes) / horizon).
    Returns 0.0 if horizon <= 0.
    """
    if instance.horizon <= 0:
        return 0.0

    # Determine corridor IDs to evaluate
    corridor_ids = [c.id for c in instance.corridors]
    if not corridor_ids:
        corridor_ids = sorted({t.corridor_id for t in instance.tasks})
    if not corridor_ids:
        corridor_ids = [0]

    # Pre-calculate task minutes per corridor
    task_mins_by_corridor: dict[int, int] = {}
    for t in instance.tasks:
        task_mins_by_corridor[t.corridor_id] = (
            task_mins_by_corridor.get(t.corridor_id, 0) + t.duration
        )

    # Pre-calculate train minutes per corridor
    train_mins_by_corridor: dict[int, int] = {}
    for tt in instance.timetable:
        train_mins_by_corridor[tt.corridor_id] = (
            train_mins_by_corridor.get(tt.corridor_id, 0)
            + sum(iv.end - iv.start for iv in tt.intervals)
        )

    total_util = 0.0
    for cid in corridor_ids:
        t_mins = task_mins_by_corridor.get(cid, 0)
        tr_mins = train_mins_by_corridor.get(cid, 0)
        util = min(1.0, (t_mins + tr_mins) / float(instance.horizon))
        total_util += util

    return total_util / float(len(corridor_ids))


def compute_features(instance: Instance, n_ref: int = DEFAULT_N_REF) -> Features:
    """Compute all 5 normalized complexity features for an instance."""
    return Features(
        f1_size=feature_f1_size(instance, n_ref=n_ref),
        f2_conflict_density=feature_f2_conflict_density(instance),
        f3_resource_contention=feature_f3_resource_contention(instance),
        f4_window_tightness=feature_f4_window_tightness(instance),
        f5_corridor_utilization=feature_f5_corridor_utilization(instance),
    )


def load_alpha(path: str | Path | None = None) -> tuple[float, float, float, float, float]:
    """Load and validate alpha weights from config file.

    Weights must be 5 non-negative floats that sum to 1.0 (+- 1e-5).
    """
    config_file = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "alpha" not in data:
        raise ValueError(f"Missing 'alpha' field in configuration: {config_file}")

    raw_alpha = data["alpha"]
    if not isinstance(raw_alpha, (list, tuple)) or len(raw_alpha) != 5:
        raise ValueError(
            f"Alpha weights must be a list or tuple of exactly 5 numbers, got {raw_alpha!r}"
        )

    alpha_vals = tuple(float(x) for x in raw_alpha)
    if any(a < 0.0 for a in alpha_vals):
        raise ValueError(f"Alpha weights must be non-negative, got {alpha_vals}")

    if abs(sum(alpha_vals) - 1.0) > 1e-5:
        raise ValueError(
            f"Alpha weights must sum to 1.0, got sum={sum(alpha_vals)} from {alpha_vals}"
        )

    return (alpha_vals[0], alpha_vals[1], alpha_vals[2], alpha_vals[3], alpha_vals[4])


def complexity_score(
    features: Features,
    alpha: Sequence[float] | None = None,
) -> float:
    """Compute weighted complexity score C = sum(alpha_i * f_i).

    Parameters:
      features: Features dataclass instance.
      alpha: 5-element sequence of weights summing to 1.0. If None, loaded from threshold.json.
    """
    if alpha is None:
        alpha_weights = load_alpha()
    else:
        if len(alpha) != 5:
            raise ValueError(f"Alpha must have exactly 5 elements, got {len(alpha)}")
        if abs(sum(alpha) - 1.0) > 1e-5:
            raise ValueError(f"Alpha must sum to 1.0, got sum={sum(alpha)}")
        alpha_weights = tuple(float(x) for x in alpha)

    f_vals = features.as_tuple()
    score = sum(a * f for a, f in zip(alpha_weights, f_vals))
    return score
