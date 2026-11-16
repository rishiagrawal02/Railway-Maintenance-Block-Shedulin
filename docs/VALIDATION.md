# Validation evidence and release status

Historical records are evidence for the named revisions, not claims that every
later revision was retested. [Original gate log](validation_log.md).

| Date | Revision | Evidence | Scope |
| --- | --- | --- | --- |
| 2026-10-25 | `e28c60c` | WIS-DP 100/100 against brute force | [Gate log](validation_log.md) |
| 2026-10-25 | `a6ffb7e` | Exact-solver cross-check report recorded | [Historical ILP report](ilp_crosscheck.md); finite-instance evidence, not a universal proof |
| 2026-11-15 | `549e823` | E1 1080, E2 245, E3 600 primary rows; E1 repeat matched | [Phase 9 checkpoint](PHASE9_COMPLETION.md); E2 partial and E3 not repeated |
| 2026-11-16 | `44ff3c2`, merge `a420a90` | 11 focused tests, UI walkthrough, cleanup and failure handling | [Phase 10 checkpoint](PHASE_10_CHECKPOINT.md) |

## Phase 11 candidate

Local verification on 2026-11-16 used a separate clone at
`590bf1e01bbd66326555888db40cbe059a1e9d50` and a newly created Python 3.12.8
virtual environment on Windows. It did not reuse the development environment's
editable package. The clone's working tree remained clean.

| Check | Observed result |
| --- | --- |
| README installation | `pip install -r requirements.txt` succeeded, including editable `rbp` |
| Dependency integrity | `pip check`: no broken requirements |
| Import location | `rbp.__file__` resolved into the new clone |
| Full pytest, including slow | **279 passed in 209.97 seconds** |
| Standalone WIS-DP gate | **100/100** |
| Release checker | Exit 0; 151 indexed files inspected |
| Repository lint | `ruff check .`: passed |
| Reproduction script syntax | Git Bash `bash -n scripts/reproduce.sh`: passed |
| Experiment smoke | E1 dry-run: nine runs, all OK |
| Clean-environment app health | HTTP 200, response `ok`, port 8503 |
| Full primary/repeat E1–E3 via reproduction script | Not run in this release verification; pending |
| Independent second-person reproduction | Pending |
| Hosted Community Cloud deployment | Not performed |

The full suite includes UI interaction, failure handling, figure cleanup and
small report-pipeline tests; it is not a substitute for complete experiment grids.
Later documentation-only commits record this evidence without changing the
tested implementation. Local environment details were saved under ignored
`results/release-verification/environment.txt`.

The second-person attempt against `a420a9036d6a926e031ef024bc51231cc16eff8b`
on 2026-11-16 was **BLOCKED**: the release branch/scripts were not published,
Python 3.12 was unavailable, and dependencies were not installed. Its 30 collection
errors are not a completed application correctness evaluation.

On 2026-11-16 the user explicitly waived the independent teammate verification.
No second-person success is inferred from local checks. Final release remains
pending final CI and disposition of the additional qualifications in the
[final checklist](FINAL_RELEASE_CHECKLIST.md). Follow [the verification procedure](RELEASE_VERIFICATION.md).

Byte-identical timing summaries are not promised. The reproduction script compares
non-timing summaries and audits primary/repeat outcomes; platform-dependent solver
budget differences fail that check and require investigation. Full E2/E3 repeat
certification cannot be inherited from the partial Phase 9 evidence.

The milestone's byte-identical-summary requirement needs an explicitly accepted
exception for runtime columns. The implemented non-timing comparison is the
proposed criterion; it does not silently certify that original requirement.
