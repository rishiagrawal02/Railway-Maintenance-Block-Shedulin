# Complexity derived from the implementation

These are bounds for the actual code, not promises inferred from timing slopes.
Let n be tasks, H horizon minutes, R resource types, r demanded resource types per
task, d maximum duration, p prerequisites per task, T train intervals scanned on
a corridor, c timetable entries, A availability intervals, m candidate starts
per task and k lookahead tasks. Hash/dictionary access is expected O(1).

## WIS-DP

[solve_wis_dp](../src/rbp/algorithms/wis_dp.py) sorts tasks by end time in O(n log n),
performs n binary predecessor searches in O(n log n), fills an O(n) DP table and
reconstructs at most n tasks. Time **O(n log n)** and extra space **O(n)** for the
simplified-input solver. It is not applicable to extended instances.
Admission additionally checks resource availability coverage in O(A log A) time;
the generated simplified family has one availability interval.

## Shared placement costs

[Instance lookups](../src/rbp/models/instance.py) scan tuples: task lookup O(n),
resource lookup O(R), timetable lookup O(c). They are not indexed dictionaries.
[Feasibility](../src/rbp/constraints/predicates.py) costs
`F = O(c + T + log(n+1) + rR + rd + pn)` in the worst case: C2 scans trains,
C3 bisects asset intervals, C4 scans every minute for each demanded resource,
and C5 performs linear task lookups. The **resource check alone is O(duration)**
per resource, not the complete predicate when input dimensions grow.

[event_starts](../src/rbp/algorithms/placement.py) gathers train ends, placed-task
ends, dependency ends and resource availability starts, then sorts unique
candidates. At most `m <= 1 + T + 2n + p + A` candidates before clipping (a loose
bound; duplicates reduce it). A safe generation bound is
`G = O(c + T + n^2 + nr + pn + rR + A + m log(m+1))`.
The n-squared term comes from scanning placed IDs and calling linear `Instance.task`.

[PlacementState](../src/rbp/constraints/state.py) allocates O(RH+n) working space.
Initialization takes O(RH+L), where L counts all availability minutes visited
(including overlaps). Sorted-list insertion/removal costs O(n), not O(log n),
plus O(rd) resource-array updates. Let `P = O(n+rd)`.

## NAIVE-GREEDY

[solve_naive_greedy](../src/rbp/algorithms/naive_greedy.py) sorts once, visits each
task once, and tries up to m event starts. A safe bound is
`O(RH + L + n log n + n(G + mF + P) + n^2)` with O(RH+n+m) working space.
The final n-squared term includes objective recomputation through linear lookups.
With fixed auxiliary dimensions, sparse dependencies, and m=O(n), the current
linear lookup scans give a conservative O(n^3) bound; observed growth can be much
lower because candidates are clipped and feasibility exits early. Single-pass
unmet dependencies cause skips. There is no optimality guarantee.

## CA-GREEDY

[solve_ca_greedy](../src/rbp/algorithms/ca_greedy.py) manages a ready heap but also
sorts all remaining tasks for each lookahead selection: O(n^2 log n) across the
run, plus dependency-edge processing. It adds at most 1+2k candidate alignments.
[Scoring](../src/rbp/algorithms/ca_terms.py) recomputes feasible candidates for up
to k lookahead tasks before and after every tentative placement.

One scoring call performs **O(k*m) feasibility checks**, not O(k*m) total time.
Including generation and state updates it costs `O(k(G+mF) + rd + P)`.
A safe overall bound is
`O(RH+L+n^2 log n+np+n*(G+mF+m*(k*(G+mF)+rd+P))+n^2)`.
Working space is O(RH+n+np+m+k); lookahead candidates are processed sequentially.
This explains why increasing k, candidate counts or minute durations matters.
**CA-GREEDY is a heuristic with no optimality guarantee.**

## ILP-EXACT / CP-SAT

[ilp_exact.py](../src/rbp/algorithms/ilp_exact.py) enumerates possible integer start
minutes to build allowed domains; domain construction can cost
O(nH(T+rd)) plus state/model setup. Combinatorial selection and placement search
has exponential worst-case complexity (roughly up to (H+1)^n assignments before
constraints/pruning), not a polynomial scalability guarantee. A time budget limits
search; FEASIBLE/UNKNOWN do not prove optimality. Model preprocessing also consumes
time outside the solver search budget.

## Selector

[features.py](../src/rbp/selector/features.py) groups tasks by asset and sorts
2n interval endpoints: O(n log n) for conflict-density extraction. Size is O(1),
tightness O(n), resource contention O(Rn+A), and corridor utilization O(n+T+c).
Thus extraction is **O(n log n)** when resource counts and auxiliary data are
fixed or linear-size; the general bound is O(n log n+Rn+A+T+c), with O(n+c) extra
space. The weighted score and threshold comparison use five values: O(1).
The selector is deterministic rule-based routing calibrated on held-out seeds,
not a learned predictive model.

## Check against E2 measurements

The committed [runtime slopes](../reports/runtime_slopes.csv) use finite log-log
fits: WIS-DP 0.841; NAIVE-GREEDY 2.043 simplified / 2.084 extended; CA-GREEDY 1.919 /
1.679. These are consistent with finite workloads below conservative upper bounds,
not estimates proving those bounds tight. Fixed horizon, early exits, linear
lookup overhead and changing actual/requested task counts all affect measurements.
The extended ILP fit 2.386 uses only two sizes and six proven-optimal runs; it does
not contradict exponential worst-case search. Simplified ILP has insufficient
sizes for a slope. Do not rewrite theoretical bounds to match these slopes.
