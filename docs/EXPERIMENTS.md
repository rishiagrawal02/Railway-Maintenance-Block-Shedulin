# Phase 9 experiments

Run from the repository root after installing the project:

```powershell
python -m rbp.experiments.runner config/experiments/e1.yaml --dry-run
python -m rbp.experiments.runner config/experiments/e1.yaml
python -m rbp.experiments.runner config/experiments/e2.yaml
python -m rbp.experiments.runner config/experiments/e3.yaml
```

`--dry-run` actually executes a tiny grid (eight tasks, one seed, one knob per
instance kind), in a separate directory. Full E1 has 1,080 rows, E2 has 245 rows
(including explicit ILP size-stop rows), and E3 has 600 rows. Simplified and
extended studies are distinct: WIS-DP is never applied to extended instances.

Each grid writes ignored `results/<id>/runs.csv`, `meta.json`, and `failures.log`.
CSV includes all RunRecord fields, requested size, actual task count, instance
hash, knob JSON, selector decision, CP-SAT status and UTC timestamp. Nested
metadata includes the schedule, so results can be independently inspected.
Source/config hashes, resolved settings, Python/OR-Tools versions, git commit,
dirty flag and platform are retained in provenance. Raw results are not committed.

All algorithm runs execute serially through the validating metrics runner.
Runtime measures the solver call, excluding instance generation, independent
validation and disk I/O. Configurable repetitions use median runtime. The
committed studies use one repetition per instance and aggregate across seeds.
CP-SAT uses one worker, seed zero, a 30-second wall limit (D11), and an additional
one-unit deterministic search limit to make budget-limited objectives repeatable.
The wall limit remains an emergency cap; repeat comparisons detect any divergence.
CA uses its documented five-task lookahead, explicitly stored in each config.

E2 stops attempting ILP for each kind/knob/seed after the first unproven result,
recording subsequent sizes as `SKIPPED_LIMIT`; heuristics and WIS-DP still run.
`TIMEOUT` with solver status `FEASIBLE` means a valid incumbent without a proof;
`UNKNOWN` means no incumbent. Neither is a proven optimum.

Rerunning the same command resumes by `(kind, algorithm, size, knob, seed)`.
Completed error/timeout rows are retained, not retried silently. Use another
`--output-root` for a fresh run. Resume refuses changed source, configuration or
Python/OR-Tools versions. Each row is flushed and synced; a torn final append is
discarded on restart. An OS lock prevents concurrent writers and is released
automatically if the process exits. Do not hand-edit completed CSV rows.

Evaluation seeds are restricted to 2000–2099; the committed E1/E3 grids use
2000–2029 and E2 uses 2000–2004. Calibration inputs are never accepted.
