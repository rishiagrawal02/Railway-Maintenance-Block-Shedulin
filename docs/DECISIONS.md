# Implementation decisions D1–D12

These choices are transcribed from the development playbook and checked against
implementation. Defaults and experiment overrides are distinguished explicitly.

| ID | Implemented choice | Evidence |
| --- | --- | --- |
| D1 | Score <= threshold selects WIS-DP for simplified inputs; extended inputs use ILP when enabled and n <= 150. Otherwise choose CA-GREEDY. `exact_route_for_extended: none` disables the extended exact route; optional `simplified_always_dp` bypasses the threshold. | [Selector](../src/rbp/selector/selector.py), [defaults](../config/defaults.yaml) |
| D2 | Threshold 0.715, version 1; five equal alpha weights. Threshold grid calibration uses disjoint seeds; no ML model. Equal alpha weights are configured, not claimed to have been learned. | [Calibration record](../config/threshold.json), [evaluation](../reports/selector_eval.md) |
| D3 | Integer minutes, half-open intervals, default horizon 1440. | [Intervals](../src/rbp/models/interval.py) |
| D4 | Integer task weight = 10*criticality + urgency; both input values 1–5. | [Task](../src/rbp/models/task.py) |
| D5 | Same-asset intervals cannot overlap; no compatibility matrix. | [Predicates](../src/rbp/constraints/predicates.py) |
| D6 | All prerequisites must be scheduled and finish before the dependent starts; input graph must be acyclic. | [Input checks](../src/rbp/io/input_checks.py), [validator](../src/rbp/validation/validator.py) |
| D7 | Integer resource capacity and full-duration demand; availability intervals constrain placement. | [Resource](../src/rbp/models/resource.py), C4 validator |
| D8 | One corridor; one capacity-one resource available throughout the horizon; each task demands one, has a fixed window, and has no dependencies; no trains. | [Simplified predicate](../src/rbp/models/simplified.py) |
| D9 | GitHub phase branches; phase merges into main; GitHub Actions CI. Current release checks use Python 3.12 and include slow tests. | [CI](../.github/workflows/ci.yml) |
| D10 | Score = w - lambda_b*B + lambda_r*w*R - lambda_c*C. Defaults 1.0/0.5/0.5. Solver default and experiment k=5; UI config k=20. No optimality guarantee. | [CA notes](CA_GREEDY.md), [defaults](../config/defaults.yaml), [E2](../config/experiments/e2.yaml) |
| D11 | Oracle studies n<=16; gap studies n=20–200; E2 up to 5000; experiment ILP uses one worker, 30s search budget and a deterministic search cap. | [Experiment instructions](EXPERIMENTS.md) |
| D12 | NAIVE-GREEDY processes priority order once and skips tasks with unplaced prerequisites. | [Baseline](../src/rbp/algorithms/naive_greedy.py) |

The selector always returns its actual route and reason; tests cover equality at
the threshold, size-guard fallback, override flags and UI reason preservation.
Budget-limited CP-SAT is not described as a proven optimum. The configured search
time limit is not a hard end-to-end deadline: model construction is outside it.
