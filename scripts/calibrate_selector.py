"""Calibration script for the adaptive selector threshold (Milestone 8.3).

Calibrates theta on calibration seeds (1000-1099) using deterministic CP-SAT
limits, writes config/threshold.json (version 1), evaluates on held-out seeds
(2000-2099), and generates reports/selector_eval.md.
"""

from __future__ import annotations

import argparse
import sys

from rbp.generation import generate_extended
from rbp.selector.calibration import (
    CALIBRATION_SEED_RANGE,
    DEFAULT_DETERMINISTIC_LIMIT,
    EVALUATION_SEED_RANGE,
    calibrate_threshold,
    label_instance_exact_ok,
    run_held_out_evaluation,
    validate_calibration_seeds,
    write_selector_eval_report,
    write_threshold_json,
)
from rbp.selector.features import (
    DEFAULT_CONFIG_PATH,
    Features,
    complexity_score,
    compute_features,
    load_alpha,
)


def run_calibration(
    n_cal_instances: int = 40,
    n_eval_instances: int = 25,
    deterministic_limit: float = DEFAULT_DETERMINISTIC_LIMIT,
    output_config: str = str(DEFAULT_CONFIG_PATH),
    output_report: str = "reports/selector_eval.md",
) -> None:
    """Run calibration and held-out evaluation."""
    print("=" * 60)
    print("Railway Maintenance Block Planning: Selector Calibration")
    print("=" * 60)

    # 1. Prepare calibration seeds (strictly within 1000-1099)
    cal_start, cal_end = CALIBRATION_SEED_RANGE
    cal_seeds = list(range(cal_start, min(cal_end + 1, cal_start + n_cal_instances)))
    validate_calibration_seeds(cal_seeds)

    # Load initial alpha
    alpha = load_alpha(output_config)
    print(f"Loaded alpha weights: {alpha}")
    print(f"Generating and labelling {len(cal_seeds)} calibration instances...")

    scores: list[float] = []
    labels: list[int] = []

    # Sizes 20 to 60 for fast and robust calibration
    sizes = [20, 25, 30, 40]
    knob_slack = [0.8, 1.0, 1.2]

    for idx, seed in enumerate(cal_seeds):
        n = sizes[idx % len(sizes)]
        slack = knob_slack[(idx // len(sizes)) % len(knob_slack)]
        inst = generate_extended(n=n, seed=seed, window_slack_factor=slack)

        feats: Features = compute_features(inst)
        score = complexity_score(feats, alpha=alpha)
        scores.append(score)

        label = label_instance_exact_ok(inst, deterministic_limit=deterministic_limit)
        labels.append(label)

    exact_ok_count = sum(labels)
    print(f"Calibration complete: {exact_ok_count}/{len(labels)} instances exact_ok=1")

    # 2. Calibrate threshold theta
    best_theta, best_acc = calibrate_threshold(scores, labels, step=0.01)
    print(f"Calibrated threshold theta: {best_theta:.4f} (Accuracy: {best_acc * 100:.2f}%)")

    # 3. Write updated config/threshold.json (version 1)
    limits_meta = {
        "max_deterministic_time": deterministic_limit,
        "sample_sizes": sizes,
    }
    write_threshold_json(
        path=output_config,
        threshold=best_theta,
        alpha=alpha,
        calibration_seeds=cal_seeds,
        labelling_limits=limits_meta,
        version=1,
    )
    print(f"Wrote calibrated threshold configuration to: {output_config}")

    # 4. Held-out evaluation on evaluation seeds (2000-2099)
    eval_start, eval_end = EVALUATION_SEED_RANGE
    eval_seeds = list(range(eval_start, min(eval_end + 1, eval_start + n_eval_instances)))

    print(f"\nEvaluating on {len(eval_seeds)} held-out seeds ({eval_start}-{eval_seeds[-1]})...")
    eval_metrics = run_held_out_evaluation(
        eval_seeds=eval_seeds,
        threshold=best_theta,
        alpha=alpha,
        deterministic_limit=deterministic_limit,
    )

    print(f"Held-out Selector Accuracy: {eval_metrics['selector_accuracy'] * 100:.2f}%")
    print(f"Majority-Class Baseline:    {eval_metrics['majority_baseline_accuracy'] * 100:.2f}%")

    # 5. Write held-out report
    write_selector_eval_report(
        report_path=output_report,
        eval_metrics=eval_metrics,
        threshold=best_theta,
        alpha=alpha,
    )
    print(f"Wrote evaluation report to: {output_report}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate selector threshold.")
    parser.add_argument("--cal-instances", type=int, default=30)
    parser.add_argument("--eval-instances", type=int, default=20)
    parser.add_argument("--det-limit", type=float, default=5.0)
    args = parser.parse_args()

    run_calibration(
        n_cal_instances=args.cal_instances,
        n_eval_instances=args.eval_instances,
        deterministic_limit=args.det_limit,
    )
    sys.exit(0)
