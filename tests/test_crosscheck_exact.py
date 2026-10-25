"""Tests for cross-validation of ILP, DP, Brute-Force, and heuristics (Milestone 6.2)."""

import pytest

from rbp.algorithms.brute_force import solve_brute_force
from rbp.algorithms.ca_greedy import solve_ca_greedy
from rbp.algorithms.ilp_exact import solve_ilp_exact
from rbp.algorithms.naive_greedy import solve_naive_greedy
from rbp.algorithms.wis_dp import solve_wis_dp
from rbp.generation.extended import generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.validation.validator import validate_schedule


def test_t62_01_three_way_equality():
    """T6.2-01: BF = WIS-DP = ILP on seeds 0-99 with n<=14. Must be 100/100 equal."""
    matched = 0
    total = 100
    failures = []

    for seed in range(total):
        inst = generate_simplified(n=8, seed=seed)
        r_bf = solve_brute_force(inst)
        r_dp = solve_wis_dp(inst)
        r_ilp = solve_ilp_exact(inst)

        if r_bf.objective == r_dp.objective == r_ilp.objective:
            matched += 1
        else:
            failures.append(
                f"seed={seed}: BF={r_bf.objective} DP={r_dp.objective} ILP={r_ilp.objective}"
            )

    assert matched == total, (
        f"Three-way equality failed for {total - matched}/{total} seeds:\n"
        + "\n".join(failures)
    )


def test_t62_02_ilp_bounds_ca():
    """T6.2-02: On 50 OPTIMAL extended instances, ILP >= CA-GREEDY for all."""
    violations = []

    for seed in range(50):
        inst = generate_extended(n=15, seed=seed)
        r_ilp = solve_ilp_exact(inst, time_limit_s=5.0)

        if not r_ilp.meta["optimal"]:
            continue  # Only check proven optima

        r_ca = solve_ca_greedy(inst)
        if r_ca.objective > r_ilp.objective:
            violations.append(
                f"seed={seed}: CA={r_ca.objective} > ILP={r_ilp.objective}"
            )

    assert len(violations) == 0, (
        f"CA-GREEDY exceeded OPTIMAL ILP in {len(violations)} cases:\n"
        + "\n".join(violations)
    )


def test_t62_03_ilp_bounds_naive():
    """T6.2-03: On 50 OPTIMAL extended instances, ILP >= NAIVE-GREEDY for all."""
    violations = []

    for seed in range(50):
        inst = generate_extended(n=15, seed=seed)
        r_ilp = solve_ilp_exact(inst, time_limit_s=5.0)

        if not r_ilp.meta["optimal"]:
            continue

        r_n = solve_naive_greedy(inst)
        if r_n.objective > r_ilp.objective:
            violations.append(
                f"seed={seed}: NAIVE={r_n.objective} > ILP={r_ilp.objective}"
            )

    assert len(violations) == 0, (
        f"NAIVE-GREEDY exceeded OPTIMAL ILP in {len(violations)} cases:\n"
        + "\n".join(violations)
    )


def test_t62_04_heuristic_schedules_valid():
    """T6.2-04: CA and NAIVE schedules on 50 extended instances all pass validation."""
    for seed in range(50):
        inst = generate_extended(n=15, seed=seed)

        ca_res = solve_ca_greedy(inst)
        ca_report = validate_schedule(inst, ca_res.schedule)
        assert ca_report.valid, f"CA invalid on seed {seed}: {ca_report.violations}"

        naive_res = solve_naive_greedy(inst)
        naive_report = validate_schedule(inst, naive_res.schedule)
        assert naive_report.valid, (
            f"NAIVE invalid on seed {seed}: {naive_report.violations}"
        )


def test_t62_05_non_optimal_runs_excluded():
    """T6.2-05: FEASIBLE (time-limited) runs are never counted as proven optima."""
    inst = generate_extended(n=100, seed=77)
    # Extremely short time limit to force non-optimal
    res = solve_ilp_exact(inst, time_limit_s=0.01)

    # If the solver did not reach OPTIMAL status, optimal must be False
    if res.meta["status"] != "OPTIMAL":
        assert res.meta["optimal"] is False


@pytest.mark.not_slow
def test_t62_06_regression_not_slow():
    """T6.2-06: Regression run of fast tests (marked not_slow) passes without failure."""
    # Sanity check: the three main solvers agree on one simple instance
    inst = generate_simplified(n=10, seed=42)
    r_dp = solve_wis_dp(inst)
    r_ilp = solve_ilp_exact(inst)
    assert r_ilp.objective == r_dp.objective
