"""Compare summary outcomes to committed reference, excluding timing measurements."""

import argparse
from pathlib import Path

import pandas as pd


def compare(actual, reference):
    differences = []
    keys = ["kind", "size", "knob", "algo"]
    for experiment in ("E1", "E2", "E3"):
        name = f"summary_{experiment}.csv"
        left, right = pd.read_csv(actual / name), pd.read_csv(reference / name)
        cols = [c for c in right.columns if not c.startswith("runtime_s_")]
        if set(left.columns) != set(right.columns):
            differences.append(f"{experiment}: column schema differs")
            continue
        if left.duplicated(keys).any() or right.duplicated(keys).any():
            differences.append(f"{experiment}: duplicate summary keys")
            continue
        try:
            pd.testing.assert_frame_equal(
                left[cols].sort_values(keys).reset_index(drop=True),
                right[cols].sort_values(keys).reset_index(drop=True),
                check_dtype=False,
                check_exact=False,
                rtol=1e-9,
                atol=1e-12,
            )
        except AssertionError:
            differences.append(f"{experiment}: non-timing summary values differ; inspect both CSVs")
    return differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=Path("reports"))
    args = parser.parse_args()
    try:
        differences = compare(args.actual, args.reference)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Comparison failed: {exc}")
        return 1
    for message in differences:
        print("FAIL:", message)
    if not differences:
        print("PASS: E1–E3 non-timing summary values match reference within numeric tolerance.")
        print("Runtime statistics are intentionally excluded; no byte-identical claim is made.")
    return bool(differences)


if __name__ == "__main__":
    raise SystemExit(main())
