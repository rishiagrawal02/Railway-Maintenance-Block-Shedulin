"""Uniform algorithm evaluation runner.

Wraps any algorithm in the ALGORITHMS registry (or custom callable), executes it
with performance timing, validates the resulting schedule against independent
constraints, and returns a standardized RunRecord.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from rbp.algorithms import (
    AlgoResult,
    NotSimplifiedError,
    solve_brute_force,
    solve_ca_greedy,
    solve_ilp_exact,
    solve_naive_greedy,
    solve_wis_dp,
)
from rbp.metrics.metrics import (
    objective_value,
    optimality_gap,
    scheduled_count,
    weighted_coverage,
)
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.models.simplified import is_simplified
from rbp.validation.validator import validate_schedule

ALGORITHMS: dict[str, Callable[..., Any]] = {
    "WIS-DP": solve_wis_dp,
    "NAIVE-GREEDY": solve_naive_greedy,
    "CA-GREEDY": solve_ca_greedy,
    "ILP-EXACT": solve_ilp_exact,
    "BRUTE-FORCE": solve_brute_force,
}


def register_algorithm(name: str, fn: Callable[..., Any]) -> None:
    """Register or override an algorithm in the ALGORITHMS registry."""
    ALGORITHMS[name] = fn


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Standardized record of an algorithm execution run."""

    algo: str
    n: int
    seed: int | None
    objective: int
    coverage: float
    scheduled: int
    runtime_s: float
    violations: int
    status: str
    optimal: bool
    gap: float | None
    anomaly: bool
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.meta, dict):
            object.__setattr__(self, "meta", MappingProxyType(dict(self.meta)))

    def as_dict(self) -> dict[str, Any]:
        """Convert record fields to a standard dictionary."""
        return {
            "algo": self.algo,
            "n": self.n,
            "seed": self.seed,
            "objective": self.objective,
            "coverage": self.coverage,
            "scheduled": self.scheduled,
            "runtime_s": self.runtime_s,
            "violations": self.violations,
            "status": self.status,
            "optimal": self.optimal,
            "gap": self.gap,
            "anomaly": self.anomaly,
            "meta": dict(self.meta),
        }


def _resolve_algo(name_or_fn: str | Callable[..., Any]) -> tuple[str, Callable[..., Any]]:
    """Resolve algorithm name and callable from registry or direct function."""
    if callable(name_or_fn):
        fn = name_or_fn
        name = getattr(name_or_fn, "__name__", "custom")
        return name, fn

    key = str(name_or_fn)
    # Check exact match
    if key in ALGORITHMS:
        return key, ALGORITHMS[key]

    # Check case-insensitive
    for registered_name, fn in ALGORITHMS.items():
        if registered_name.upper() == key.upper():
            return registered_name, fn

    raise ValueError(
        f"Unknown algorithm '{name_or_fn}'. Registered algorithms: {list(ALGORITHMS.keys())}"
    )


