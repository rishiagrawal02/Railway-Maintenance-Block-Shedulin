"""CLI tool for generating synthetic scheduling instances.

Usage:
    python scripts/gen_instances.py --kind simplified --n 50 --seed 1 --out data/generated/s1.json
    python scripts/gen_instances.py --kind extended --n 50 --seed 1 --out data/generated/e1.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(root_dir / "src") not in sys.path:
    sys.path.insert(0, str(root_dir / "src"))

from rbp.generation.simplified import generate_simplified  # noqa: E402
from rbp.io.serialize import save_json  # noqa: E402


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic scheduling instances.")
    parser.add_argument(
        "--kind",
        type=str,
        choices=["simplified", "extended"],
        default="simplified",
        help="Type of instance to generate",
    )
    parser.add_argument("--n", type=int, required=True, help="Number of tasks")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed")
    parser.add_argument("--horizon", type=int, default=1440, help="Planning horizon (minutes)")
    parser.add_argument(
        "--overlap-factor",
        type=float,
        default=0.5,
        help="Overlap factor for simplified instances (0.0 to 1.0)",
    )
    parser.add_argument("--dmin", type=int, default=10, help="Minimum task duration")
    parser.add_argument("--dmax", type=int, default=120, help="Maximum task duration")
    parser.add_argument("--out", type=str, required=True, help="Output JSON path")
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> int:
    parsed = parse_args(args)

    if parsed.kind == "simplified":
        instance = generate_simplified(
            n=parsed.n,
            seed=parsed.seed,
            horizon=parsed.horizon,
            overlap_factor=parsed.overlap_factor,
            dmin=parsed.dmin,
            dmax=parsed.dmax,
        )
    elif parsed.kind == "extended":
        try:
            from rbp.generation.extended import generate_extended
        except ImportError:
            print("Error: extended generator not yet implemented.", file=sys.stderr)
            return 1
        instance = generate_extended(
            n=parsed.n,
            seed=parsed.seed,
            horizon=parsed.horizon,
        )
    else:
        print(f"Unknown kind: {parsed.kind}", file=sys.stderr)
        return 1

    out_path = Path(parsed.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(instance, out_path)
    print(f"Generated {parsed.kind} instance with {len(instance.tasks)} tasks -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
