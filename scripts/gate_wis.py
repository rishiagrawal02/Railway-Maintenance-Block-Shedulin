"""Mandatory Correctness Gate: WIS-DP vs Brute-Force Oracle (100/100).

Runs 100 independent simplified instances across seeds 0-99 and verifies
that the DP exact solver matches the brute-force oracle with zero tolerance.

Usage:
    python scripts/gate_wis.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(root_dir / "src") not in sys.path:
    sys.path.insert(0, str(root_dir / "src"))

from rbp.algorithms.brute_force import solve_brute_force  # noqa: E402
from rbp.algorithms.wis_dp import solve_wis_dp  # noqa: E402
from rbp.generation.simplified import generate_simplified  # noqa: E402
from rbp.validation import validate_schedule  # noqa: E402


def run_gate(n_instances: int = 100) -> tuple[int, int]:
    """Run the correctness gate across n_instances (seeds 0 to n_instances-1).

    Returns (passed, total).
    """
    passed = 0
    total = n_instances

    for seed in range(n_instances):
        # Deterministic parameters derived from seed
        rng = random.Random(seed + 1000)
        n = rng.randint(1, 16)
        overlap = round(rng.uniform(0.1, 0.9), 2)

        inst = generate_simplified(n=n, seed=seed, overlap_factor=overlap)

        res_dp = solve_wis_dp(inst)
        res_bf = solve_brute_force(inst)

        # 1. Exact objective match
        if res_dp.objective != res_bf.objective:
            print(
                f"FAIL on seed={seed} (n={n}, overlap={overlap}): "
                f"DP={res_dp.objective} != BF={res_bf.objective}",
                file=sys.stderr,
            )
            continue

        # 2. Independent validator accepts DP schedule
        val_report = validate_schedule(inst, res_dp.schedule)
        if not val_report.valid:
            print(
                f"FAIL on seed={seed}: DP schedule invalid: {val_report.violations}",
                file=sys.stderr,
            )
            continue

        # 3. Reported objective equals recomputed objective
        recomputed = sum(inst.task(tid).weight for tid in res_dp.schedule.starts)
        if res_dp.objective != recomputed:
            print(
                f"FAIL on seed={seed}: DP obj={res_dp.objective} != recomputed={recomputed}",
                file=sys.stderr,
            )
            continue

        passed += 1

    return passed, total


def main() -> int:
    passed, total = run_gate(100)
    print(f"GATE wis-dp vs brute-force: {passed}/{total}")
    if passed == total:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
