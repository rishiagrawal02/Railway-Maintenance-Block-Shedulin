"""Deterministic extended synthetic instance generator (Milestone 3.2).

Produces multi-corridor, multi-resource instances with realistic correlations:
  - Urgency with narrower and earlier windows (negative correlation with slack)
  - Criticality correlated with asset impact
  - Traffic level correlated with asset impact
  - Department selects resource type
  - Peak hours with denser trains, night band with sparser trains
  - Precedence dependencies respecting window order
  - Separate RNG streams for stream isolation and determinism
"""

from __future__ import annotations

import logging
from typing import Any

from rbp.io.input_checks import validate_instance
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval
from rbp.rng import make_rng

logger = logging.getLogger(__name__)

DEPARTMENTS = ("track", "signal", "power", "civil")
TRAFFIC_LEVELS = ("low", "medium", "high")

# Headways in minutes
HEADWAYS = {
    "low": 90,
    "medium": 45,
    "high": 25,
}


def generate_extended(
    n: int,
    seed: int,
    n_corridors: int = 2,
    horizon: int = 1440,
    window_slack_factor: float = 1.0,
    assets_per_corridor: int | None = None,
    resource_capacity_scale: float = 1.0,
    corridor_load: float = 1.0,
    meta: dict[str, Any] | None = None,
) -> Instance:
    """Generate an extended synthetic instance with realistic correlations.

    Parameters:
      n: Target number of tasks (must be >= 0).
      seed: Master random seed.
      n_corridors: Number of corridors (must be >= 1).
      horizon: Planning horizon in minutes (default 1440).
      window_slack_factor: Multiplier for task window slack (difficulty knob).
      assets_per_corridor: Fixed number of assets per corridor if specified, else 3-6.
      resource_capacity_scale: Multiplier for resource capacities (difficulty knob).
      corridor_load: Multiplier controlling task duration / horizon packing.
      meta: Optional extra metadata dictionary.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if n_corridors <= 0:
        raise ValueError(f"n_corridors must be > 0, got {n_corridors}")
    if horizon <= 60:
        raise ValueError(f"horizon must be > 60, got {horizon}")

    # Isolated deterministic RNG streams
    rng_corr = make_rng(seed, "corridors")
    rng_res = make_rng(seed, "resources")
    rng_trains = make_rng(seed, "trains")
    rng_tasks = make_rng(seed, "tasks")
    rng_deps = make_rng(seed, "deps")

    # -----------------------------------------------------------------------
    # 1. Corridors & Assets
    # -----------------------------------------------------------------------
    corridors: list[Corridor] = []
    asset_impact: dict[int, int] = {}
    next_asset_id = 1

    for c_idx in range(1, n_corridors + 1):
        traffic = rng_corr.choice(TRAFFIC_LEVELS)
        if assets_per_corridor is not None:
            num_assets = max(1, assets_per_corridor)
        else:
            num_assets = rng_corr.randint(3, 6)

        c_asset_ids: list[int] = []
        for _ in range(num_assets):
            aid = next_asset_id
            next_asset_id += 1
            c_asset_ids.append(aid)

            # Impact correlated with traffic
            if traffic == "low":
                impact = rng_corr.randint(1, 3)
            elif traffic == "medium":
                impact = rng_corr.randint(2, 4)
            else:  # high
                impact = rng_corr.randint(3, 5)
            asset_impact[aid] = impact

        corridors.append(
            Corridor(id=c_idx, traffic_level=traffic, asset_ids=tuple(c_asset_ids))
        )

    # -----------------------------------------------------------------------
    # 2. Resources (one type per department)
    # -----------------------------------------------------------------------
    resources: list[Resource] = []
    res_capacities: dict[str, int] = {}
    for dept in DEPARTMENTS:
        base_cap = rng_res.randint(1, 3)
        scaled_cap = max(1, round(base_cap * resource_capacity_scale))
        res_capacities[dept] = scaled_cap
        # Full horizon availability
        resources.append(
            Resource(
                type=dept,
                capacity=scaled_cap,
                availability=(Interval(0, horizon),),
            )
        )

    # -----------------------------------------------------------------------
    # 3. Timetable per corridor
    # -----------------------------------------------------------------------
    timetables: list[Timetable] = []
    for corridor in corridors:
        base_headway = HEADWAYS[corridor.traffic_level]
        train_intervals: list[TrainInterval] = []

        t = rng_trains.randint(10, 30)
        while t < horizon:
            # Check band
            # Night band 0-300: headway x4
            if t < 300:
                headway = base_headway * 4
            # Peak bands: 420-540 and 1020-1140: headway halved
            elif (420 <= t < 540) or (1020 <= t < 1140):
                headway = max(12, base_headway // 2)
            else:
                headway = base_headway

            train_dur = rng_trains.randint(5, 10)
            t_end = min(horizon, t + train_dur)
            if t < t_end:
                train_intervals.append(TrainInterval(start=t, end=t_end))

            jitter = rng_trains.randint(-2, 2)
            t += max(train_dur + 5, headway + jitter)

        timetables.append(
            Timetable(corridor_id=corridor.id, intervals=tuple(train_intervals))
        )

    train_by_cid = {tt.corridor_id: tt.intervals for tt in timetables}

    # -----------------------------------------------------------------------
    # 4. Tasks Generation with Correlations
    # -----------------------------------------------------------------------
    raw_tasks: list[dict[str, Any]] = []
    dropped_count = 0

    for task_id in range(1, n + 1):
        corridor = rng_tasks.choice(corridors)
        asset_id = rng_tasks.choice(corridor.asset_ids)
        impact = asset_impact[asset_id]

        # Criticality correlated with asset impact
        noise = rng_tasks.choice([-1, 0, 0, 1])
        crit = max(1, min(5, impact + noise))

        # Urgency
        urg = rng_tasks.randint(1, 5)

        # Duration scaled by corridor_load
        base_d = rng_tasks.randint(10, 60)
        duration = max(5, min(120, round(base_d * corridor_load)))

        # Department / Resource
        dept = rng_tasks.choice(DEPARTMENTS)
        cap = res_capacities[dept]
        demand = rng_tasks.randint(1, cap)

        # Slack: higher urgency -> smaller slack (negative correlation)
        # urgency 5: slack multiplier ~ 0.2 - 0.6
        # urgency 1: slack multiplier ~ 2.0 - 4.0
        slack_multiplier = max(0.1, (6 - urg) * 0.7 + rng_tasks.uniform(-0.2, 0.2))
        slack = max(0, round(duration * slack_multiplier * window_slack_factor))
        window_len = duration + slack

        # Urgency also biases window earlier in the horizon
        max_start = max(0, horizon - window_len)
        urg_fraction = (6 - urg) / 5.0  # 1.0 for urg=1, 0.2 for urg=5
        start_bound = max(0, round(max_start * (0.3 + 0.7 * urg_fraction)))
        w_start = rng_tasks.randint(0, start_bound) if start_bound > 0 else 0
        w_end = min(horizon, w_start + window_len)

        # Ensure window length >= duration
        if w_end - w_start < duration:
            w_start = max(0, w_end - duration)
            if w_end - w_start < duration:
                w_end = min(horizon, w_start + duration)

        # -------------------------------------------------------------------
        # Feasibility Sanity: Ensure at least one placeable start time
        # -------------------------------------------------------------------
        trains = train_by_cid.get(corridor.id, ())

        def find_feasible_start(ws: int, we: int, dur: int) -> int | None:
            for s in range(ws, we - dur + 1):
                e = s + dur
                # Check collision with train
                conflict = False
                for ti in trains:
                    if max(s, ti.start) < min(e, ti.end):
                        conflict = True
                        break
                if not conflict:
                    return s
            return None

        feasible_start = find_feasible_start(w_start, w_end, duration)
        tries = 0
        while feasible_start is None and tries < 20:
            tries += 1
            # Shift / expand window toward night band or later gap
            w_start = max(0, w_start - 30)
            w_end = min(horizon, w_end + 60)
            feasible_start = find_feasible_start(w_start, w_end, duration)

        if feasible_start is None:
            dropped_count += 1
            logger.debug(f"Dropped task {task_id}: no train-free window found after 20 tries")
            continue

        raw_tasks.append({
            "id": task_id,
            "corridor_id": corridor.id,
            "asset_id": asset_id,
            "window_start": w_start,
            "window_end": w_end,
            "duration": duration,
            "criticality": crit,
            "urgency": urg,
            "demands": {dept: demand},
            "depends_on": (),
        })

    # Renumber surviving tasks so IDs are 1..len(tasks)
    final_tasks: list[Task] = []
    for new_id, t_dict in enumerate(raw_tasks, start=1):
        t_dict["id"] = new_id

    # -----------------------------------------------------------------------
    # 5. Precedence Dependencies
    # -----------------------------------------------------------------------
    # Sort tasks by window_start so prerequisites always have earlier windows
    raw_tasks.sort(key=lambda t: (t["window_start"], t["id"]))

    for i in range(1, len(raw_tasks)):
        task_i = raw_tasks[i]
        # With probability 0.15, add 1-2 prerequisites
        if rng_deps.random() < 0.15:
            # Candidates must finish with enough room for task_i
            candidates = [
                raw_tasks[j]["id"]
                for j in range(i)
                if (
                    raw_tasks[j]["window_start"]
                    + raw_tasks[j]["duration"]
                    + task_i["duration"]
                    <= task_i["window_end"]
                )
            ]
            if candidates:
                num_deps = min(len(candidates), rng_deps.choice([1, 1, 2]))
                chosen = tuple(sorted(rng_deps.sample(candidates, num_deps)))
                task_i["depends_on"] = chosen

    # Convert to Task objects
    final_tasks = [
        Task(
            id=t["id"],
            corridor_id=t["corridor_id"],
            asset_id=t["asset_id"],
            window_start=t["window_start"],
            window_end=t["window_end"],
            duration=t["duration"],
            criticality=t["criticality"],
            urgency=t["urgency"],
            demands=t["demands"],
            depends_on=t["depends_on"],
        )
        for t in raw_tasks
    ]

    # Re-sort tasks by id
    final_tasks.sort(key=lambda t: t.id)

    metadata: dict[str, Any] = {
        "generator": "extended",
        "requested_n": n,
        "n": len(final_tasks),
        "seed": seed,
        "dropped_tasks": dropped_count,
        "asset_impact": {str(k): v for k, v in asset_impact.items()},
        "window_slack_factor": window_slack_factor,
        "resource_capacity_scale": resource_capacity_scale,
        "corridor_load": corridor_load,
    }
    if meta:
        metadata.update(meta)

    instance = Instance(
        tasks=tuple(final_tasks),
        corridors=tuple(corridors),
        resources=tuple(resources),
        timetable=tuple(timetables),
        horizon=horizon,
        meta=metadata,
    )

    # Sanity check: must be valid
    errors = validate_instance(instance)
    if errors:
        codes = ", ".join(e.code for e in errors)
        raise ValueError(f"Generated extended instance failed validation: {codes}")

    return instance
