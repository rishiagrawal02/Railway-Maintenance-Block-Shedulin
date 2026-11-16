# Final release checklist and traceability

Release: 1.0.0, subject to the final CI/tag gate below. This record distinguishes measured evidence from scope
exceptions. A historical measurement is not described as a fresh experiment run.

## Functional requirements

| Requirement | Implementation / verification |
| --- | --- |
| 1 Generate/load instances | `generation`, `io`, facade; generator/golden/serialization/API tests |
| 2 Represent domain entities | Immutable `models`; model tests |
| 3 Validate input | `io.input_checks`; failure-input/API/UI tests |
| 4 Check constraints | C1–C5 predicates; differential fuzz checks |
| 5 Generate alternative schedules | All six registry choices in `metrics.runner`; solver/runner/selector tests |
| 6 Independently validate schedules | `validation` imports only models/itself; boundary tests |
| 7 Calculate metrics | `metrics.metrics` and validated runner; metrics/runner tests |
| 8 Compare algorithms | Experiment reports and Performance Analytics; analysis/comparison tests |
| 9 Display results | Six Streamlit workspaces, Gantt and exports; AppTest and browser walkthrough |
| 10 Explain adaptive routing | Five features, threshold, chosen route and reason; selector/AppTest |

D1–D12 are recorded in [DECISIONS.md](DECISIONS.md). Algorithm Laboratory,
Experiment History and what-if analysis are intentionally deferred; they do not
remove backend scheduling, comparisons or selection reasoning.

## Evidence

- [Clean-clone verification](VALIDATION.md): 279 tests passed at `590bf1e`, Python
  3.12.8, standalone WIS-DP/brute-force gate 100/100, health HTTP 200 / `ok`.
- The full suite includes three-way BF/WIS/ILP equality across 100 seeds,
  predicate/validator fuzz agreement and golden hashes.
- The final candidate adds a regression rejecting resource outages in the
  simplified-case predicate, matching D8. Final CI must include this regression.
- [Historical Phase 9 audit](../reports/phase9_audit.json): E1/E2/E3 primary grids
  have zero violations/anomalies. E1's 1080-row repeat matched objectives;
  E2's repeat is partial and E3's repeat was not run.
- [E2 slopes](../reports/runtime_slopes.csv): WIS-DP 0.841 on finite workloads;
  this supports near-linear measured scaling, not an asymptotic proof.
- Gantt 1000-task render under 10 seconds and explicit figure cleanup are tested.
- `release_check.py` inspects staged UTF-8 files for credential patterns, verifies
  threshold/golden hashes and doc links, rejects generated/cache/environment
  files and files over 5 MB. This is a heuristic check, not a security audit.
- Uploads have server and facade caps, task/horizon guards and JSON-only parsing.
- Direct dependencies are pinned in requirements; transitive dependencies are
  resolved by pip and are not claimed to be a complete hash-locked environment.

## Release conditions and scope exceptions

| Item | Disposition |
| --- | --- |
| Independent teammate verification | Waived explicitly by user on 2026-11-16 |
| E2/E3 full repeat certification | Not claimed; prior user-requested shortened Phase 9 verification retained, accepted explicitly by user on 2026-11-16 |
| Byte-identical timing CSVs | Not a valid cross-machine criterion; non-timing comparison implemented, accepted explicitly by user on 2026-11-16 |
| ILP time limit | Solver search budget; preprocessing and scheduling overhead are outside it, accepted explicitly by user on 2026-11-16 |
| Authentication / authorization | Out of scope; public user accounts require a new phase and unauthorized-access tests |
| Hosted deployment | Setup documented; no claim of a live verified Community Cloud deployment |
| Existing personal checkout edits | Preserved; final main cleanliness will be checked in a separate clean release worktree |
| Final CI | Must pass on the main merge before tagging v1.0.0; run URL recorded in the delivery report |

Time-limited results are marked non-optimal. Genuine gaps require a validated
proven optimum; best-observed objective ratios are explicitly relative comparisons.
The selector evaluation's one-class sample does not demonstrate a routing benefit.

## Git completion

Do not treat this document as a claim that a tag exists before it is pushed.
Record the final branch/merge hashes, CI run URL and tag outcomes in the delivery
report. `cp-11.1`, `phase-11-complete` and `v1.0.0` are reserved until the applicable
release conditions above are satisfied or explicitly waived.

Final candidate implementation: `196ca8769be13bb8c084d6ae666a7b2ec673328e`.
[Candidate CI run](https://github.com/rishiagrawal02/Railway-Maintenance-Block-Shedulin/actions/runs/43848968548).
The final release tag is created only after the main merge CI passes.
