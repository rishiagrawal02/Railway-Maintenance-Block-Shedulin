"""Phase 9.1 acceptance tests, including interrupted and incompatible resumes."""

import csv
import json
from copy import deepcopy

import pytest

from rbp.experiments import runner
from rbp.metrics.runner import ALGORITHMS
from rbp.models import Schedule


@pytest.fixture
def cfg():
    return {
        "id": "tiny", "sizes": [4, 6], "seeds": [2000, 2001, 2002],
        "studies": [{"kind": "simplified", "algorithms": ["NAIVE-GREEDY", "WIS-DP"]}],
    }


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def without_timing(value):
    if isinstance(value, dict):
        return {k: without_timing(v) for k, v in value.items()
                if k not in ("runtime_s", "timestamp")}
    if isinstance(value, list):
        return [without_timing(v) for v in value]
    return value


def test_row_count_schema_and_reproducibility(cfg, tmp_path):
    first = rows(runner.run_grid(cfg, tmp_path / "first"))
    second = rows(runner.run_grid(cfg, tmp_path / "second"))
    assert len(first) == 12
    assert list(first[0]) == runner.COLUMNS
    for left, right in zip(first, second):
        for row in (left, right):
            assert int(row["violations"]) == 0
            assert float(row["runtime_s"]) >= 0
            assert int(row["objective"]) > 0
            row["meta"] = json.loads(row["meta"])
        assert without_timing(left) == without_timing(right)


def test_interrupted_resume_and_partial_tail(cfg, tmp_path, monkeypatch):
    original = runner.run_algorithm
    calls = 0

    def interrupt(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "run_algorithm", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run_grid(cfg, tmp_path)
    path = tmp_path / "tiny" / "runs.csv"
    assert len(rows(path)) == 5
    prefix = path.read_bytes()
    with path.open("ab") as handle:
        handle.write(b"torn,row")
    monkeypatch.setattr(runner, "run_algorithm", original)
    runner.run_grid(cfg, tmp_path)
    assert path.read_bytes().startswith(prefix)
    assert len(rows(path)) == 12
    contents = path.read_bytes()
    runner.run_grid(cfg, tmp_path)
    assert path.read_bytes() == contents


def test_failure_isolation_and_violations(cfg, tmp_path, monkeypatch):
    def fail(instance):
        raise RuntimeError("injected failure")

    def invalid(instance):
        return Schedule({instance.tasks[0].id: -50})

    monkeypatch.setitem(ALGORITHMS, "FAIL", fail)
    monkeypatch.setitem(ALGORITHMS, "INVALID", invalid)
    cfg["studies"][0]["algorithms"] = ["FAIL", "INVALID", "WIS-DP"]
    data = rows(runner.run_grid(cfg, tmp_path))
    assert len(data) == 18
    assert all(r["status"] == "ERROR" for r in data if r["algo"] == "FAIL")
    assert all(int(r["violations"]) > 0 for r in data if r["algo"] == "INVALID")
    assert all(r["status"] == "OK" for r in data if r["algo"] == "WIS-DP")
    assert "injected failure" in (tmp_path / "tiny" / "failures.log").read_text()


def test_provenance_and_changed_config_refused(cfg, tmp_path):
    runner.run_grid(cfg, tmp_path)
    meta = json.loads((tmp_path / "tiny" / "meta.json").read_text())
    for key in ("git_hash", "git_dirty", "config_hash", "source_hash", "python_version",
                "ortools_version", "timestamp", "config"):
        assert key in meta
    changed = deepcopy(cfg)
    changed["sizes"] = [4, 7]
    with pytest.raises(ValueError, match="Resume refused"):
        runner.run_grid(changed, tmp_path)


@pytest.mark.parametrize("seeds", [[1000], [1999], [2100], [], [2000, 2000]])
def test_seed_policy(cfg, tmp_path, seeds):
    cfg["seeds"] = seeds
    with pytest.raises(ValueError):
        runner.run_grid(cfg, tmp_path)
    assert not (tmp_path / "tiny").exists()


def test_timeout_selector_options_and_stopping(cfg, tmp_path):
    cfg["studies"] = [{"kind": "extended", "algorithms": ["SELECTOR", "ILP-EXACT"]}]
    cfg["selector_threshold"] = 1.0
    cfg["seeds"] = [2000]
    cfg["solver_options"] = {"ILP-EXACT": {"time_limit_s": 1e-9}}
    cfg["stop_ilp_after_limit"] = True
    data = rows(runner.run_grid(cfg, tmp_path))
    selector = [r for r in data if r["algo"] == "SELECTOR"]
    assert all(r["chosen_algorithm"] == "ILP-EXACT" for r in selector)
    assert all(r["selector_reason"] for r in selector)
    assert all(r["status"] == "TIMEOUT" and r["optimal"] == "False" for r in selector)
    ilp = [r for r in data if r["algo"] == "ILP-EXACT"]
    assert ilp[0]["solver_status"] == "UNKNOWN"
    assert ilp[1]["status"] == "SKIPPED_LIMIT"


def test_selector_dp_optimal(cfg, tmp_path):
    cfg["studies"][0]["algorithms"] = ["SELECTOR"]
    cfg["selector_threshold"] = 1.0
    data = rows(runner.run_grid(cfg, tmp_path))
    assert all(r["chosen_algorithm"] == "WIS-DP" and r["optimal"] == "True" for r in data)


def test_generation_failure_isolated(cfg, tmp_path, monkeypatch):
    original = runner.generate_simplified

    def generate(**kwargs):
        if kwargs["seed"] == 2001:
            raise ValueError("bad instance")
        return original(**kwargs)

    monkeypatch.setattr(runner, "generate_simplified", generate)
    data = rows(runner.run_grid(cfg, tmp_path))
    assert len(data) == 12
    assert sum(r["status"] == "ERROR" for r in data) == 4
