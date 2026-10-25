"""NAIVE-GREEDY baseline heuristic (Milestone 5.1).

Places tasks in descending priority order at their earliest feasible start time.
Uses no look-ahead and no resource reasoning (Decision D12: single-pass dependency rule).
"""

from __future__ import annotations

import time
from typing import Any

from rbp.algorithms.base import AlgoResult
from rbp.algorithms.placement import earliest_feasible_start
from rbp.constraints.state import PlacementState
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule


def solve_naive_greedy(instance: Instance) -> AlgoResult:
    """Solve scheduling problem using NAIVE-GREEDY heuristic.

    Tasks are ordered by:
      1. Higher weight (descending)
      2. Shorter duration (ascending)
      3. Lower ID (ascending, tie-breaker)

    Each task is placed at its earliest feasible start time.
    Under single-pass Decision D12: if any prerequisite task is not yet placed,
    the task is skipped immediately.

    Parameters:
      instance: Validated Instance.

    Returns:
      AlgoResult with final Schedule, total objective, and metadata.
    """
    t0 = time.perf_counter()

    state = PlacementState(instance)

    # Sort tasks by (-weight, duration, id)
    ordered_tasks = sorted(
        instance.tasks,
        key=lambda t: (-t.weight, t.duration, t.id),
    )

    placed_count = 0
    skipped_dep_count = 0
    skipped_infeasible_count = 0

    for task in ordered_tasks:
        # Decision D12: All prerequisites must already be placed in this single pass
        prereqs_ok = all(state.is_placed(dep_id) for dep_id in task.depends_on)
        if not prereqs_ok:
            skipped_dep_count += 1
            continue

        start = earliest_feasible_start(instance, state, task)
        if start is not None:
            state.place(task, start)
            placed_count += 1
        else:
            skipped_infeasible_count += 1

    elapsed = time.perf_counter() - t0
    final_starts = dict(state.placed_starts)
    objective = sum(instance.task(tid).weight for tid in final_starts)

    meta: dict[str, Any] = {
        "runtime_s": elapsed,
        "n_tasks": len(instance.tasks),
        "n_scheduled": placed_count,
        "skipped_dep": skipped_dep_count,
        "skipped_infeasible": skipped_infeasible_count,
    }

    return AlgoResult(
        name="naive_greedy",
        schedule=Schedule(starts=final_starts),
        objective=objective,
        meta=meta,
    )
