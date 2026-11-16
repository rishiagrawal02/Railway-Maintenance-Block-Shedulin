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

Implementation and local verification are being recorded on `phase-11-release`.
The second-person attempt against `a420a9036d6a926e031ef024bc51231cc16eff8b`
on 2026-11-16 was **BLOCKED**: the release branch/scripts were not published,
Python 3.12 was unavailable, and dependencies were not installed. Its 30 collection
errors are not a completed application correctness evaluation.

The release remains **NO-GO for v1.0.0** until independent fresh-clone installation,
full tests, gate, release hygiene and full reproduction are recorded, or the user
explicitly accepts written exceptions. No second-person success is inferred from
agent-run local checks. Follow [the verification procedure](RELEASE_VERIFICATION.md).

Byte-identical timing summaries are not promised. The reproduction script compares
non-timing summaries and audits primary/repeat outcomes; platform-dependent solver
budget differences fail that check and require investigation. Full E2/E3 repeat
certification cannot be inherited from the partial Phase 9 evidence.
