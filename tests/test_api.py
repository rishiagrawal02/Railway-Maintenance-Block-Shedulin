"""Focused prototype contracts; tiny instances keep checks quick."""

import copy
import json

import pytest

from rbp import api


def test_plain_data_end_to_end():
    inst = api.generate_instance(n=6)
    assert api.load_instance(api.to_json(inst)) == inst
    result = api.run(inst)
    assert result["validation"]["valid"]
    assert result["metrics"]["violations"] == 0
    assert api.run(inst)["metrics"]["objective"] == result["metrics"]["objective"]
    for value in (inst, api.list_algorithms(inst), result, api.select(inst), api.compare(inst)):
        json.dumps(value, allow_nan=False)


def test_invalid_uploads_and_limits():
    inst = api.generate_instance(n=3)
    invalid = copy.deepcopy(inst)
    invalid["tasks"][0]["duration"] = -1
    with pytest.raises(api.APIError, match="E_DURATION"):
        api.load_instance(json.dumps(invalid))
    for raw in ('{"tasks":', "null", '{"horizon": NaN}', b"\xff"):
        with pytest.raises(api.APIError):
            api.load_instance(raw)
    with pytest.raises(api.APIError, match="size cap"):
        api.load_instance(b" " * (api.limits()["upload_max_mb"] * 1024 * 1024 + 1))
    with pytest.raises(api.APIError, match="Task count"):
        api.generate_instance(n=api.limits()["max_tasks_ui"] + 1)
    invalid = copy.deepcopy(inst)
    invalid["tasks"] *= api.limits()["max_tasks_ui"]
    with pytest.raises(api.APIError, match="Task limit"):
        api.load_instance(json.dumps(invalid))
    with pytest.raises(api.APIError, match="simplified"):
        api.run(inst, "WIS-DP")
    large = api.generate_instance("simplified", n=api.limits()["ilp_max_tasks"] + 1)
    with pytest.raises(api.APIError, match="ILP disabled"):
        api.run(large, "ILP-EXACT")


def test_small_exact_run():
    result = api.run(api.generate_instance("simplified", n=4), "ILP-EXACT", {"time_limit_s": 1})
    assert result["validation"]["valid"]
    assert result["metrics"]["scheduled"] > 0
