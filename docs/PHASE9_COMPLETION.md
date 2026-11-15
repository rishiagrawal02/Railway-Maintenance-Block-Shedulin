# Phase 9 completion checkpoint

Milestones 9.1 and 9.2 are implemented. The complete primary E1, E2 and E3 grids,
summary tables, paired comparisons, seed-half comparisons, provenance audit and
four figures are committed. Raw results remain ignored.

| Check | Result |
|---|---|
| E1 primary grid | 1,080 rows; zero errors, violations and anomalies |
| E2 primary grid | 245 rows; zero errors, violations and anomalies |
| E3 primary grid | 600 rows; zero errors, violations and anomalies |
| E1 fresh-clone repeat | All 1,080 rows matched; clean clone at `549e823` |
| E2 repeat | 99/245 rows matched; remaining runs stopped at user request |
| E3 repeat | Not run, at user request |
| Integration checks before measurements | 49 tests passed |
| Final focused verification | 4 tests passed, 5 deselected; no full-suite rerun |
| Lint | `ruff check .` passed |
| Figures | Four inspected PNGs, each below 110 KB |
| Existing checkpoint | `cp-9.1` retained without rewriting history |
| Final checkpoint tags | `cp-9.2`, `phase-9-complete` |
| Phase 10 | GO under the user's shortened verification scope |

The user explicitly requested fewer tests after the full primary grids and E1
fresh-clone repeat completed. Accordingly, this checkpoint does **not** certify
full E2/E3 repeat reproducibility. The final focused checks cover aggregation
math, genuine-optimum filtering, slope fitting, and complete/partial report
generation. An earlier full-suite run passed 266 tests and found a chart pivot
issue; that issue was fixed and subsequently passed the integration and focused
checks. A new full-suite run was not performed after the shorter-verification
request.

## Changes

- Serial resumable grid runner with durable CSV rows, exclusive output locks,
  evaluation-seed enforcement, source/config fingerprints and dependency versions.
- SELECTOR uses the shared validated algorithm runner, records its choice, and
  passes bounded settings only to the solver it selects.
- CP-SAT incumbents and unknown outcomes are distinguished from proven optima.
- E1 includes simplified and extended instances; E2 reaches 5,000 tasks; E3 covers
  all five prescribed asset-count levels and all 30 seeds.
- Analysis reports sample counts, means, sample standard deviations, paired
  win/tie/loss counts, genuine gaps, best-observed objective ratios, fitted runtime
  slopes and seed-half comparisons.
- The earlier remote Phase 9.1 branch was merged without force-pushing or changing
  its checkpoint tag. Existing local `pyproject.toml` edits and the Word lock file
  were excluded from commits.

## Results and limitations

See [analysis](../reports/phase9_analysis.md) and [audit](../reports/phase9_audit.json).
Budget-limited CP-SAT and explicit E2 ILP size skips are expected outcomes, not
execution failures. The measured WIS-DP log-log slope is 0.841; this finite-range,
single-repetition timing result is not an asymptotic-complexity proof. The E3
selector chose ILP in all 150 instances, so that study does not demonstrate
adaptive routing benefit. All claims are scoped to these synthetic workloads.

The measurements used committed source `549e823`. Reporting changes afterward
add explicit partial-repeat handling without changing solvers or generated data.
For exact checkpoint commit IDs, resolve the annotated Git tags above.
