"""Tests for config loading and validation."""

import pytest
import yaml

from rbp.config import ConfigError, load_config


def test_load_valid_default_config():
    """T0.3-01: Load valid default configuration."""
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert cfg["horizon"] == 1440
    assert "seeds" in cfg
    assert "selector" in cfg
    assert "ca_greedy" in cfg
    assert "ilp" in cfg


def test_missing_key_raises_config_error(tmp_path):
    """T0.3-02: Missing required key raises ConfigError naming the key."""
    cfg = load_config()
    del cfg["horizon"]

    temp_file = tmp_path / "bad_config.yaml"
    with open(temp_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    with pytest.raises(ConfigError, match="horizon"):
        load_config(temp_file)


def test_wrong_type_raises_config_error(tmp_path):
    """T0.3-03: Wrong value type raises ConfigError."""
    cfg = load_config()
    cfg["horizon"] = "not-an-integer"

    temp_file = tmp_path / "bad_type.yaml"
    with open(temp_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    with pytest.raises(ConfigError, match="horizon"):
        load_config(temp_file)


def test_alpha_sum_validation(tmp_path):
    """T0.3-04: Alpha weights not summing to 1.0 raise ConfigError."""
    cfg = load_config()
    cfg["selector"]["alpha"] = [0.2, 0.2, 0.2, 0.2, 0.1]  # sums to 0.9

    temp_file = tmp_path / "bad_alpha.yaml"
    with open(temp_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    with pytest.raises(ConfigError, match="sum to 1.0"):
        load_config(temp_file)
