"""ILP-EXACT Reference Baseline using OR-Tools CP-SAT (Milestone 6.1).

Exact solver for the maintenance block scheduling problem.
Models C1 and C2 directly into variable domains and enforces C3 (NoOverlap),
C4 (Cumulative), and C5 (Implication and precedence).
"""

from __future__ import annotations

import time
from typing import Any

from ortools.sat.python import cp_model

from rbp.algorithms.base import AlgoResult
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.models.task import Task


def _compute_valid_start_intervals(
    instance: Instance,
    task: Task,
    corridor_trains: list[tuple[int, int]],
    avail_ok: dict[str, list[bool]],
) -> list[list[int]]:
    """Compute contiguous start minute intervals satisfying C1, C2, and availability."""
    latest_start = task.window_end - task.duration
    if task.window_start > latest_start:
        return []

    valid_minutes: list[int] = []
    duration = task.duration

    for s in range(task.window_start, latest_start + 1):
        end = s + duration

        # C2: Train interval overlap
        c2_conflict = False
        for tr_s, tr_e in corridor_trains:
            if max(s, tr_s) < min(end, tr_e):
                c2_conflict = True
                break
        if c2_conflict:
            continue

        # Resource availability check
        avail_conflict = False
        for res_type, demand in task.demands.items():
            if demand <= 0:
                continue
            res_avail = avail_ok.get(res_type)
            if res_avail is None:
                avail_conflict = True
                break
            for m in range(s, end):
                if m >= len(res_avail) or not res_avail[m]:
                    avail_conflict = True
                    break
            if avail_conflict:
                break

        if not avail_conflict:
            valid_minutes.append(s)

    if not valid_minutes:
        return []

    # Group contiguous valid minutes into [start_range, end_range] inclusive
    intervals: list[list[int]] = []
    cur_start = valid_minutes[0]
    cur_end = valid_minutes[0]

    for m in valid_minutes[1:]:
        if m == cur_end + 1:
            cur_end = m
        else:
            intervals.append([cur_start, cur_end])
            cur_start = m
            cur_end = m
    intervals.append([cur_start, cur_end])

    return intervals


