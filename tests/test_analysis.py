"""Hand-computed statistics, reference filtering and end-to-end report checks."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from rbp.experiments.analysis import (
    aggregate,
    compare_runs,
    enrich,
    fit_slope,
    load_runs,
    make_report,
    paired_differences,
    seed_halves,
)
from rbp.experiments.runner import run_grid


@pytest.fixture
def sample():
    rows = []
    for seed, naive, ca, exact in zip(range(2000, 2003), [10, 20, 30],
                                     [12, 20, 25], [20, 25, 40]):
        for algo, objective in [("NAIVE-GREEDY", naive), ("CA-GREEDY", ca),
                                ("ILP-EXACT", exact)]:
            rows.append({
                "kind": "extended", "size": 20, "n": 20, "knob": "{}", "seed": seed,
                "algo": algo, "objective": objective, "coverage": objective / 100,
                "scheduled": 2, "runtime_s": 1.0, "status": "OK", "violations": 0,
                "optimal": algo == "ILP-EXACT", "anomaly": False,
                "chosen_algorithm": algo, "solver_status": "OPTIMAL" if algo == "ILP-EXACT"
                else "", "instance_hash": str(seed), "conflict_density": 0.2,
            })
    return pd.DataFrame(rows)


def test_aggregation_math_and_schema(sample):
    summary = aggregate(enrich(sample))
    row = summary.loc[summary.algo.eq("NAIVE-GREEDY")].iloc[0]
    assert row.objective_mean == 20
    assert row.objective_std == 10
    assert row.gap_mean == pytest.approx((0.5 + 0.2 + 0.25) / 3)
    assert row.n_gap == 3
    assert row.n_total == row.n_valid == 3
    assert {"kind", "size", "knob", "algo", "n_total", "n_valid", "n_gap",
            "objective_mean", "objective_std", "ilp_optimal_share"} <= set(summary)


def test_paired_wins_ties_losses(sample):
    row = paired_differences(enrich(sample)).iloc[0]
    assert (row.pairs, row.wins, row.ties, row.losses) == (3, 1, 1, 1)
    assert row.difference_mean == -1
    assert row.difference_std == pytest.approx(np.std([2, 0, -5], ddof=1))


def test_feasible_is_not_optimum(sample):
    mask = sample.algo.eq("ILP-EXACT") & sample.seed.eq(2001)
    sample.loc[mask, "solver_status"] = "FEASIBLE"
    sample.loc[mask, "optimal"] = False
    sample.loc[mask, "status"] = "TIMEOUT"
    data = enrich(sample)
    assert data.loc[data.seed.eq(2001), "gap"].isna().all()
    assert data.loc[data.seed.eq(2001), "objective_ratio"].notna().all()
    summary = aggregate(data)
    assert (summary.n_gap == 2).all()
    assert summary.loc[summary.algo.eq("ILP-EXACT"), "ilp_optimal_share"].iloc[0] == 2 / 3


def test_invalid_reference_and_empty_cell(sample):
    sample.loc[sample.algo.eq("ILP-EXACT"), "violations"] = 1
    sample.loc[sample.algo.eq("NAIVE-GREEDY"), "status"] = "ERROR"
    summary = aggregate(enrich(sample))
    empty = summary.loc[summary.algo.eq("NAIVE-GREEDY")].iloc[0]
    assert empty.n_valid == empty.n_gap == 0
    assert np.isnan(empty.objective_mean)
    assert (summary.n_gap == 0).all()


def test_unknown_without_incumbent_is_missing(sample):
    mask = sample.algo.eq("ILP-EXACT")
    sample.loc[mask, "status"] = "TIMEOUT"
    sample.loc[mask, "solver_status"] = "UNKNOWN"
    sample.loc[mask, "optimal"] = False
    assert not enrich(sample).loc[mask, "usable"].any()


def test_slope_n_log_n():
    n = np.array([50, 100, 200, 500, 1000, 2000, 5000])
    assert 0.9 < fit_slope(n, n * np.log(n)) < 1.3
    assert np.isnan(fit_slope([1], [1]))


def test_anomalies_and_instance_pairing(sample):
    bad = sample.copy()
    bad.loc[(bad.seed == 2000) & (bad.algo == "CA-GREEDY"), "objective"] = 21
    assert enrich(bad).anomaly.sum() == 1
    sample.loc[0, "instance_hash"] = "different-instance"
    with pytest.raises(ValueError, match="different instances"):
        enrich(sample)


def test_repeat_and_seed_halves(sample):
    data = enrich(sample)
    assert compare_runs(data, data)["passed"]
    changed = data.copy()
    changed.loc[0, "objective"] += 1
    assert not compare_runs(data, changed)["passed"]
    assert not compare_runs(data, data.iloc[:-1])["passed"]
    halves = seed_halves(data)
    assert set(halves.half) == {"first", "second"}
    assert halves.n_total.sum() == len(data)


def test_full_report_figures_audit_and_repeat(tmp_path):
    cfg = {
        "id": "E1", "sizes": [4, 6], "seeds": [2000, 2001],
        "studies": [{"kind": "extended", "algorithms": [
            "NAIVE-GREEDY", "CA-GREEDY", "ILP-EXACT", "SELECTOR",
        ]}, {"kind": "simplified", "algorithms": [
            "NAIVE-GREEDY", "CA-GREEDY", "WIS-DP",
        ]}],
    }
    root, repeat = tmp_path / "results", tmp_path / "repeat"
    for name in ("E1", "E2", "E3"):
        current = deepcopy(cfg)
        current["id"] = name
        if name == "E3":
            current["studies"] = [current["studies"][0]]
            current["studies"][0]["knobs"] = [{"assets_per_corridor": 2}]
        for directory in (root, repeat):
            run_grid(current, directory)
    output = tmp_path / "reports"
    audit = make_report(root, output, repeat)
    assert all(v["passed"] for v in audit["reproducibility"].values())
    figures = list((output / "figures").glob("*.png"))
    assert len(figures) == 4
    assert all(1000 < p.stat().st_size < 300_000 for p in figures)
    for name in ("E1", "E2", "E3"):
        assert not pd.read_csv(output / f"summary_{name}.csv").empty
    assert (output / "phase9_analysis.md").stat().st_size > 1000
    assert load_runs(root / "E1" / "runs.csv").violations.sum() == 0
    # Shortened verification is explicit, never advertised as a complete repeat.
    repeat_e2 = repeat / "E2" / "runs.csv"
    lines = repeat_e2.read_text().splitlines()
    repeat_e2.write_text("\n".join(lines[:5]) + "\n")
    (repeat / "E3" / "runs.csv").unlink()
    partial = make_report(root, output, repeat, allow_partial_repeat=True)
    assert partial["reproducibility"]["E1"]["complete"]
    assert partial["reproducibility"]["E2"]["status"] == "PARTIAL"
    assert partial["reproducibility"]["E2"]["rows_compared"] == 4
    assert partial["reproducibility"]["E3"]["status"] == "NOT_RUN"
    with pytest.raises(ValueError, match="Incomplete grid"):
        make_report(root, output, repeat)
    # A report must not silently bless an incomplete grid.
    path = root / "E1" / "runs.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="Incomplete grid"):
        make_report(root, output)
