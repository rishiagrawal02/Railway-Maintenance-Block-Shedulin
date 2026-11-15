"""Generate Phase 9 summary tables and figures from complete result grids."""

import argparse
import json
from pathlib import Path

from rbp.experiments.analysis import make_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--repeat-root", type=Path)
    parser.add_argument("--allow-partial-repeat", action="store_true",
                        help="Label incomplete/missing repeats; primary grids stay strict")
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    print(json.dumps(make_report(args.results_root, args.output, args.repeat_root,
                                 args.allow_partial_repeat), indent=2))


if __name__ == "__main__":
    main()