def solve_ilp_exact(
    instance: Instance,
    time_limit_s: float | None = None,
    num_workers: int = 1,
    random_seed: int = 42,
    deterministic_time_limit: float | None = None,
) -> AlgoResult:
    """Solve the maintenance block scheduling problem exactly using OR-Tools CP-SAT.

    Parameters:
      instance: Validated Instance.
      time_limit_s: Maximum solver wall-clock time in seconds (None for unlimited).
      num_workers: Number of parallel search workers (default 1 for determinism).
      random_seed: Random seed for CP-SAT search (default 42).
      deterministic_time_limit: Maximum deterministic time budget (for machine-speed independence).

    Returns:
      AlgoResult with final Schedule, total objective, and metadata.

    Raises:
      RuntimeError: If CP-SAT returns INFEASIBLE (empty schedule is always feasible).
    """
    t0 = time.perf_counter()

    if len(instance.tasks) == 0:
        elapsed = time.perf_counter() - t0
        return AlgoResult(
            name="ilp_exact",
            schedule=Schedule(starts={}),
            objective=0,
            meta={
                "status": "OPTIMAL",
                "optimal": True,
                "best_bound": 0.0,
                "runtime_s": elapsed,
                "n_tasks": 0,
                "n_scheduled": 0,
            },
        )

    model = cp_model.CpModel()

    # Precompute corridor train intervals
    corridor_trains: dict[int, list[tuple[int, int]]] = {
        c.id: [] for c in instance.corridors
    }
    for tt in instance.timetable:
        for tr in tt.intervals:
            corridor_trains.setdefault(tt.corridor_id, []).append((tr.start, tr.end))

    # Precompute resource availability boolean arrays
    avail_ok: dict[str, list[bool]] = {}
    for r in instance.resources:
        avail = [False] * instance.horizon
        for iv in r.availability:
            for m in range(max(0, iv.start), min(instance.horizon, iv.end)):
                avail[m] = True
        avail_ok[r.type] = avail

    present_vars: dict[int, cp_model.IntVar] = {}
    start_vars: dict[int, cp_model.IntVar] = {}
    interval_vars: dict[int, cp_model.IntervalVar] = {}

    for task in instance.tasks:
        present = model.NewBoolVar(f"present_{task.id}")
        present_vars[task.id] = present

        intervals = _compute_valid_start_intervals(
            instance=instance,
            task=task,
            corridor_trains=corridor_trains.get(task.corridor_id, []),
            avail_ok=avail_ok,
        )

        if not intervals:
            # Empty domain: task can never be present
            model.Add(present == 0)
            dummy_start = model.NewIntVar(0, instance.horizon, f"dummy_start_{task.id}")
            iv = model.NewOptionalFixedSizeIntervalVar(
                dummy_start, task.duration, present, f"iv_{task.id}"
            )
            start_vars[task.id] = dummy_start
            interval_vars[task.id] = iv
        else:
            start_domain = cp_model.Domain.FromIntervals(intervals)
            start = model.NewIntVarFromDomain(start_domain, f"start_{task.id}")
            iv = model.NewOptionalFixedSizeIntervalVar(
                start, task.duration, present, f"iv_{task.id}"
            )
            start_vars[task.id] = start
            interval_vars[task.id] = iv

    # C3: NoOverlap per asset
    tasks_by_asset: dict[int, list[int]] = {}
    for task in instance.tasks:
        tasks_by_asset.setdefault(task.asset_id, []).append(task.id)

    for asset_id, t_ids in tasks_by_asset.items():
        if len(t_ids) > 1:
            model.AddNoOverlap([interval_vars[tid] for tid in t_ids])

    # C4: Cumulative per resource type
    for resource in instance.resources:
        res_type = resource.type
        demanding_intervals: list[cp_model.IntervalVar] = []
        demands: list[int] = []

        for task in instance.tasks:
            dem = task.demands.get(res_type, 0)
            if dem > 0:
                demanding_intervals.append(interval_vars[task.id])
                demands.append(dem)

        if demanding_intervals:
            model.AddCumulative(demanding_intervals, demands, resource.capacity)

    # C5: Dependency precedence
    task_map = {t.id: t for t in instance.tasks}
    for task in instance.tasks:
        for prereq_id in task.depends_on:
            if prereq_id in task_map:
                prereq_task = task_map[prereq_id]
                # present[task] implies present[prereq]
                model.AddImplication(present_vars[task.id], present_vars[prereq_id])
                # start[task] >= start[prereq] + prereq.duration if present[task]
                model.Add(
                    start_vars[task.id]
                    >= start_vars[prereq_id] + prereq_task.duration
                ).OnlyEnforceIf(present_vars[task.id])

    # Objective: maximize total weight of scheduled tasks
    model.Maximize(
        sum(task.weight * present_vars[task.id] for task in instance.tasks)
    )

    # Solver configuration
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = num_workers
    solver.parameters.random_seed = random_seed
    if time_limit_s is not None:
        solver.parameters.max_time_in_seconds = float(time_limit_s)
    if deterministic_time_limit is not None:
        solver.parameters.max_deterministic_time = float(deterministic_time_limit)

    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    if status == cp_model.INFEASIBLE:
        raise RuntimeError(
            "CP-SAT solver returned INFEASIBLE: "
            "modeling bug detected as the empty schedule is always feasible."
        )
    if status == cp_model.MODEL_INVALID:
        raise RuntimeError(f"CP-SAT model invalid: {solver.ResponseStats()}")

    final_starts: dict[int, int] = {}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for task in instance.tasks:
            if solver.BooleanValue(present_vars[task.id]):
                final_starts[task.id] = int(solver.Value(start_vars[task.id]))

    elapsed = time.perf_counter() - t0
    objective = sum(task_map[tid].weight for tid in final_starts)
    is_optimal = status == cp_model.OPTIMAL

    try:
        best_bound = float(solver.BestObjectiveBound())
    except (ValueError, AttributeError):
        best_bound = float(objective)

    det_time = getattr(solver, "deterministic_time", 0.0)

    meta: dict[str, Any] = {
        "status": status_name,
        "optimal": is_optimal,
        "best_bound": best_bound,
        "runtime_s": elapsed,
        "deterministic_time": det_time,
        "n_tasks": len(instance.tasks),
        "n_scheduled": len(final_starts),
        "num_workers": num_workers,
        "random_seed": random_seed,
    }

    return AlgoResult(
        name="ilp_exact",
        schedule=Schedule(starts=final_starts),
        objective=objective,
        meta=meta,
    )
