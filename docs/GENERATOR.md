# Synthetic Instance Generator Specifications

This document records the design parameters, numeric thresholds, and correlation structures implemented in `rbp.generation` (Milestones 3.1, 3.2, and 3.3).

---

## 1. Simplified Generator (`generate_simplified`)

Designed for the Weighted Interval Scheduling Dynamic Programming algorithm (WIS-DP).
Implements Decision **D8**:
- Exactly **1 corridor**, with 1 asset (`asset_id = 1`).
- Exactly **1 resource type** (`crew`), capacity = 1, available across `[0, horizon)`.
- **0 train intervals** (timetable is empty).
- All tasks have **`window_end - window_start == duration`** (fixed-interval problem).
- Every task demands exactly 1 unit of `crew`.
- **0 dependencies** (`depends_on = ()`).
- Controllable overlap via `span = max(dmax, round(horizon * (1 - 0.9 * overlap_factor)))`.

---

## 2. Extended Generator (`generate_extended`)

Designed for full-scale benchmark evaluation, Naive Greedy, Conflict-Aware Greedy, and Integer Linear Programming (ILP).

### Numeric Thresholds & Parameters

| Component | Parameter / Rule | Value / Distribution |
| :--- | :--- | :--- |
| **Corridors** | Number of corridors | `n_corridors` (default: 2) |
| | Traffic levels | Uniform choice of `low`, `medium`, `high` |
| | Assets per corridor | Uniform integer in `[3, 6]` (or `assets_per_corridor`) |
| **Asset Impact** | Low traffic corridor | Uniform integer in `[1, 3]` |
| | Medium traffic corridor | Uniform integer in `[2, 4]` |
| | High traffic corridor | Uniform integer in `[3, 5]` |
| **Resources** | Departments | `track`, `signal`, `power`, `civil` |
| | Capacities | `round(base_cap * resource_capacity_scale)` where base is in `[1, 3]` |
| | Availability | Full horizon `[0, horizon)` (100% >= 70% threshold) |
| **Timetable** | Low traffic base headway | 90 minutes |
| | Medium traffic base headway | 45 minutes |
| | High traffic base headway | 25 minutes |
| | Train occupancy duration | Uniform integer in `[5, 10]` minutes |
| | Night band `[0, 300)` | Headway $\times 4$ |
| | Morning peak `[420, 540)` | Headway $\div 2$ (minimum 12 min) |
| | Evening peak `[1020, 1140)` | Headway $\div 2$ (minimum 12 min) |
| **Tasks** | Duration | `round(base_d * corridor_load)` with base in `[10, 60]` min |
| | Criticality | $\text{clip}(\text{asset\_impact} + \text{noise}, 1, 5)$ where noise $\in \{-1, 0, 1\}$ |
| | Urgency | Uniform integer in `[1, 5]` |
| | Window slack factor | Multiplier $k \in [0.1, 4.0]$ negatively correlated with urgency |
| | Window placement | Higher urgency placed earlier in horizon |
| **Dependencies** | Precedence probability | 15% probability per task |
| | Precedence count | 1 or 2 prerequisites from earlier-windowed tasks |
| | Precedence validity | Candidate must satisfy `prereq_start + prereq_d + d <= task_window_end` |
| **Feasibility Sanity** | Minimum placeability | Scans for at least one train-free start in $[w_{start}, w_{end} - d]$ |
| | Window expansion | Expands up to 20 tries if blocked, else dropped and logged |

---

## 3. RNG Stream Isolation

All random numbers are drawn from SHA-256 isolated streams via `make_rng(seed, stream_name)`:
- `corridors`
- `resources`
- `trains`
- `tasks`
- `deps`
