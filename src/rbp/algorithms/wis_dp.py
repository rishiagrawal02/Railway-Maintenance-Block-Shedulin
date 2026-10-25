"""Weighted Interval Scheduling Dynamic Programming (WIS-DP) exact solver.

Solves the simplified scheduling problem (Decision D8) optimally in O(n log n)
time and O(n) space.
"""

from __future__ import annotations

import bisect
import time
from typing import Any

from rbp.algorithms.base import AlgoResult, NotSimplifiedError
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.models.simplified import is_simplified


def solve_wis_dp(instance: Instance) -> AlgoResult:
    """Solve a simplified instance optimally using Weighted Interval Scheduling DP.

    Parameters:
      instance: A validated Instance satisfying is_simplified(instance).

    Returns:
      AlgoResult containing the optimal Schedule, objective value, and metadata.

    Raises:
      NotSimplifiedError: If instance is not a simplified instance (Decision D8).
    """
    if not is_simplified(instance):
        raise NotSimplifiedError(
            "solve_wis_dp requires a simplified instance (Decision D8). "
            "Instance has multiple corridors/resources, non-fixed windows, trains, or dependencies."
        )

    t0 = time.perf_counter()

    n = len(instance.tasks)
    if n == 0:
        elapsed = time.perf_counter() - t0
        return AlgoResult(
            name="wis_dp",
            schedule=Schedule(starts={}),
            objective=0,
            meta={"runtime_s": elapsed, "n_tasks": 0, "p": [], "opt": [0]},
        )

    # Sort tasks by (end, start, id) for deterministic ordering
    sorted_tasks = sorted(
        instance.tasks,
        key=lambda t: (t.window_end, t.window_start, t.id),
    )

    ends = [t.window_end for t in sorted_tasks]

    # Compute p[i]: 1-indexed predecessor index (0 if none)
    # bisect_right returns count of elements <= start_i
    p: list[int] = [0] * (n + 1)
    for i in range(1, n + 1):
        task = sorted_tasks[i - 1]
        p[i] = bisect.bisect_right(ends, task.window_start)

    # DP table: OPT[i] = maximum weight using a subset of first i tasks
    opt: list[int] = [0] * (n + 1)
    for i in range(1, n + 1):
        task = sorted_tasks[i - 1]
        weight = task.weight
        opt[i] = max(opt[i - 1], weight + opt[p[i]])

    # Reconstruct optimal solution with tie-breaker:
    # Take task i only if strictly better than excluding it
    chosen_tasks = []
    curr = n
    while curr > 0:
        task = sorted_tasks[curr - 1]
        weight = task.weight
        if weight + opt[p[curr]] > opt[curr - 1]:
            chosen_tasks.append(task)
            curr = p[curr]
        else:
            curr = curr - 1

    # In fixed-interval problem, start = window_start
    starts = {t.id: t.window_start for t in chosen_tasks}
    objective = opt[n]
    elapsed = time.perf_counter() - t0

    meta: dict[str, Any] = {
        "runtime_s": elapsed,
        "n_tasks": n,
        "n_scheduled": len(chosen_tasks),
        "p": p[1:],  # 0-indexed view of p for inspection
        "opt": opt,
    }

    return AlgoResult(
        name="wis_dp",
        schedule=Schedule(starts=starts),
        objective=objective,
        meta=meta,
    )
