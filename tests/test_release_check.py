"""Negative hygiene tests use synthetic files and an isolated temporary Git index."""

import json
import subprocess

from scripts.compare_summaries import compare
from scripts.release_check import check_files, indexed_files


def valid_files():
    return {
        "config/threshold.json": b'{"version":1}',
        "tests/data/golden_hashes.json": json.dumps(
            {
                f"{kind}_n{n}_s{seed}": "a" * 64
                for kind in ("simplified", "extended")
                for n, seed in ((25, 1), (50, 42))
            }
        ).encode(),
        "README.md": b"[Guide](docs/guide.md)",
        "docs/guide.md": b"[Home](../README.md)\n[Web](https://example.com)",
    }


def test_release_hygiene_negative_cases():
    files = valid_files()
    assert check_files(files) == []
    assert any(
        "Threshold version" in e
        for e in check_files({**files, "config/threshold.json": b'{"version":0}'})
    )
    assert any(
        "Golden hashes" in e for e in check_files({**files, "tests/data/golden_hashes.json": b"{}"})
    )
    assert any("Generated output" in e for e in check_files({**files, "results/x.csv": b"x"}))
    assert any(
        "Broken relative link" in e
        for e in check_files({**files, "README.md": b"[Missing](absent.md)"})
    )
    credential = ("gh" + "p_" + "A" * 36).encode()
    errors = check_files({**files, "settings.txt": credential})
    assert any("Potential credential" in e for e in errors)
    assert all(credential.decode() not in e for e in errors)


def test_index_scan_sees_staged_content(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    for name, content in valid_files().items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (tmp_path / ".gitignore").write_text("results/\n")
    git("add", ".")
    assert check_files(indexed_files(tmp_path)) == []
    output = tmp_path / "results/x.csv"
    output.parent.mkdir()
    output.write_text("private output")
    git("add", "-f", "results/x.csv")
    output.unlink()  # Staged output still fails even when removed from the working tree.
    assert any("Generated output" in e for e in check_files(indexed_files(tmp_path)))
    git("rm", "--cached", "results/x.csv")
    assert check_files(indexed_files(tmp_path)) == []


def test_summary_comparison_ignores_only_timing(tmp_path):
    import pandas as pd

    reference = tmp_path / "reference"
    actual = tmp_path / "actual"
    reference.mkdir()
    actual.mkdir()
    row = dict(
        kind="simplified", size=5, knob="{}", algo="WIS-DP", objective_mean=12, runtime_s_mean=0.1
    )
    for name in ("E1", "E2", "E3"):
        pd.DataFrame([row]).to_csv(reference / f"summary_{name}.csv", index=False)
        pd.DataFrame([{**row, "runtime_s_mean": 99}]).to_csv(
            actual / f"summary_{name}.csv", index=False
        )
    assert compare(actual, reference) == []
    pd.DataFrame([{**row, "objective_mean": 13}]).to_csv(actual / "summary_E1.csv", index=False)
    assert len(compare(actual, reference)) == 1
