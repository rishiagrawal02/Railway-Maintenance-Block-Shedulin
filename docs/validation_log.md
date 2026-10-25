# Algorithm Validation and Correctness Log

This document records formal correctness gate results across development phases.

---

## Phase 4 Correctness Gate: WIS-DP vs Brute-Force Oracle

- **Gate Result**: `GATE wis-dp vs brute-force: 100/100` (100% agreement, 0 tolerance)
- **Date**: 2026-10-25
- **Commit Hash**: `e28c60c`
- **Specification Section**: 8.2 & 9.1 (Milestone 4.3)
- **Scope**:
  - 100 random simplified instances across seeds 0–99 with sizes $n \in [1, 16]$ and overlap factors $\in [0.1, 0.9]$.
  - 7 adversarial instance families across 5 sizes (3, 5, 8, 12, 15):
    1. `all_overlapping`
    2. `chain_of_touching`
    3. `nested_intervals`
    4. `equal_end_times`
    5. `equal_weights`
    6. `identical_intervals`
    7. `long_low_vs_short_high`
  - 100% of DP schedules verified against the independent ground-truth validator (`validate_schedule`).
  - 100% of reported DP objectives match exact sum of scheduled task weights.
