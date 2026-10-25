# CA-GREEDY: Conflict-Aware Greedy Heuristic Documentation

## Overview

The `CA-GREEDY` algorithm (Milestone 5.3) enhances the baseline greedy heuristic by incorporating look-ahead conflict awareness and resource packing logic. While `NAIVE-GREEDY` places each ready task at its earliest feasible start time without considering subsequent tasks, `CA-GREEDY` evaluates a candidate set of start times for each task and selects the start that maximizes a multi-term objective score.

---

## 1. Scoring Function (Decision D10)

For a task $t$ evaluated at a candidate start time $s$, the score is computed as:

$$\text{Score}(t, s) = w_t - \lambda_b \cdot B + \lambda_r \cdot w_t \cdot R - \lambda_c \cdot C$$

Where:
1. **Base Priority ($w_t$)**: The intrinsic weight of task $t$, derived from its criticality and urgency ($w_t = 10 \cdot c_t + u_t$).
2. **Blocking Penalty ($B$)**:
   $$B = \sum_{u \in \text{Lookahead}, \text{count}_{\text{after}}(u) = 0} w_u$$
   Penalizes placing $t$ at $s$ if doing so completely blocks any upcoming task $u$ in the lookahead window (feasible candidate count drops from $\ge 1$ to 0).
3. **Resource Fit Bonus ($R \in [0, 1]$)**:
   $$R = \frac{1}{|D_t|} \sum_{r \in D_t} \min\left(1.0, \frac{\text{mean usage of } r \text{ over } [s, s + d_t)}{\text{capacity}(r)}\right)$$
   Rewards placing $t$ during intervals when required resources are already partially utilized by other tasks, packing resource demand and leaving larger contiguous blocks free for future tasks.
4. **Conflict-Creation Penalty ($C$)**:
   $$C = \sum_{u \in \text{Lookahead}, 0 < \text{count}_{\text{after}}(u) < \text{count}_{\text{before}}(u)} w_u \cdot \left(1 - \frac{\text{count}_{\text{after}}(u)}{\text{count}_{\text{before}}(u)}\right)$$
   Penalizes placements that squeeze the feasible start options of upcoming tasks, weighted by the fraction of candidates eliminated.

---

## 2. Hyperparameter Settings

The calibrated default weights are:
- $\lambda_b = 1.0$: Full penalty for completely starving a lookahead task.
- $\lambda_r = 0.5$: Moderate incentive to pack resource usage.
- $\lambda_c = 0.5$: Proportional penalty for narrowing lookahead flexibility.
- $k = 5$: Lookahead depth (evaluates the top 5 highest-priority remaining unplaced tasks).
- `allow_skip_negative = False`: Tasks are placed at their best available candidate start even if the net score is negative, unless explicitly configured to skip.

---

## 3. Candidate Start Generation

To evaluate continuous time efficiently, candidate start times are generated from:
1. `event_starts`: Boundary event points from train blocking intervals and already placed maintenance blocks on the same asset.
2. `latest_start`: $W_t^{\text{end}} - d_t$.
3. Flush alignments with lookahead tasks on the same asset:
   - $u.W^{\text{end}}$
   - $u.W^{\text{start}} - d_t$

All candidate starts are validated with `is_feasible` (C1–C5) before score evaluation. Ties in score are broken by choosing the earliest start time.

---

## 4. Empirical Evaluation: Calibration Seeds 1000–1029

Across 30 calibration instances generated with `generate_extended(n=20)`:

| Metric | NAIVE-GREEDY | CA-GREEDY | Improvement |
| :--- | :--- | :--- | :--- |
| **Mean Objective** | 491.20 | 524.47 | **+33.27 (+6.77%)** |
| **Wins** | - | 18 / 30 (60.0%) | - |
| **Ties** | - | 12 / 30 (40.0%) | - |
| **Losses** | - | 0 / 30 (0.0%) | - |

### Per-Seed Results

| Seed | NAIVE | CA-GREEDY | Diff | Status |
| :---: | :---: | :---: | :---: | :---: |
| 1000 | 461 | 486 | +25 | WIN |
| 1001 | 499 | 499 | +0 | TIE |
| 1002 | 383 | 383 | +0 | TIE |
| 1003 | 451 | 482 | +31 | WIN |
| 1004 | 384 | 507 | +123 | WIN |
| 1005 | 477 | 543 | +66 | WIN |
| 1006 | 376 | 376 | +0 | TIE |
| 1007 | 332 | 332 | +0 | TIE |
| 1008 | 465 | 500 | +35 | WIN |
| 1009 | 609 | 660 | +51 | WIN |
| 1010 | 414 | 448 | +34 | WIN |
| 1011 | 449 | 449 | +0 | TIE |
| 1012 | 452 | 484 | +32 | WIN |
| 1013 | 502 | 608 | +106 | WIN |
| 1014 | 511 | 512 | +1 | WIN |
| 1015 | 513 | 513 | +0 | TIE |
| 1016 | 475 | 508 | +33 | WIN |
| 1017 | 544 | 638 | +94 | WIN |
| 1018 | 578 | 578 | +0 | TIE |
| 1019 | 397 | 397 | +0 | TIE |
| 1020 | 634 | 634 | +0 | TIE |
| 1021 | 394 | 464 | +70 | WIN |
| 1022 | 484 | 614 | +130 | WIN |
| 1023 | 693 | 747 | +54 | WIN |
| 1024 | 485 | 485 | +0 | TIE |
| 1025 | 423 | 447 | +24 | WIN |
| 1026 | 634 | 634 | +0 | TIE |
| 1027 | 641 | 685 | +44 | WIN |
| 1028 | 519 | 564 | +45 | WIN |
| 1029 | 557 | 557 | +0 | TIE |

---

## 5. Architectural Compliance

- Algorithm imports are restricted to domain models (`rbp.models`) and constraint state/predicates (`rbp.constraints`).
- The validator (`rbp.validation`) is completely independent and only called by integration tests.
- Execution is strictly deterministic across runs for any given instance.
