"""Deterministic generator for simplified scheduling instances (Milestone 3.1).

Produces single-corridor, single-resource, fixed-interval instances with
controllable overlap level suitable for WIS-DP and correctness benchmarking.
"""

from __future__ import annotations

from typing import Any

from rbp.io.input_checks import validate_instance
from rbp.models import Corridor, Instance, Interval, Resource, Task
from rbp.rng import make_rng


def generate_simplified(
    n: int,
    seed: int,
    horizon: int = 1440,
    overlap_factor: float = 0.5,
    dmin: int = 10,
    dmax: int = 120,
    meta: dict[str, Any] | None = None,
) -> Instance:
    """Generate a simplified instance (Decision D8) with n tasks.

    Parameters:
      n: Number of tasks to generate (must be >= 0).
      seed: Master random seed.
      horizon: Planning horizon in minutes (default 1440).
      overlap_factor: Float in [0.0, 1.0]; higher values compress task span
        yielding higher pairwise overlap.
      dmin: Minimum task duration (minutes).
      dmax: Maximum task duration (minutes).
      meta: Optional extra metadata dictionary.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if dmin <= 0 or dmax < dmin:
        raise ValueError(f"Invalid duration bounds: dmin={dmin}, dmax={dmax}")
    if not (0.0 <= overlap_factor <= 1.0):
        raise ValueError(f"overlap_factor must be in [0.0, 1.0], got {overlap_factor}")
    if horizon < dmax:
        raise ValueError(f"horizon {horizon} must be >= dmax {dmax}")

    rng = make_rng(seed, "tasks")

    # span calculation as specified in Playbook Milestone 3.1:
    # span = max(dmax, round(horizon * (1 - 0.9 * overlap_factor)))
    span = max(dmax, round(horizon * (1.0 - 0.9 * overlap_factor)))

    tasks: list[Task] = []
    for task_id in range(1, n + 1):
        d = rng.randint(dmin, dmax)
        start = rng.randint(0, span - d)
        crit = rng.randint(1, 5)
        urg = rng.randint(1, 5)

        task = Task(
            id=task_id,
            corridor_id=1,
            asset_id=1,
            window_start=start,
            window_end=start + d,
            duration=d,
            criticality=crit,
            urgency=urg,
            demands={"crew": 1},
            depends_on=(),
        )
        tasks.append(task)

    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(
        type="crew",
        capacity=1,
        availability=(Interval(0, horizon),),
    )

    metadata: dict[str, Any] = {
        "generator": "simplified",
        "n": n,
        "seed": seed,
        "overlap_factor": overlap_factor,
        "horizon": horizon,
        "span": span,
    }
    if meta:
        metadata.update(meta)

    instance = Instance(
        tasks=tuple(tasks),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=horizon,
        meta=metadata,
    )

    # Sanity check: must be valid
    errors = validate_instance(instance)
    if errors:
        codes = ", ".join(e.code for e in errors)
        raise ValueError(f"Generated simplified instance failed validation: {codes}")

    return instance
