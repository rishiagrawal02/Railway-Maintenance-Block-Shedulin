"""Conflict-Aware Greedy (CA-GREEDY) scoring terms and candidate generation (Milestone 5.2).

Implements the four look-ahead scoring components (Decision D10):
  1. Base priority: w_t
  2. Blocking penalty: B = sum(w_u for u whose feasible count drops to 0)
  3. Resource-fit bonus: R in [0, 1] = mean resource utilization over [start, start + duration)
  4. Conflict-creation penalty: C = sum(w_u * (1 - after/before) for u whose count drops
     but stays > 0)

Score = w_t - lambda_b * B + lambda_r * w_t * R - lambda_c * C
"""

from __future__ import annotations

from typing import Sequence

from rbp.algorithms.placement import event_starts
from rbp.constraints.predicates import is_feasible
from rbp.constraints.state import PlacementState
from rbp.models.instance import Instance
from rbp.models.task import Task


def lookahead_set(
    instance: Instance, state: PlacementState, lookahead_k: int
) -> list[Task]:
    """Return top lookahead_k unplaced tasks by priority (higher weight, shorter dur, lower id)."""
    if lookahead_k <= 0:
        return []

    unplaced = [t for t in instance.tasks if not state.is_placed(t.id)]
    unplaced.sort(key=lambda t: (-t.weight, t.duration, t.id))
    return unplaced[:lookahead_k]


def ca_candidates(
    instance: Instance,
    state: PlacementState,
    task: Task,
    lookahead_tasks: Sequence[Task] = (),
) -> list[int]:
    """Generate sorted unique feasible start times for task.

    Includes:
      - event_starts
      - latest start (task.window_end - task.duration)
      - flush alignments with lookahead tasks on the same asset:
        u.window_end and (u.window_start - task.duration)

    Filtered by is_feasible.
    """
    latest_start = task.window_end - task.duration
    if task.window_start > latest_start:
        return []

    candidates: set[int] = set(event_starts(instance, state, task))
    candidates.add(latest_start)

    # Flush alignments with lookahead tasks on the same asset
    for u in lookahead_tasks:
        if u.id == task.id:
            continue
        if u.asset_id == task.asset_id:
            candidates.add(u.window_end)
            candidates.add(u.window_start - task.duration)

    # Filter to [task.window_start, latest_start] and is_feasible
    valid_starts = [
        s for s in sorted(candidates)
        if task.window_start <= s <= latest_start and is_feasible(instance, state, task, s)
    ]
    return valid_starts


def count_feasible_starts(
    instance: Instance,
    state: PlacementState,
    task: Task,
    lookahead_tasks: Sequence[Task] = (),
) -> int:
    """Count number of feasible candidate starts for task."""
    return len(ca_candidates(instance, state, task, lookahead_tasks))


def compute_fit_term(
    instance: Instance, state: PlacementState, task: Task, start: int
) -> float:
    """Compute resource-fit bonus R in [0, 1] over [start, start + task.duration).

    Measures mean existing utilization: packing into already-busy resource intervals
    leaves larger contiguous free blocks for future tasks.
    Returns 0.0 if task has no resource demands.
    """
    if not task.demands:
        return 0.0

    end = start + task.duration
    util_per_res: list[float] = []

    for res_type in task.demands:
        try:
            res = instance.resource(res_type)
            cap = res.capacity
        except KeyError:
            continue

        if cap <= 0 or task.duration <= 0:
            continue

        existing_sum = sum(state.resource_usage_at(res_type, m) for m in range(start, end))
        mean_usage = existing_sum / task.duration
        util_fraction = min(1.0, mean_usage / cap)
        util_per_res.append(util_fraction)

    return sum(util_per_res) / len(util_per_res) if util_per_res else 0.0


def evaluate_ca_placement(
    instance: Instance,
    state: PlacementState,
    task: Task,
    start: int,
    lookahead_tasks: Sequence[Task],
    lambda_b: float = 1.0,
    lambda_r: float = 0.5,
    lambda_c: float = 0.5,
) -> tuple[float, float, float, float]:
    """Evaluate look-ahead score for placing task at candidate start.

    Tentatively places task, measures impact on lookahead_tasks, and restores state.

    Returns:
      (total_score, blocking_B, fit_R, conflict_C)
    """
    fit_r = compute_fit_term(instance, state, task, start)

    if not lookahead_tasks:
        total_score = float(task.weight) + lambda_r * float(task.weight) * fit_r
        return total_score, 0.0, fit_r, 0.0

    # 1. Measure feasible counts before placement
    before_counts: dict[int, int] = {}
    for u in lookahead_tasks:
        if u.id != task.id:
            before_counts[u.id] = count_feasible_starts(instance, state, u, lookahead_tasks)

    # 2. Tentatively place task
    state.place(task, start)

    # 3. Measure feasible counts after placement
    blocking_b = 0.0
    conflict_c = 0.0

    try:
        for u in lookahead_tasks:
            if u.id == task.id:
                continue
            before = before_counts[u.id]
            if before == 0:
                continue

            after = count_feasible_starts(instance, state, u, lookahead_tasks)
            if after == 0:
                # Dropped to 0: completely blocked
                blocking_b += float(u.weight)
            elif after < before:
                # Squeezed: conflict creation
                conflict_c += float(u.weight) * (1.0 - (after / before))
    finally:
        # Guarantee state is restored exactly
        state.unplace(task)

    total_score = (
        float(task.weight)
        - lambda_b * blocking_b
        + lambda_r * float(task.weight) * fit_r
        - lambda_c * conflict_c
    )

    return total_score, blocking_b, fit_r, conflict_c