def run_algorithm(
    name: str | Callable[..., Any],
    instance: Instance,
    repeats: int = 1,
    optimum: int | float | None = None,
    **kwargs: Any,
) -> RunRecord:
    """Execute an algorithm on an instance and return a standardized RunRecord.

    Catches all exceptions so callers never crash:
      - NotSimplifiedError -> status = "NOT_APPLICABLE"
      - TimeoutError / solver timeout -> status = "TIMEOUT"
      - Any other Exception -> status = "ERROR"

    Optimum logic:
      A genuine optimum comes only from BRUTE-FORCE, WIS-DP on a simplified instance,
      or ILP with status OPTIMAL. A negative gap sets anomaly=True.
    """
    algo_name, algo_fn = _resolve_algo(name)
    n = len(instance.tasks)
    seed = kwargs.pop("seed", None)
    if seed is None and "seed" in instance.meta:
        seed = instance.meta["seed"]

    elapsed_list: list[float] = []
    last_res: Any = None
    runs_to_do = max(1, repeats)

    for i in range(runs_to_do):
        t0 = time.perf_counter()
        try:
            res = algo_fn(instance, **kwargs) if kwargs else algo_fn(instance)
            dt = time.perf_counter() - t0
            elapsed_list.append(dt)
            if i == 0:
                last_res = res
        except NotSimplifiedError as err:
            dt = time.perf_counter() - t0
            return RunRecord(
                algo=algo_name,
                n=n,
                seed=seed,
                objective=0,
                coverage=0.0,
                scheduled=0,
                runtime_s=dt,
                violations=0,
                status="NOT_APPLICABLE",
                optimal=False,
                gap=None,
                anomaly=False,
                meta={
                    "error": f"NotSimplifiedError: {err}",
                    "exception_type": "NotSimplifiedError",
                },
            )
        except TimeoutError as err:
            dt = time.perf_counter() - t0
            return RunRecord(
                algo=algo_name,
                n=n,
                seed=seed,
                objective=0,
                coverage=0.0,
                scheduled=0,
                runtime_s=dt,
                violations=0,
                status="TIMEOUT",
                optimal=False,
                gap=None,
                anomaly=False,
                meta={
                    "error": f"TimeoutError: {err}",
                    "exception_type": "TimeoutError",
                },
            )
        except Exception as err:
            dt = time.perf_counter() - t0
            return RunRecord(
                algo=algo_name,
                n=n,
                seed=seed,
                objective=0,
                coverage=0.0,
                scheduled=0,
                runtime_s=dt,
                violations=0,
                status="ERROR",
                optimal=False,
                gap=None,
                anomaly=False,
                meta={
                    "error": f"{type(err).__name__}: {err}",
                    "exception_type": type(err).__name__,
                },
            )

    runtime_s = statistics.median(elapsed_list) if elapsed_list else 0.0

    # Extract schedule and metadata from output
    algo_meta: dict[str, Any] = {}
    if isinstance(last_res, AlgoResult):
        schedule = last_res.schedule
        algo_meta = dict(last_res.meta)
    elif isinstance(last_res, Schedule):
        schedule = last_res
    elif hasattr(last_res, "schedule"):
        schedule = getattr(last_res, "schedule")
        if hasattr(last_res, "meta"):
            algo_meta = dict(getattr(last_res, "meta"))
    else:
        schedule = Schedule(starts={})

    # Validate output schedule
    report = validate_schedule(instance, schedule)
    violations = len(report.violations)

    obj = objective_value(schedule, instance)
    cov = weighted_coverage(schedule, instance)
    sched_count = scheduled_count(schedule)

    # Determine status
    if algo_meta.get("status") == "TIMEOUT" or algo_meta.get("cp_status") == "TIMEOUT":
        status = "TIMEOUT"
    else:
        status = "OK"

    # Genuine optimum determination
    # Genuine optimum comes only from BRUTE-FORCE, WIS-DP on a simplified instance,
    # or ILP with status OPTIMAL.
    is_genuine_opt = False
    if status == "OK":
        if algo_name in ("WIS-DP", "BRUTE-FORCE") and is_simplified(instance):
            is_genuine_opt = True
        elif algo_name == "ILP-EXACT":
            ilp_status = algo_meta.get("status") or algo_meta.get("cp_status")
            if ilp_status == "OPTIMAL" or algo_meta.get("optimal") is True:
                is_genuine_opt = True

    optimal = is_genuine_opt

    # Compute gap
    gap: float | None = None
    if optimum is not None:
        gap = optimality_gap(obj, optimum)
    elif is_genuine_opt:
        gap = 0.0

    # Negative gap flags an anomaly
    anomaly = bool(gap is not None and gap < -1e-9)

    record_meta = dict(algo_meta)
    record_meta["schedule"] = schedule

    return RunRecord(
        algo=algo_name,
        n=n,
        seed=seed,
        objective=obj,
        coverage=cov,
        scheduled=sched_count,
        runtime_s=runtime_s,
        violations=violations,
        status=status,
        optimal=optimal,
        gap=gap,
        anomaly=anomaly,
        meta=record_meta,
    )
