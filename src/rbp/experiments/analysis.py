"""Paired experimental analysis; only proven reference optima produce gaps."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rbp.experiments.runner import KEY, digest, read_rows

CELL = ["kind", "size", "knob", "algo"]
INSTANCE = ["kind", "size", "knob", "seed"]
MEASURES = ["objective", "coverage", "runtime_s", "gap", "objective_ratio",
            "conflict_density"]


def load_runs(path: str | Path) -> pd.DataFrame:
    """Read typed rows without treating missing or failed objectives as zero."""
    data = pd.DataFrame(read_rows(Path(path)))
    if data.empty:
        raise ValueError(f"No result rows in {path}")
    for col in ("n", "size", "seed", "objective", "scheduled", "violations"):
        data[col] = pd.to_numeric(data[col], errors="raise")
    for col in ("coverage", "runtime_s", "gap", "conflict_density", "selector_score"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    for col in ("optimal", "anomaly"):
        if not data[col].isin(["True", "False"]).all():
            raise ValueError(f"Invalid boolean in {col}")
        data[col] = data[col].eq("True")
    return data


def enrich(data: pd.DataFrame) -> pd.DataFrame:
    """Join paired reference optima and best-observed objectives, by exact instance."""
    data = data.copy()
    if data.duplicated(list(KEY)).any():
        raise ValueError("Duplicate run keys")
    hashes = data.loc[data.instance_hash.ne("")].groupby(INSTANCE).instance_hash.nunique()
    if (hashes > 1).any():
        raise ValueError("Algorithms evaluated different instances in the same cell")
    data["usable"] = (
        data.status.isin(["OK", "TIMEOUT"])
        & data.violations.eq(0) & ~data.anomaly
        & ~data.solver_status.eq("UNKNOWN")
    )
    reference = data.loc[data.usable & (
        (data.algo.eq("ILP-EXACT") & data.solver_status.eq("OPTIMAL") & data.optimal)
        | (data.algo.eq("WIS-DP") & data.kind.eq("simplified") & data.optimal)
    )]
    if (reference.groupby(INSTANCE).objective.nunique() > 1).any():
        raise ValueError("Exact references disagree")
    optimum = reference.groupby(INSTANCE).objective.max().rename("reference_optimum")
    best = data.loc[data.usable].groupby(INSTANCE).objective.max().rename("best_observed")
    data = data.drop(columns=["reference_optimum", "best_observed"], errors="ignore")
    data = data.join(optimum, on=INSTANCE).join(best, on=INSTANCE)
    # Recompute rather than trusting the per-solver gap column.
    data["gap"] = np.nan
    valid_gap = data.usable & data.reference_optimum.gt(0)
    data.loc[valid_gap, "gap"] = (
        1 - data.loc[valid_gap, "objective"] / data.loc[valid_gap, "reference_optimum"]
    )
    data["anomaly"] |= data.gap.lt(-1e-9)
    data["objective_ratio"] = np.nan
    ratio_ok = data.usable & data.best_observed.gt(0)
    data.loc[ratio_ok, "objective_ratio"] = (
        data.loc[ratio_ok, "objective"] / data.loc[ratio_ok, "best_observed"]
    )
    return data


def aggregate(data: pd.DataFrame) -> pd.DataFrame:
    """One cell per kind/size/knob/algorithm, sample std (ddof=1) and counts."""
    records = []
    for keys, group in data.groupby(CELL, sort=True):
        valid = group.loc[group.usable & ~group.anomaly]
        row = dict(zip(CELL, keys))
        row.update(
            n_total=len(group), n_valid=len(valid), n_gap=int(valid.gap.count()),
            n_error=int(group.status.eq("ERROR").sum()),
            n_timeout=int(group.status.eq("TIMEOUT").sum()),
            n_skipped=int(group.status.eq("SKIPPED_LIMIT").sum()),
            violations=int(group.violations.sum()), anomalies=int(group.anomaly.sum()),
            actual_n_min=int(group.n.min()), actual_n_max=int(group.n.max()),
        )
        ilp = group.loc[group.chosen_algorithm.eq("ILP-EXACT")
                        & ~group.status.eq("SKIPPED_LIMIT")]
        n_optimal = int((ilp.solver_status.eq("OPTIMAL") & ilp.optimal
                         & ilp.violations.eq(0)).sum())
        row.update(ilp_attempted=len(ilp), ilp_optimal=n_optimal,
                   ilp_optimal_share=n_optimal / len(ilp) if len(ilp) else np.nan)
        for measure in MEASURES:
            values = valid[measure].dropna()
            row[f"{measure}_count"] = len(values)
            row[f"{measure}_mean"] = values.mean()
            row[f"{measure}_std"] = values.std(ddof=1)
        records.append(row)
    return pd.DataFrame(records)


def paired_differences(data: pd.DataFrame) -> pd.DataFrame:
    """Pair CA and naive on kind, requested size, knob and seed."""
    valid = data.loc[data.usable & ~data.anomaly]
    paired = valid.loc[valid.algo.eq("CA-GREEDY"), INSTANCE + ["objective"]].merge(
        valid.loc[valid.algo.eq("NAIVE-GREEDY"), INSTANCE + ["objective"]],
        on=INSTANCE, suffixes=("_ca", "_naive"), validate="one_to_one",
    )
    paired["difference"] = paired.objective_ca - paired.objective_naive
    records = []
    for keys, group in paired.groupby(INSTANCE[:-1], sort=True):
        values = group.difference
        records.append(dict(zip(INSTANCE[:-1], keys)) | {
            "pairs": len(values), "difference_mean": values.mean(),
            "difference_std": values.std(ddof=1), "wins": int(values.gt(0).sum()),
            "ties": int(values.eq(0).sum()), "losses": int(values.lt(0).sum()),
        })
    return pd.DataFrame(records, columns=INSTANCE[:-1] + [
        "pairs", "difference_mean", "difference_std", "wins", "ties", "losses",
    ])


def seed_halves(data: pd.DataFrame) -> pd.DataFrame:
    seeds = sorted(data.seed.unique())
    first = set(seeds[:len(seeds) // 2])
    parts = []
    for half, mask in [("first", data.seed.isin(first)), ("second", ~data.seed.isin(first))]:
        if not mask.any():
            continue
        table = aggregate(data.loc[mask])
        table.insert(0, "half", half)
        parts.append(table)
    return pd.concat(parts, ignore_index=True)


def fit_slope(n, runtimes) -> float:
    x, y = np.asarray(n, dtype=float), np.asarray(runtimes, dtype=float)
    good = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    if len(np.unique(x[good])) < 2:
        return float("nan")
    return float(np.polyfit(np.log(x[good]), np.log(y[good]), 1)[0])


def runtime_slopes(data: pd.DataFrame) -> pd.DataFrame:
    # Budget-censored CP-SAT runtimes must not masquerade as scalability evidence.
    valid = data.loc[data.usable & ~data.anomaly & (
        ~data.chosen_algorithm.eq("ILP-EXACT") | data.solver_status.eq("OPTIMAL")
    )]
    rows = []
    for (kind, algo), group in valid.groupby(["kind", "algo"]):
        means = group.groupby("size").runtime_s.mean()
        rows.append({"kind": kind, "algo": algo, "sizes": len(means), "runs": len(group),
                     "slope": fit_slope(means.index, means.values)})
    return pd.DataFrame(rows)


def selector_shares(data: pd.DataFrame) -> pd.DataFrame:
    selected = data.loc[data.algo.eq("SELECTOR") & data.chosen_algorithm.ne("")]
    columns = ["kind", "size", "knob", "chosen_algorithm"]
    counts = selected.groupby(columns).size().rename("count").reset_index()
    counts["total"] = counts.groupby(columns[:-1])["count"].transform("sum")
    counts["share"] = counts["count"] / counts["total"]
    return counts


def compare_runs(first: pd.DataFrame, second: pd.DataFrame) -> dict:
    """Require identical full key sets and compare objectives, inputs and solver outcomes."""
    if first.duplicated(list(KEY)).any() or second.duplicated(list(KEY)).any():
        raise ValueError("Duplicate keys in reproducibility comparison")
    columns = ["objective", "instance_hash", "status", "solver_status", "optimal",
               "violations", "chosen_algorithm", "scheduled", "coverage"]
    left = first.set_index(list(KEY)).sort_index()[columns]
    right = second.set_index(list(KEY)).sort_index()[columns]
    same_keys = left.index.equals(right.index)
    mismatches = int((left.ne(right)).any(axis=1).sum()) if same_keys else None
    objectives_equal = same_keys and left.objective.equals(right.objective)
    return {
        "rows_first": len(left), "rows_second": len(right), "same_keys": same_keys,
        "objectives_identical": objectives_equal, "mismatched_rows": mismatches,
        "passed": same_keys and mismatches == 0,
        "objective_hash_first": digest(left.objective.to_list()),
        "objective_hash_second": digest(right.objective.to_list()),
    }


def audit_grid(path: Path, data: pd.DataFrame, allow_incomplete: bool = False) -> dict:
    """Reject incomplete grids rather than publishing partial experiments as complete."""
    meta = json.loads((path.parent / "meta.json").read_text())
    cfg = meta["config"]
    expected = {
        (s["kind"], a, n, json.dumps(k, sort_keys=True, separators=(",", ":")), seed)
        for s in cfg["studies"] for a in s["algorithms"] for n in cfg["sizes"]
        for k in s["knobs"] for seed in cfg["seeds"]
    }
    actual = set(data[list(KEY)].itertuples(index=False, name=None))
    if actual - expected or (actual != expected and not allow_incomplete):
        raise ValueError(f"Incomplete grid {path}: missing={len(expected - actual)}, "
                         f"unexpected={len(actual - expected)}")
    return {
        "rows": len(data), "expected_rows": len(expected),
        "complete": actual == expected, "missing_rows": len(expected - actual),
        "errors": int(data.status.eq("ERROR").sum()),
        "violations": int(data.violations.sum()), "anomalies": int(data.anomaly.sum()),
        "timeouts": int(data.status.eq("TIMEOUT").sum()),
        "skipped": int(data.status.eq("SKIPPED_LIMIT").sum()),
        "proven_gap_rows": int(data.gap.count()),
        "ilp_attempts": int((data.algo.eq("ILP-EXACT")
                             & ~data.status.eq("SKIPPED_LIMIT")).sum()),
        "ilp_optimal": int((data.algo.eq("ILP-EXACT") & data.optimal
                            & data.solver_status.eq("OPTIMAL")).sum()),
        "config_hash": meta["config_hash"], "source_hash": meta["source_hash"],
        "git_hash": meta["git_hash"], "git_dirty": meta["git_dirty"],
        "python_version": meta["python_version"], "ortools_version": meta["ortools_version"],
    }


def make_figures(tables: dict[str, pd.DataFrame], output: Path) -> None:
    """Every plotted point's count is retained in the corresponding summary CSV."""
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.2})

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(output / name, dpi=140)
        plt.close(fig)

    e1 = tables["E1"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, kind in zip(axes, ["extended", "simplified"]):
        for algo, group in e1.loc[e1.kind.eq(kind)].groupby("algo"):
            group = group.sort_values("size")
            ax.errorbar(group["size"], group.gap_mean, yerr=group.gap_std.fillna(0),
                        marker="o", capsize=2, label=algo)
        ax.set(title=f"{kind.title()}: proven gaps only", xlabel="Requested tasks",
               ylabel="(Optimum − objective) / optimum")
        ax.legend(fontsize=7)
    save(fig, "gap_vs_size.png")

    e2 = tables["E2"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, kind in zip(axes, ["extended", "simplified"]):
        for algo, group in e2.loc[e2.kind.eq(kind)].groupby("algo"):
            group = group.loc[group.runtime_s_count.gt(0)].sort_values("size")
            slope = fit_slope(group["size"], group.runtime_s_mean)
            # ILP includes censored incumbents here; do not fit those points.
            label = algo if algo == "ILP-EXACT" else f"{algo} (slope {slope:.2f})"
            ax.loglog(group["size"], group.runtime_s_mean, "o-", label=label)
        ax.set(title=f"{kind.title()}: runtime", xlabel="Requested tasks",
               ylabel="Mean solver runtime (seconds)")
        ax.legend(fontsize=7)
    save(fig, "runtime_vs_n.png")

    e3 = tables["E3"].copy()
    e3["assets"] = e3.knob.map(lambda k: json.loads(k)["assets_per_corridor"])
    fig, ax = plt.subplots(figsize=(7, 4))
    for algo, group in e3.groupby("algo"):
        group = group.sort_values("conflict_density_mean")
        ax.errorbar(group.conflict_density_mean, group.objective_ratio_mean,
                    yerr=group.objective_ratio_std.fillna(0), marker="o", capsize=2, label=algo)
    ax.set(xlabel="Measured same-asset window conflict density (mean)",
           ylabel="Objective / best observed objective",
           title="E3: relative quality (not an optimality gap)")
    ax.legend(fontsize=8)
    save(fig, "objective_ratio_vs_density.png")

    shares = tables["selector"]
    shares = shares.loc[shares.kind.eq("extended")].copy()
    shares["assets"] = shares.knob.map(lambda k: json.loads(k)["assets_per_corridor"])
    counts = shares.groupby(["assets", "chosen_algorithm"])["count"].sum().unstack(fill_value=0)
    pivot = counts.div(counts.sum(axis=1), axis=0)
    pivot = pivot.reindex(sorted(pivot.index, reverse=True))
    fig, ax = plt.subplots(figsize=(7, 4))
    if not pivot.empty:
        pivot.plot.bar(stacked=True, ax=ax, rot=0)
    ax.set(xlabel="Assets per corridor (more to fewer)", ylabel="Decision share",
           title="E3: selector routing by asset-count level", ylim=(0, 1.05))
    save(fig, "selector_share_vs_density.png")


def make_report(results_root: str | Path = "results", output: str | Path = "reports",
                repeat_root: str | Path | None = None,
                allow_partial_repeat: bool = False) -> dict:
    """Write compact tables, figures and an evidence-linked report for complete grids."""
    root, output = Path(results_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    tables, audits, repetitions = {}, {}, {}
    for name in ("E1", "E2", "E3"):
        path = root / name / "runs.csv"
        data = enrich(load_runs(path))
        audits[name] = audit_grid(path, data)
        if audits[name]["errors"] or audits[name]["violations"] or audits[name]["anomalies"]:
            raise ValueError(f"{name} has errors, violations or anomalies: {audits[name]}")
        tables[name] = aggregate(data)
        tables[name].to_csv(output / f"summary_{name}.csv", index=False)
        paired_differences(data).to_csv(output / f"paired_{name}.csv", index=False)
        seed_halves(data).to_csv(output / f"seed_halves_{name}.csv", index=False)
        if name == "E2":
            runtime_slopes(data).to_csv(output / "runtime_slopes.csv", index=False)
        if name == "E3":
            tables["selector"] = selector_shares(data)
            tables["selector"].to_csv(output / "selector_shares_E3.csv", index=False)
        if repeat_root is not None:
            repeat_path = Path(repeat_root) / name / "runs.csv"
            if not repeat_path.exists() and allow_partial_repeat:
                repetitions[name] = {
                    "complete": False, "status": "NOT_RUN", "passed": False,
                    "rows_first": len(data), "rows_second": 0, "rows_compared": 0,
                }
                continue
            repeated = enrich(load_runs(repeat_path))
            repeat_audit = audit_grid(repeat_path, repeated, allow_partial_repeat)
            if any(repeat_audit[k] for k in ("errors", "violations", "anomalies")):
                raise ValueError(f"Repeat {name} failed validation")
            for key in ("config_hash", "source_hash", "python_version", "ortools_version"):
                if repeat_audit[key] != audits[name][key]:
                    raise ValueError(f"Repeat {name} changed {key}")
            compared = data
            if not repeat_audit["complete"]:
                compared = data.merge(repeated[list(KEY)], on=list(KEY), validate="one_to_one")
            repetitions[name] = compare_runs(compared, repeated)
            repetitions[name].update(
                complete=repeat_audit["complete"], rows_first=len(data),
                rows_compared=len(compared),
                status="COMPLETE" if repeat_audit["complete"] else "PARTIAL",
            )
            repetitions[name]["repeat_git_hash"] = repeat_audit["git_hash"]
            repetitions[name]["repeat_git_dirty"] = repeat_audit["git_dirty"]
            if not repetitions[name]["passed"]:
                raise ValueError(f"Reproducibility failed: {name}: {repetitions[name]}")
    make_figures(tables, output / "figures")
    evidence = {"experiments": audits, "reproducibility": repetitions}
    (output / "phase9_audit.json").write_text(json.dumps(evidence, indent=2) + "\n")
    _write_report(output, tables, evidence)
    return evidence


def _write_report(output: Path, tables: dict, evidence: dict) -> None:
    lines = [
        "# Phase 9: measured scheduling experiments", "",
        "All solver calls ran serially. Runtime excludes generation, validation and I/O. "
        "Tables report sample standard deviations (ddof=1); single observations have no "
        "estimated standard deviation. Missing/failed/censored-without-incumbent values "
        "are not treated as zero. Error bars show one standard deviation, "
        "not confidence intervals.",
        "", "## Completeness and correctness", "",
        "| Study | Rows | Errors | Violations | Anomalies | ILP OPTIMAL / attempted | "
        "Timeouts (including selector) | Skipped ILP | Rows with proven gaps |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, audit in evidence["experiments"].items():
        lines.append(f"| {name} | {audit['rows']} | {audit['errors']} | {audit['violations']} | "
                     f"{audit['anomalies']} | {audit['ilp_optimal']} / {audit['ilp_attempts']} | "
                     f"{audit['timeouts']} | {audit['skipped']} | {audit['proven_gap_rows']} |")
    lines += [
        "", "Exact gaps use only same-instance ILP OPTIMAL or simplified WIS-DP references. "
        "A FEASIBLE incumbent is never an optimum. When a reference is unproven the gap is "
        "missing, even if the incumbent happens to be best. Relative quality is objective "
        "divided by the best observed valid objective for the same instance; it is not a gap.",
        "", "CP-SAT uses one worker, random seed 0, a 30-second wall cap and one unit of "
        "deterministic search. E2 stops ILP for each seed/kind after an unproven result. "
        "These are budget-specific results, not claims about unrestricted solver performance. "
        "CA-GREEDY uses a five-task lookahead.",
        "", "## E1: solution quality", "",
        "![Proven optimality gaps](figures/gap_vs_size.png)", "",
        "Every point and its sample size is in [summary_E1.csv](summary_E1.csv): "
        "`gap_count` counts proven gaps; `n_total` is the full cell size. "
        "Extended and simplified instances are analyzed separately.", "",
        "## Paired CA-minus-naive differences", "",
        "| Study | Pairs | CA wins | Ties | CA losses |", "|---|---:|---:|---:|---:|",
    ]
    for name in ("E1", "E2", "E3"):
        paired = pd.read_csv(output / f"paired_{name}.csv")
        lines.append(f"| [{name}](paired_{name}.csv) | {paired.pairs.sum()} | "
                     f"{paired.wins.sum()} | {paired.ties.sum()} | {paired.losses.sum()} |")
    lines += [
        "", "The linked paired tables give mean and sample standard deviation of the "
        "within-instance difference for each size/knob/kind. Losses are retained.",
        "", "## E2: scalability", "", "![Runtime](figures/runtime_vs_n.png)", "",
        "[summary_E2.csv](summary_E2.csv) provides `runtime_s_count` behind every point. "
        "[runtime_slopes.csv](runtime_slopes.csv) fits log(mean runtime) against log(n); "
        "ILP slopes use only OPTIMAL observations and are omitted when fewer than two "
        "sizes remain. The plotted ILP incumbent times may be budget-censored.", "",
    ]
    slopes = pd.read_csv(output / "runtime_slopes.csv")
    wis = slopes.loc[slopes.algo.eq("WIS-DP")]
    if not wis.empty:
        slope = wis.iloc[0].slope
        lines.append(f"The measured simplified WIS-DP slope is **{slope:.3f}**. "
                     "This is a finite-range timing observation; it does not prove asymptotic "
                     "complexity. The implementation's expected bound is O(n log n).")
    lines += [
        "", "## E3: asset-count / conflict study", "",
        "![Relative objective](figures/objective_ratio_vs_density.png)", "",
        "![Selector decisions](figures/selector_share_vs_density.png)", "",
        "[summary_E3.csv](summary_E3.csv) contains objective-ratio counts, actual measured "
        "density, true-gap counts and means. [selector_shares_E3.csv](selector_shares_E3.csv) "
        "contains every decision count and denominator. Assets per corridor are 8, 6, 4, 3, 2; "
        "the x-coordinate in the ratio figure is measured conflict density, not an assumed "
        "monotonic density. Changing asset count also changes generated task assignments "
        "and priorities, so this is a controlled generator-knob study, "
        "not isolated causal evidence.",
        "", "## Reproducibility and seed-half consistency", "",
    ]
    for name in ("E1", "E2", "E3"):
        check = evidence["reproducibility"].get(name)
        if not check or not check.get("rows_compared", 0):
            lines.append(f"- {name}: not repeated; no reproducibility claim for this study.")
        else:
            scope = "complete" if check["complete"] else "PARTIAL"
            lines.append(
                f"- {name}: {scope} repeat, {check['rows_compared']}/{check['rows_first']} "
                "rows compared; objectives, instance hashes, statuses, chosen algorithms, "
                "coverage and schedule counts identical."
            )
    if any(not c.get("complete", False) for c in evidence["reproducibility"].values()):
        lines += ["", "**Verification scope:** The user requested a shorter verification run. "
                  "Remaining repeat runs were stopped; primary E1/E2/E3 grids are complete. "
                  "Partial repeat agreement is not evidence of a full-study repeat."]
    lines += [
        "", "Seed halves split the sorted seeds at the midpoint (15/15 for E1 and E3, "
        "2/3 for E2). [E1 halves](seed_halves_E1.csv), [E2 halves](seed_halves_E2.csv), "
        "and [E3 halves](seed_halves_E3.csv) retain counts, means and standard deviations. "
        "The table below compares CA-minus-naive mean objective differences in the two "
        "halves by cell; sign agreement is descriptive, not a significance test.", "",
        "| Study | Comparable cells | Same sign | Largest absolute half difference |",
        "|---|---:|---:|---:|",
    ]
    for name in ("E1", "E2", "E3"):
        halves = pd.read_csv(output / f"seed_halves_{name}.csv")
        pivot = halves.pivot(index=["kind", "size", "knob"],
                             columns=["half", "algo"], values="objective_mean")
        d1 = pivot[("first", "CA-GREEDY")] - pivot[("first", "NAIVE-GREEDY")]
        d2 = pivot[("second", "CA-GREEDY")] - pivot[("second", "NAIVE-GREEDY")]
        good = d1.notna() & d2.notna()
        agree = int((np.sign(d1[good]) == np.sign(d2[good])).sum())
        lines.append(f"| {name} | {int(good.sum())} | {agree} | "
                     f"{(d1[good] - d2[good]).abs().max():.3f} |")
    lines += [
        "", "## Provenance and limitations", "",
        "[phase9_audit.json](phase9_audit.json) records source/config fingerprints, commit "
        "identifiers, dependency versions, objective hashes and completion checks. Full resolved "
        "configs, per-run schedules and UTC timestamps are in ignored raw results. "
        "Commands and resumption semantics are in [EXPERIMENTS.md](../docs/EXPERIMENTS.md).", "",
        "These synthetic results do not establish operational railway performance. "
        "Requested size and actual generated count are both retained because generation may "
        "drop individually infeasible tasks. Timing reflects this machine and these workloads; "
        "large-size heuristic curves need not expose their worst-case behavior. "
        "A selector that always chooses one solver on a study has not demonstrated adaptive "
        "benefit there. The E2 seed count is small and its halves are unequal.", "",
    ]
    (output / "phase9_analysis.md").write_text("\n".join(lines), encoding="utf-8")
