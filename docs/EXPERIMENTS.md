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

## Repeats and analysis

After the first three grids, rerun all three with `--output-root results/repeat`.
Run these serially as well. Then generate and verify the report:

```powershell
python scripts/make_report.py --results-root results --repeat-root results/repeat
```

The delivered run uses `--allow-partial-repeat` because the user requested shorter
verification after the full primary grids and fresh-clone E1 repeat completed.
It explicitly marks E2's 99-row repeat as partial and E3 as not repeated. This
flag never relaxes completeness, error or constraint checks on the primary grids.
The saved measurements use commit `549e823`; the later reporting-only change adds
partial-repeat labels. For resuming those original raw measurements, use that
commit's runner so its source fingerprint matches, rather than editing provenance.

The report refuses missing/duplicate grid keys, input-hash disagreement, errors,
constraint violations, negative gaps, incompatible repeat provenance, or changed
repeat objectives/statuses. Omit `--repeat-root` only for an uncertified exploratory
report. Runtime is deliberately excluded from reproducibility comparisons.

For the fresh-clone E1 check, clone the experiment commit into a separate directory,
set `PYTHONPATH` to that clone's `src` (so an editable installation cannot resolve
the original checkout), and run the E1 command from the clone with an absolute
`--output-root` pointing at `results/repeat` in the original checkout. Use the same
Python and OR-Tools versions recorded in the first run. Do not run another copy
concurrently with a timing study. This is a fresh-checkout repeat on the same
machine, not independent hardware replication.

Committed outputs are `summary_E1.csv`–`summary_E3.csv`, `paired_E*.csv`,
`seed_halves_E*.csv`, `runtime_slopes.csv`, `selector_shares_E3.csv`,
`phase9_audit.json`, `phase9_analysis.md` and four small PNGs. Every plotted point
has its sample count in the summary tables. Sample standard deviation is missing
for a single observation; cells with no usable result remain missing. Zero
reference/best-observed objectives have undefined gap/ratio, not fabricated zeros.

`objective_ratio` means objective divided by the best observed valid objective on
the same instance. It is never labeled an optimality gap. True gaps require an
ILP `OPTIMAL` reference, or WIS-DP for simplified instances. The selector's own
claim of optimality is not used as an independent reference.
