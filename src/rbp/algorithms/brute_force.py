"""Exhaustive brute-force oracle for small simplified instances (Milestone 4.2).

Provides an independent ground-truth optimum for correctness verification.
Shares NO code with WIS-DP or algorithm constraints.
"""

from __future__ import annotations

import time
from typing import Any

from rbp.algorithms.base import AlgoResult, NotSimplifiedError
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.models.simplified import is_simplified


def solve_brute_force(instance: Instance, max_n: int = 20) -> AlgoResult:
    """Find the exact optimal schedule by exhaustive search over all compatible subsets.

    Parameters:
      instance: A validated Instance satisfying is_simplified(instance).
      max_n: Maximum allowed number of tasks (default 20). Enforces 2^n safety.

    Returns:
      AlgoResult containing optimal Schedule and objective.

    Raises:
      NotSimplifiedError: If instance is not a simplified instance (Decision D8).
      ValueError: If len(instance.tasks) > max_n.
    """
    if not is_simplified(instance):
        raise NotSimplifiedError(
            "solve_brute_force requires a simplified instance (Decision D8)."
        )

    n = len(instance.tasks)
    if n > max_n:
        raise ValueError(
            f"Instance size n={n} exceeds brute-force limit max_n={max_n}."
        )

    t0 = time.perf_counter()

    if n == 0:
        elapsed = time.perf_counter() - t0
        return AlgoResult(
            name="brute_force",
            schedule=Schedule(starts={}),
            objective=0,
            meta={"runtime_s": elapsed, "n_tasks": 0, "subsets_explored": 1},
        )

    tasks = list(instance.tasks)
    weights = [t.weight for t in tasks]

    # Precompute pairwise conflict bitmask using inline overlap check:
    # a.window_start < b.window_end and b.window_start < a.window_end
    conflict_mask = [0] * n
    for i in range(n):
        for j in range(n):
            if i != j:
                ti = tasks[i]
                tj = tasks[j]
                if ti.window_start < tj.window_end and tj.window_start < ti.window_end:
                    conflict_mask[i] |= (1 << j)

    # Suffix sums of remaining weights for upper-bound pruning
    suffix_weights = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_weights[i] = suffix_weights[i + 1] + weights[i]

    best_weight = -1
    best_mask = 0
    subsets_explored = 0

    def search(idx: int, current_mask: int, current_weight: int) -> None:
        nonlocal best_weight, best_mask, subsets_explored
        subsets_explored += 1

        if idx == n:
            if current_weight > best_weight:
                best_weight = current_weight
                best_mask = current_mask
            return

        # Prune if even taking all remaining tasks cannot beat best_weight
        if current_weight + suffix_weights[idx] <= best_weight:
            return

        # Branch 1: Include task idx (if compatible with currently selected subset)
        if (conflict_mask[idx] & current_mask) == 0:
            search(idx + 1, current_mask | (1 << idx), current_weight + weights[idx])

        # Branch 2: Exclude task idx
        search(idx + 1, current_mask, current_weight)

    search(0, 0, 0)

    # Build Schedule from best_mask
    starts = {
        tasks[i].id: tasks[i].window_start
        for i in range(n)
        if (best_mask & (1 << i))
    }
    elapsed = time.perf_counter() - t0

    meta: dict[str, Any] = {
        "runtime_s": elapsed,
        "n_tasks": n,
        "subsets_explored": subsets_explored,
    }

    return AlgoResult(
        name="brute_force",
        schedule=Schedule(starts=starts),
        objective=best_weight,
        meta=meta,
    )
