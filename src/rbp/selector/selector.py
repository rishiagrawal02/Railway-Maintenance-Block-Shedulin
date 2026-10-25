"""Threshold-based algorithm selection and routing module (Milestone 8.2).

Computes instance complexity features and score, compares against a calibrated
threshold, and routes to the appropriate solver:
  - If score <= threshold:
      - WIS-DP if instance is simplified
      - ILP-EXACT if instance is extended and exact_route_for_extended == "ilp"
        (subject to ILP size guard n <= ilp_max_tasks)
      - CA-GREEDY if exact_route_for_extended == "none" or n > ilp_max_tasks
  - If score > threshold:
      - CA-GREEDY
  - If simplified_always_dp is True and instance is simplified:
      - WIS-DP regardless of score
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rbp.algorithms import AlgoResult, solve_ca_greedy, solve_ilp_exact, solve_wis_dp
from rbp.config import load_config
from rbp.models.instance import Instance
from rbp.models.simplified import is_simplified
from rbp.selector.features import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_N_REF,
    Features,
    complexity_score,
    compute_features,
)

DEFAULT_ILP_MAX_TASKS = 150


@dataclass(frozen=True, slots=True)
class Decision:
    """Algorithm selection decision with human-readable reasoning."""

    algorithm: str
    score: float
    features: Features
    threshold: float
    reason: str


def _load_threshold_and_alpha(
    threshold_path: str | Path | None = None,
) -> tuple[float, list[float] | None]:
    """Load threshold and optional alpha weights from JSON file."""
    path = Path(threshold_path) if threshold_path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Threshold configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "threshold" not in data:
        raise ValueError(f"Missing 'threshold' field in {path}")

    threshold = float(data["threshold"])
    alpha = data.get("alpha")
    return threshold, alpha


def select(
    instance: Instance,
    config: dict[str, Any] | None = None,
    threshold: float | None = None,
    threshold_path: str | Path | None = None,
) -> Decision:
    """Select the best algorithm for instance and provide human-readable reasoning."""
    # 1. Resolve configuration parameters
    cfg_selector: dict[str, Any] = {}
    if config is not None:
        cfg_selector = config.get("selector", {})
    else:
        try:
            full_cfg = load_config()
            cfg_selector = full_cfg.get("selector", {})
        except Exception:
            cfg_selector = {}

    n_ref = int(cfg_selector.get("n_ref", DEFAULT_N_REF))
    exact_route_ext = str(cfg_selector.get("exact_route_for_extended", "ilp")).lower()
    ilp_max_tasks = int(cfg_selector.get("ilp_max_tasks", DEFAULT_ILP_MAX_TASKS))
    simplified_always_dp = bool(cfg_selector.get("simplified_always_dp", False))
    alpha = cfg_selector.get("alpha")

    # 2. Resolve threshold and alpha weights
    if threshold is None:
        file_threshold, file_alpha = _load_threshold_and_alpha(threshold_path)
        threshold = file_threshold
        if alpha is None:
            alpha = file_alpha

    # 3. Compute features and score
    features = compute_features(instance, n_ref=n_ref)
    score = complexity_score(features, alpha=alpha)

    # 4. Identify dominant feature
    feat_dict = features.as_dict()
    dominant_feat, max_val = max(feat_dict.items(), key=lambda item: item[1])
    features_str = ", ".join(f"{k}={v:.4f}" for k, v in feat_dict.items())

    n = len(instance.tasks)
    is_simp = is_simplified(instance)

    # 5. Routing logic
    if simplified_always_dp and is_simp:
        algorithm = "WIS-DP"
        rule = (
            "simplified_always_dp is True -> routed simplified instance directly to WIS-DP "
            f"regardless of score ({score:.4f})"
        )
    elif score <= threshold:
        if is_simp:
            algorithm = "WIS-DP"
            rule = (
                f"score ({score:.4f}) <= threshold ({threshold:.4f}) and instance is simplified "
                "-> routed to exact solver WIS-DP"
            )
        else:
            if exact_route_ext == "ilp":
                if n > ilp_max_tasks:
                    algorithm = "CA-GREEDY"
                    rule = (
                        f"score ({score:.4f}) <= threshold ({threshold:.4f}) on extended instance, "
                        f"but task count n={n} exceeds ilp_max_tasks={ilp_max_tasks} "
                        "(ILP size guard) -> fallback to heuristic CA-GREEDY"
                    )
                else:
                    algorithm = "ILP-EXACT"
                    rule = (
                        f"score ({score:.4f}) <= threshold ({threshold:.4f}) on extended instance "
                        f"and exact_route_for_extended='ilp' (n={n} <= {ilp_max_tasks}) "
                        "-> routed to exact solver ILP-EXACT"
                    )
            else:
                algorithm = "CA-GREEDY"
                rule = (
                    f"score ({score:.4f}) <= threshold ({threshold:.4f}) on extended instance, "
                    f"but exact_route_for_extended flag is '{exact_route_ext}' "
                    "-> fallback to heuristic CA-GREEDY"
                )
    else:
        algorithm = "CA-GREEDY"
        rule = (
            f"score ({score:.4f}) > threshold ({threshold:.4f}) "
            "-> routed to conflict-aware heuristic CA-GREEDY"
        )

    reason = (
        f"Algorithm '{algorithm}' selected. Score: {score:.4f}, Threshold: {threshold:.4f}. "
        f"Features: [{features_str}]. Dominant feature: {dominant_feat} ({max_val:.4f}). "
        f"Rule: {rule}."
    )

    return Decision(
        algorithm=algorithm,
        score=score,
        features=features,
        threshold=threshold,
        reason=reason,
    )


def run_selected(
    instance: Instance,
    config: dict[str, Any] | None = None,
    threshold: float | None = None,
    threshold_path: str | Path | None = None,
    **algo_kwargs: Any,
) -> AlgoResult:
    """Select the optimal algorithm, run it, and store decision in AlgoResult.meta."""
    decision = select(
        instance,
        config=config,
        threshold=threshold,
        threshold_path=threshold_path,
    )

    if decision.algorithm == "WIS-DP":
        res = solve_wis_dp(instance, **algo_kwargs)
    elif decision.algorithm == "ILP-EXACT":
        res = solve_ilp_exact(instance, **algo_kwargs)
    elif decision.algorithm == "CA-GREEDY":
        res = solve_ca_greedy(instance, **algo_kwargs)
    else:
        raise ValueError(f"Unknown algorithm selected: '{decision.algorithm}'")

    new_meta = dict(res.meta)
    new_meta["decision"] = decision
    return AlgoResult(
        name=res.name,
        schedule=res.schedule,
        objective=res.objective,
        meta=new_meta,
    )
