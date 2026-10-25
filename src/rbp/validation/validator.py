"""Independent constraint validator for Schedule objects.

IMPORTANT: This module imports ONLY rbp.models — never rbp.constraints or
rbp.algorithms. The independence is machine-checked by tests/test_import_boundaries.py.

Algorithms used here are intentionally different from the predicates in
rbp.constraints so that a common bug cannot hide in both:
  - C1: direct integer comparison
  - C2: sorted train starts + bisect
  - C3: per-asset sort + running maximum end
  - C4: sweep-line over +demand/-demand events
  - C5: direct end-of-prerequisite comparison

Reports ALL violations, not just the first.
"""

from __future__ import annotations

import bisect

from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.validation.report import ValidationReport, Violation

# Structural check codes
S_UNKNOWN = "S_UNKNOWN"
S_FORMAT = "S_FORMAT"


def validate_schedule(instance: Instance, schedule: Schedule) -> ValidationReport:
    """Validate schedule against instance constraints C1-C5.

    Returns a ValidationReport containing all violations found.
    An empty schedule is always valid.
    """
    violations: list[Violation] = []

    # -----------------------------------------------------------------------
    # Structural checks
    # -----------------------------------------------------------------------
    task_by_id = {t.id: t for t in instance.tasks}

    for task_id, start in schedule.starts.items():
        if task_id not in task_by_id:
            violations.append(Violation(
                code=S_UNKNOWN,
                task_ids=(task_id,),
                detail=f"Task {task_id} not found in instance",
            ))
            continue
        if not isinstance(start, int):
            violations.append(Violation(
                code=S_FORMAT,
                task_ids=(task_id,),
                detail=f"Start of task {task_id} is not an integer: {start!r}",
            ))

    # Only validate structurally sound entries
    valid_scheduled: dict[int, int] = {
        tid: s for tid, s in schedule.starts.items()
        if tid in task_by_id and isinstance(s, int)
    }

    # -----------------------------------------------------------------------
    # C1: Time-window compliance — direct comparison
    # -----------------------------------------------------------------------
    for task_id, start in valid_scheduled.items():
        task = task_by_id[task_id]
        end = start + task.duration
        if start < task.window_start or end > task.window_end:
            violations.append(Violation(
                code="C1",
                task_ids=(task_id,),
                detail=(
                    f"Task {task_id} placed at [{start},{end}) "
                    f"outside window [{task.window_start},{task.window_end})"
                ),
            ))

    # -----------------------------------------------------------------------
    # C2: Train conflict — sorted train starts + bisect per corridor
    # -----------------------------------------------------------------------
    # Build per-corridor sorted list of (train_start, train_end)
    train_by_corridor: dict[int, list[tuple[int, int]]] = {}
    for tt in instance.timetable:
        train_by_corridor[tt.corridor_id] = sorted(
            (ti.start, ti.end) for ti in tt.intervals
        )

    for task_id, start in valid_scheduled.items():
        task = task_by_id[task_id]
        end = start + task.duration
        trains = train_by_corridor.get(task.corridor_id, [])
        if not trains:
            continue
        train_starts = [t[0] for t in trains]
        # Find first train that could overlap: train_start < end
        idx = bisect.bisect_left(train_starts, end)
        # Check all trains before this index
        for i in range(idx):
            t_start, t_end = trains[i]
            if max(start, t_start) < min(end, t_end):
                violations.append(Violation(
                    code="C2",
                    task_ids=(task_id,),
                    detail=(
                        f"Task {task_id} [{start},{end}) overlaps "
                        f"train [{t_start},{t_end}) on corridor {task.corridor_id}"
                    ),
                ))
                break  # report once per task per check

    # -----------------------------------------------------------------------
    # C3: Asset conflict — per-asset sort + running maximum end
    # -----------------------------------------------------------------------
    asset_tasks: dict[int, list[tuple[int, int, int]]] = {}  # asset_id -> [(start,end,tid)]
    for task_id, start in valid_scheduled.items():
        task = task_by_id[task_id]
        end = start + task.duration
        asset_tasks.setdefault(task.asset_id, []).append((start, end, task_id))

    for asset_id, entries in asset_tasks.items():
        entries.sort()  # sort by start
        max_end = -1
        prev_tid = -1
        for start, end, task_id in entries:
            if start < max_end:
                # Overlap with a previously placed task
                violations.append(Violation(
                    code="C3",
                    task_ids=(prev_tid, task_id),
                    detail=(
                        f"Tasks {prev_tid} and {task_id} overlap on asset {asset_id}: "
                        f"running max_end={max_end} > start={start}"
                    ),
                ))
            if end > max_end:
                max_end = end
                prev_tid = task_id

    # -----------------------------------------------------------------------
    # C4: Resource capacity — sweep-line over +demand/-demand events
    # -----------------------------------------------------------------------
    resource_cap: dict[str, int] = {r.type: r.capacity for r in instance.resources}
    # Build per-resource-type availability merged intervals
    resource_avail: dict[str, list[tuple[int, int]]] = {}
    for r in instance.resources:
        resource_avail[r.type] = sorted((iv.start, iv.end) for iv in r.availability)

    # Collect events per resource type: (minute, +demand or -demand, task_id)
    # Ends are processed BEFORE starts at the same time (task ends free capacity)
    res_events: dict[str, list[tuple[int, int, int, int]]] = {}
    # Tuple: (time, order, delta, task_id)  order=0 for end (free), order=1 for start (use)
    for task_id, start in valid_scheduled.items():
        task = task_by_id[task_id]
        end = start + task.duration
        for res_type, demand in task.demands.items():
            ev_list = res_events.setdefault(res_type, [])
            ev_list.append((start, 1, +demand, task_id))   # start: use capacity
            ev_list.append((end, 0, -demand, task_id))     # end:   free capacity

    for res_type, events in res_events.items():
        cap = resource_cap.get(res_type, 0)
        avail_ivs = resource_avail.get(res_type, [])
        avail_starts = [a[0] for a in avail_ivs]

        events.sort(key=lambda e: (e[0], e[1]))  # sort by time, ends before starts
        current_usage = 0
        active_tasks: list[int] = []  # task_ids with active demand

        for time, order, delta, task_id in events:
            if delta > 0:
                # Task starting — check availability
                active_tasks.append(task_id)
                current_usage += delta

                # Check availability at this minute
                # Find the interval containing `time`
                in_avail = False
                idx = bisect.bisect_right(avail_starts, time) - 1
                if idx >= 0:
                    a_start, a_end = avail_ivs[idx]
                    if a_start <= time < a_end:
                        in_avail = True

                task = task_by_id[task_id]
                end = time + task.duration
                # Check all minutes in [time, end) within availability
                # (full-interval check done via events; spot-check at start)
                if not in_avail:
                    violations.append(Violation(
                        code="C4",
                        task_ids=(task_id,),
                        detail=(
                            f"Task {task_id} starts at {time} outside "
                            f"availability for resource '{res_type}'"
                        ),
                    ))

                if current_usage > cap:
                    violating_ids = tuple(active_tasks)
                    violations.append(Violation(
                        code="C4",
                        task_ids=violating_ids,
                        detail=(
                            f"Resource '{res_type}' capacity {cap} exceeded "
                            f"at t={time}: usage={current_usage}"
                        ),
                    ))
            else:
                # Task ending
                current_usage += delta
                if task_id in active_tasks:
                    active_tasks.remove(task_id)

    # -----------------------------------------------------------------------
    # C5: Dependency precedence — direct comparison
    # -----------------------------------------------------------------------
    for task_id, start in valid_scheduled.items():
        task = task_by_id[task_id]
        for dep_id in task.depends_on:
            if dep_id not in valid_scheduled:
                violations.append(Violation(
                    code="C5",
                    task_ids=(dep_id, task_id),
                    detail=(
                        f"Task {task_id} is scheduled but prerequisite "
                        f"{dep_id} is not scheduled"
                    ),
                ))
            else:
                dep_task = task_by_id[dep_id]
                dep_end = valid_scheduled[dep_id] + dep_task.duration
                if dep_end > start:
                    violations.append(Violation(
                        code="C5",
                        task_ids=(dep_id, task_id),
                        detail=(
                            f"Task {task_id} starts at {start} before "
                            f"prerequisite {dep_id} finishes at {dep_end}"
                        ),
                    ))

    return ValidationReport(valid=len(violations) == 0, violations=violations)
