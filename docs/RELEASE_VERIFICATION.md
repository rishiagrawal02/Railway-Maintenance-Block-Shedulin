# Independent release verification

The user waived this independent teammate requirement on 2026-11-16. This
procedure remains available for optional external audits; it is no longer a
blocking release gate. See [accepted release scope](FINAL_RELEASE_CHECKLIST.md).

Use a fresh clone, not an existing development environment. Save logs outside the
repository. Do not change code, weaken tests, or modify measurements to make checks
pass. A blocked prerequisite is BLOCKED; an unattempted check is NOT TESTED.

1. Confirm `origin/phase-11-release` exists and contains `scripts/release_check.py`
   and `scripts/reproduce.sh`. Otherwise stop: the candidate is not ready.
2. Clone that branch into a new directory. Record `git rev-parse HEAD`, OS, date
   and tester identity. Read [README](../README.md) and applicable repository instructions.
3. Use Python 3.12 to create a new venv. If absent, install it or report BLOCKED;
   do not silently substitute another interpreter for reference reproduction.
4. Follow README installation commands. `pip check` must pass; imports of `rbp`,
   `streamlit` and `ortools` must succeed. Confirm `rbp.__file__` is in this clone.
   Stop if installation fails instead of collecting dependency-related test errors.
5. Run `python -m pytest` including slow tests, then `python scripts/gate_wis.py`
   (100/100), then `python scripts/release_check.py` (exit 0). Save outputs/exit codes.
6. With the environment activated, run `bash scripts/reproduce.sh`. This repeats
   the gates then runs complete primary and repeat grids. It may take substantial
   time. Record output directories and outcome comparisons. Do not run timing
   studies concurrently. Git Bash activation is `source .venv/Scripts/activate`.
7. Launch `python -m streamlit run app/streamlit_app.py`. Check the printed port's
   `/_stcore/health` endpoint for HTTP 200 and `ok`.
8. In the browser, generate an extended instance (20 tasks, two corridors, seed 3),
   run CA-GREEDY, inspect the Gantt/table and zero violations, compare NAIVE-GREEDY
   with CA-GREEDY, then open Adaptive Intelligence and Validation Center.
9. Upload a temporary malformed JSON file containing `{"tasks":` and confirm a
   friendly error without a traceback. Keep temporary uploads outside the repo.
10. Stop only your own app server; record `git status --short`. Do not commit/push.
    If browser automation is unavailable, mark the visual walkthrough NOT TESTED;
    an HTTP health check does not certify the interface.

## Return this report

```text
Tester:
Date / OS / Python version:
Branch / full commit hash:
Fresh installation: PASS / FAIL / BLOCKED
Full pytest: passed / failed / skipped
100-instance gate:
Release check exit code:
Primary/repeat audit:
Non-timing reference-summary comparison:
App health:
Browser walkthrough:
Invalid-upload handling:
Git status:
Log / screenshot locations:
Failures, blockers, untested items and limitations:
```

Runtime statistics vary across machines; see README's explicit comparison rule.
The author must review this evidence before tagging a final release. This checklist
is not an authorization to publish or deploy anything.
