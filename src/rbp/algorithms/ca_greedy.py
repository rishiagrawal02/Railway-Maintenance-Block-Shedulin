"""Conflict-Aware Greedy (CA-GREEDY) heuristic (Milestone 5.3).

Schedules tasks using look-ahead reasoning:
  - Base priority: weight w_t
  - Blocking penalty: B (tasks completely blocked)
  - Resource fit bonus: R (utilization of demanded resources)
  - Conflict creation penalty: C (reduction in feasible starts)

Score = w_t - lambda_b * B + lambda_r * w_t * R - lambda_c * C
"""

from __future__ import annotations

import heapq
import time
from typing import Any

from rbp.algorithms.base import AlgoResult
from rbp.algorithms.ca_terms import (
    ca_candidates,
    evaluate_ca_placement,
)
from rbp.constraints.state import PlacementState
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.models.task import Task


def solve_ca_greedy(
    instance: Instance,
    lambda_b: float = 1.0,
    lambda_r: float = 0.5,
    lambda_c: float = 0.5,
    lookahead_k: int = 5,
    allow_skip_negative: bool = False,
) -> AlgoResult:
    """Solve scheduling problem using Conflict-Aware Greedy heuristic.

    Maintains a priority queue of ready tasks (all prerequisites placed).
    Ready tasks are ordered by (-weight, duration, id).

    Parameters:
      instance: Validated Instance.
      lambda_b: Weight for blocking penalty B (default 1.0).
      lambda_r: Weight for resource fit bonus R (default 0.5).
      lambda_c: Weight for conflict creation penalty C (default 0.5).
      lookahead_k: Number of unplaced tasks in lookahead window (default 5).
      allow_skip_negative: If True, skips tasks when max candidate score < 0 (default False).

    Returns:
      AlgoResult with final Schedule, total objective, and metadata.
    """
    t0 = time.perf_counter()

    state = PlacementState(instance)

    # Track tasks by ID
    all_tasks = {t.id: t for t in instance.tasks}
    unplaced_ids = set(all_tasks.keys())

    # Map each task to the set of tasks that depend on it
    dependents_map: dict[int, list[int]] = {tid: [] for tid in all_tasks}
    # Map each task to its remaining unplaced prerequisites
    remaining_prereqs: dict[int, set[int]] = {}

    for task in instance.tasks:
        prereqs = set(task.depends_on)
        remaining_prereqs[task.id] = prereqs
        for p in prereqs:
            if p in dependents_map:
                dependents_map[p].append(task.id)

    # Priority queue of ready tasks
    # Priority tuple: (-weight, duration, id)
    # Stored as (-weight, duration, task_id, task)
    ready_heap: list[tuple[int, int, int, Task]] = []

    for task in instance.tasks:
        if len(remaining_prereqs[task.id]) == 0:
            heapq.heappush(ready_heap, (-task.weight, task.duration, task.id, task))

    placed_count = 0
    skipped_infeasible_count = 0
    skipped_negative_count = 0

    while ready_heap:
        _, _, _, task = heapq.heappop(ready_heap)
        unplaced_ids.remove(task.id)

        # Build lookahead set from top unplaced tasks (excluding current task)
        unplaced_tasks = [all_tasks[tid] for tid in unplaced_ids]
        unplaced_tasks.sort(key=lambda t: (-t.weight, t.duration, t.id))
        lookahead = unplaced_tasks[:lookahead_k]

        # Generate candidates
        candidates = ca_candidates(instance, state, task, lookahead)
        if not candidates:
            skipped_infeasible_count += 1
            continue

        # Evaluate each candidate start
        best_score = float("-inf")
        best_start: int | None = None

        for s in candidates:
            score, _, _, _ = evaluate_ca_placement(
                instance,
                state,
                task,
                s,
                lookahead,
                lambda_b=lambda_b,
                lambda_r=lambda_r,
                lambda_c=lambda_c,
            )
            # Strict inequality preserves earliest start on score ties
            if score > best_score:
                best_score = score
                best_start = s

        if best_start is None:
            skipped_infeasible_count += 1
            continue

        if allow_skip_negative and best_score < 0.0:
            skipped_negative_count += 1
            continue

        # Place the task at best_start
        state.place(task, best_start)
        placed_count += 1

        # Check newly unblocked dependents
        for dep_id in dependents_map[task.id]:
            prereqs = remaining_prereqs[dep_id]
            prereqs.discard(task.id)
            if len(prereqs) == 0 and dep_id in unplaced_ids:
                dep_task = all_tasks[dep_id]
                heapq.heappush(
                    ready_heap,
                    (-dep_task.weight, dep_task.duration, dep_task.id, dep_task),
                )

    elapsed = time.perf_counter() - t0
    final_starts = dict(state.placed_starts)
    objective = sum(instance.task(tid).weight for tid in final_starts)

    meta: dict[str, Any] = {
        "runtime_s": elapsed,
        "n_tasks": len(instance.tasks),
        "n_scheduled": placed_count,
        "skipped_infeasible": skipped_infeasible_count,
        "skipped_negative": skipped_negative_count,
        "lambda_b": lambda_b,
        "lambda_r": lambda_r,
        "lambda_c": lambda_c,
        "lookahead_k": lookahead_k,
        "allow_skip_negative": allow_skip_negative,
    }

    return AlgoResult(
        name="ca_greedy",
        schedule=Schedule(starts=final_starts),
        objective=objective,
        meta=meta,
    )
