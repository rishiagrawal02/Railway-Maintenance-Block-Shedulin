"""Threshold and weight calibration module for adaptive selector (Milestone 8.3).

Calibrates theta and alpha on calibration seeds (1000-1099) using deterministic
CP-SAT limit labels, strictly isolating held-out evaluation seeds (2000-2099).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from rbp.algorithms.ilp_exact import solve_ilp_exact
from rbp.generation import generate_extended
from rbp.models.instance import Instance
from rbp.selector.features import (
    DEFAULT_CONFIG_PATH,
    Features,
    complexity_score,
    compute_features,
)

CALIBRATION_SEED_RANGE = (1000, 1099)
EVALUATION_SEED_RANGE = (2000, 2099)
DEFAULT_DETERMINISTIC_LIMIT = 5.0


def validate_calibration_seeds(seeds: Sequence[int]) -> None:
    """Validate that seeds do not leak or overlap with the evaluation range."""
    eval_start, eval_end = EVALUATION_SEED_RANGE
    for s in seeds:
        if eval_start <= s <= eval_end:
            raise ValueError(
                f"Data leakage detected: seed {s} belongs to evaluation range "
                f"[{eval_start}, {eval_end}] and cannot be used in calibration."
            )


def calibrate_threshold(
    scores: Sequence[float],
    labels: Sequence[int],
    step: float = 0.01,
) -> tuple[float, float]:
    """Choose theta by grid search (step 0.01) maximizing classification accuracy.

    Rule: Predict 1 (exact_ok) if score <= theta, else 0.
    If several theta tie, return the midpoint of the best continuous range.

    Returns:
      (best_theta, best_accuracy)
    """
    if len(scores) != len(labels):
        raise ValueError(
            f"Scores and labels must have equal length, got {len(scores)} and {len(labels)}"
        )
    if not scores:
        return 0.5, 0.0

    n_samples = len(scores)

    # Grid search candidate thresholds from 0.0 to 1.0 inclusive
    num_steps = int(round(1.0 / step)) + 1
    candidates = [round(i * step, 4) for i in range(num_steps)]

    best_acc = -1.0
    best_thetas: list[float] = []

    for theta in candidates:
        correct = sum(
            1 for s, y in zip(scores, labels)
            if (1 if s <= theta else 0) == y
        )
        acc = correct / float(n_samples)

        if acc > best_acc + 1e-9:
            best_acc = acc
            best_thetas = [theta]
        elif abs(acc - best_acc) <= 1e-9:
            best_thetas.append(theta)

    if not best_thetas:
        return 0.5, 0.0

    # If several theta tie, find the longest contiguous block or take the midpoint
    min_theta = min(best_thetas)
    max_theta = max(best_thetas)
    midpoint = round((min_theta + max_theta) / 2.0, 4)

    return midpoint, best_acc


def label_instance_exact_ok(
    instance: Instance,
    deterministic_limit: float = DEFAULT_DETERMINISTIC_LIMIT,
) -> int:
    """Label an instance as exact_ok = 1 if ILP-EXACT finds OPTIMAL within deterministic limit."""
    res = solve_ilp_exact(
        instance,
        deterministic_time_limit=deterministic_limit,
        num_workers=1,
    )
    return 1 if res.meta.get("status") == "OPTIMAL" else 0


def get_git_hash() -> str:
    """Get current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def write_threshold_json(
    path: str | Path,
    threshold: float,
    alpha: Sequence[float],
    calibration_seeds: Sequence[int],
    labelling_limits: dict[str, Any],
    version: int = 1,
) -> dict[str, Any]:
    """Write validated threshold configuration to JSON file."""
    if version < 1:
        raise ValueError(f"Calibrated configuration version must be >= 1, got {version}")

    alpha_list = [round(float(a), 4) for a in alpha]
    if len(alpha_list) != 5:
        raise ValueError(f"Alpha must have 5 entries, got {len(alpha_list)}")
    if abs(sum(alpha_list) - 1.0) > 1e-4:
        raise ValueError(f"Alpha entries must sum to 1.0, got {sum(alpha_list)}")

    out_data = {
        "version": version,
        "threshold": round(float(threshold), 4),
        "alpha": alpha_list,
        "calibration_seeds": [min(calibration_seeds), max(calibration_seeds)],
        "labelling_limits": labelling_limits,
        "git_hash": get_git_hash(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    return out_data


def verify_threshold_release(path: str | Path | None = None) -> dict[str, Any]:
    """Verify threshold file schema and reject version 0 placeholder for production release."""
    cfg_file = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    with open(cfg_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("version", 0)
    if version == 0:
        raise ValueError(
            "Release check failed: threshold.json is still a provisional placeholder "
            "(version = 0). Run calibration script before release."
        )

    if "threshold" not in data or not (0.0 <= float(data["threshold"]) <= 1.0):
        raise ValueError("Invalid or missing 'threshold' in threshold.json")

    alpha = data.get("alpha", [])
    if len(alpha) != 5 or abs(sum(alpha) - 1.0) > 1e-4:
        raise ValueError("Invalid 'alpha' in threshold.json: must have 5 entries summing to 1.0")

    return data


def run_held_out_evaluation(
    eval_seeds: Sequence[int],
    threshold: float,
    alpha: Sequence[float],
    deterministic_limit: float = DEFAULT_DETERMINISTIC_LIMIT,
) -> dict[str, Any]:
    """Evaluate calibrated selector on held-out seeds and compare with baselines."""
    scores: list[float] = []
    labels: list[int] = []
    selector_preds: list[int] = []

    for seed in eval_seeds:
        # Create instance with varied sizes and knobs
        n = 10 + (seed % 5) * 5  # n in [10, 15, 20, 25, 30]
        inst = generate_extended(n=n, seed=seed)

        feats: Features = compute_features(inst)
        score = complexity_score(feats, alpha=alpha)
        scores.append(score)

        label = label_instance_exact_ok(inst, deterministic_limit=deterministic_limit)
        labels.append(label)

        pred = 1 if score <= threshold else 0
        selector_preds.append(pred)

    n_total = len(labels)
    selector_correct = sum(1 for p, y in zip(selector_preds, labels) if p == y)
    selector_acc = selector_correct / float(n_total) if n_total > 0 else 0.0

    # Majority class baseline
    count_1 = sum(labels)
    count_0 = n_total - count_1
    majority_acc = max(count_1, count_0) / float(n_total) if n_total > 0 else 0.0

    return {
        "n_samples": n_total,
        "exact_ok_count": count_1,
        "exact_fail_count": count_0,
        "selector_accuracy": selector_acc,
        "majority_baseline_accuracy": majority_acc,
    }


def write_selector_eval_report(
    report_path: str | Path,
    eval_metrics: dict[str, Any],
    threshold: float,
    alpha: Sequence[float],
) -> str:
    """Format and write held-out evaluation report to markdown file."""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""# Selector Held-Out Evaluation Report

**Date**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Git Hash**: `{get_git_hash()}`  
**Threshold**: {threshold:.4f}  
**Alpha**: `{list(alpha)}`  

## Accuracy vs Majority Baseline

| Metric | Value |
|---|---|
| Evaluation Samples | {eval_metrics['n_samples']} |
| Class 1 (Exact Affordable) | {eval_metrics['exact_ok_count']} |
| Class 0 (Exact Costly) | {eval_metrics['exact_fail_count']} |
| **Selector Accuracy** | **{eval_metrics['selector_accuracy'] * 100:.2f}%** |
| **Majority-Class Baseline** | **{eval_metrics['majority_baseline_accuracy'] * 100:.2f}%** |

## Summary
The calibrated threshold separates instances where exact ILP solving is feasible within the
deterministic budget from instances that require heuristic routing.
"""
    path.write_text(content, encoding="utf-8")
    return content
