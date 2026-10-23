# System Architecture & Import Boundaries

## Layer Overview

The Railway Maintenance Block Planning (RBP) system is organized into modular layers with strict directional dependencies:

```
+-----------------------------------------------------------+
|                   Streamlit UI (app/)                     |
+-----------------------------------------------------------+
                             |
                      (only imports)
                             v
+-----------------------------------------------------------+
|                     API Facade (api.py)                   |
+-----------------------------------------------------------+
         |                       |                 |
         v                       v                 v
+------------------+    +-----------------+    +------------+
| Adaptive Selector|    | Scheduling Algos|    | Experiments|
|   (selector/)    |    |  (algorithms/)  |    | (runner)   |
+------------------+    +-----------------+    +------------+
         |                       |
         |                       v
         |              +-----------------+
         |              |   Constraints   |
         |              | (constraints/)  |
         |              +-----------------+
         \                       |
          \                      v
           \            +-----------------+    +------------+
            ----------> |  Domain Models  | <--| Independent|
                        |    (models/)    |    |  Validator |
                        +-----------------+    +------------+
```

## Architectural Separation & Import Rules

To ensure total independence, correctness, and clean maintainability, the following boundary rules are strictly enforced by AST test (`tests/test_import_boundaries.py`):

1. **`rbp.models`**:
   - Contains immutable domain entities (`Task`, `Corridor`, `Resource`, `Timetable`, `Instance`, `Schedule`, `Interval`).
   - Must import **nothing** from `rbp`.

2. **`rbp.validation`**:
   - Independent ground-truth schedule validator for constraints C1 through C5.
   - May import **only** `rbp.models`.
   - Never imports `rbp.constraints` or `rbp.algorithms`. This ensures that a bug in algorithm predicates cannot hide or mirror a bug in the validator.

3. **`rbp.constraints`**:
   - Predicates and mutable state used by greedy search and algorithms.
   - May import `rbp.models`.
   - Never imports `rbp.validation` or `rbp.algorithms`.

4. **`rbp.algorithms`**:
   - Solvers (`wis_dp`, `brute_force`, `naive_greedy`, `ca_greedy`, `ilp_exact`).
   - May import `rbp.models` and `rbp.constraints`.
   - Never imports `rbp.validation`.

5. **`app/` (Streamlit UI)**:
   - Presentation layer only. Contains zero scheduling logic.
   - Imports **only** `rbp.api` and `rbp.viz` from the project package.

## Deterministic Seeding Policy

All random generations utilize named streams via `rbp.rng.make_rng(seed, stream)`.
- `seeds.gate`: Seeds 0–99 reserved for the 100/100 correctness gate (`WIS-DP` vs `BRUTE-FORCE`).
- `seeds.calibration`: Seeds 1000–1099 reserved for heuristic lambda tuning and selector threshold calibration.
- `seeds.evaluation`: Seeds 2000–2099 reserved strictly for final held-out evaluation experiments (E1, E2, E3).
- **Rule**: Calibration scripts are programmatically forbidden from accessing evaluation seeds to prevent data snooping.
