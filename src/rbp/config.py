"""Configuration loading and validation for RBP."""

from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid or missing required keys."""

    pass


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "defaults.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate configuration from YAML file."""
    config_file = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_file.exists():
        raise ConfigError(f"Configuration file not found: {config_file}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as exc:
        raise ConfigError(f"Failed to parse configuration YAML: {exc}") from exc

    if not isinstance(cfg, dict):
        raise ConfigError("Configuration root must be a dictionary")

    _validate_config(cfg)
    return cfg


def _validate_config(cfg: dict[str, Any]) -> None:
    # Horizon
    if "horizon" not in cfg:
        raise ConfigError("Missing required config key: 'horizon'")
    h = cfg["horizon"]
    if not isinstance(h, int) or isinstance(h, bool) or h <= 0:
        raise ConfigError("Config key 'horizon' must be a positive integer")

    # Seeds
    if "seeds" not in cfg:
        raise ConfigError("Missing required config key: 'seeds'")
    seeds = cfg["seeds"]
    if not isinstance(seeds, dict):
        raise ConfigError("Config key 'seeds' must be a dictionary")

    for seed_group in ("gate", "calibration", "evaluation"):
        if seed_group not in seeds:
            raise ConfigError(f"Missing seeds group: '{seed_group}'")
        bounds = seeds[seed_group]
        if not (isinstance(bounds, (list, tuple)) and len(bounds) == 2):
            raise ConfigError(f"Seed range '{seed_group}' must be a pair [start, end]")
        if not (isinstance(bounds[0], int) and isinstance(bounds[1], int)):
            raise ConfigError(f"Seed range '{seed_group}' bounds must be integers")
        if bounds[0] > bounds[1]:
            raise ConfigError(f"Seed range '{seed_group}' start must be <= end")

    # Selector
    if "selector" not in cfg:
        raise ConfigError("Missing required config key: 'selector'")
    selector = cfg["selector"]
    if not isinstance(selector, dict):
        raise ConfigError("Config key 'selector' must be a dictionary")

    if "alpha" not in selector:
        raise ConfigError("Missing selector key: 'alpha'")
    alpha = selector["alpha"]
    if not (isinstance(alpha, (list, tuple)) and len(alpha) == 5):
        raise ConfigError("Selector 'alpha' must be a list of 5 numeric weights")
    for a in alpha:
        if not isinstance(a, (int, float)) or isinstance(a, bool) or not (0.0 <= a <= 1.0):
            raise ConfigError("Each entry in 'alpha' must be a float between 0 and 1")
    if abs(sum(alpha) - 1.0) > 1e-6:
        raise ConfigError(f"Selector 'alpha' weights must sum to 1.0 (got {sum(alpha)})")

    if "n_ref" not in selector:
        raise ConfigError("Missing selector key: 'n_ref'")
    if not isinstance(selector["n_ref"], int) or selector["n_ref"] <= 0:
        raise ConfigError("Selector 'n_ref' must be a positive integer")

    if "exact_route_for_extended" not in selector:
        raise ConfigError("Missing selector key: 'exact_route_for_extended'")
    if selector["exact_route_for_extended"] not in ("ilp", "none"):
        raise ConfigError("Selector 'exact_route_for_extended' must be 'ilp' or 'none'")

    # CA-GREEDY
    if "ca_greedy" not in cfg:
        raise ConfigError("Missing required config key: 'ca_greedy'")
    ca = cfg["ca_greedy"]
    if not isinstance(ca, dict):
        raise ConfigError("Config key 'ca_greedy' must be a dictionary")

    for lambda_key in ("lambda_block", "lambda_resource", "lambda_conflict"):
        if lambda_key not in ca:
            raise ConfigError(f"Missing ca_greedy key: '{lambda_key}'")
        val = ca[lambda_key]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
            raise ConfigError(f"ca_greedy '{lambda_key}' must be a non-negative number")

    if "lookahead_k" not in ca:
        raise ConfigError("Missing ca_greedy key: 'lookahead_k'")
    if not isinstance(ca["lookahead_k"], int) or ca["lookahead_k"] < 0:
        raise ConfigError("ca_greedy 'lookahead_k' must be a non-negative integer")

    # ILP
    if "ilp" not in cfg:
        raise ConfigError("Missing required config key: 'ilp'")
    ilp = cfg["ilp"]
    if not isinstance(ilp, dict):
        raise ConfigError("Config key 'ilp' must be a dictionary")

    time_limit = ilp.get("time_limit_s")
    if not isinstance(time_limit, (int, float)) or time_limit <= 0:
        raise ConfigError("ilp 'time_limit_s' must be a positive number")
    if "workers" not in ilp or not isinstance(ilp["workers"], int) or ilp["workers"] < 1:
        raise ConfigError("ilp 'workers' must be a positive integer")
    if "seed" not in ilp or not isinstance(ilp["seed"], int):
        raise ConfigError("ilp 'seed' must be an integer")
