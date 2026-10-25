"""Tests for CA-GREEDY scoring terms and candidate placements (Milestone 5.2)."""

from rbp.algorithms.ca_terms import (
    ca_candidates,
    compute_fit_term,
    evaluate_ca_placement,
    lookahead_set,
)
from rbp.constraints.state import PlacementState
from rbp.generation.extended import generate_extended
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval

# ---------------------------------------------------------------------------
# Hand Fixture F
# ---------------------------------------------------------------------------


def _make_fixture_f() -> tuple[Instance, Task, Task, Task]:
    """Hand fixture F from Playbook Milestone 5.2:

    One corridor, one asset, no resource bottlenecks.
    X: w=31, [0,6), d=2
    Y: w=21, [0,2), d=2
    Z: w=21, [2,4), d=2
    """
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res = Resource(type="crew", capacity=10, availability=(Interval(0, 1440),))
    task_x = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=6, duration=2,
                  criticality=3, urgency=1, demands={}, depends_on=())
    task_y = Task(id=2, corridor_id=1, asset_id=1, window_start=0, window_end=2, duration=2,
                  criticality=2, urgency=1, demands={}, depends_on=())
    task_z = Task(id=3, corridor_id=1, asset_id=1, window_start=2, window_end=4, duration=2,
                  criticality=2, urgency=1, demands={}, depends_on=())
    inst = Instance(
        tasks=(task_x, task_y, task_z),
        corridors=(corridor,),
        resources=(res,),
        timetable=(),
        horizon=1440,
    )
    return inst, task_x, task_y, task_z


# ---------------------------------------------------------------------------
# T5.2-01: Candidates for X
# ---------------------------------------------------------------------------


def test_candidates_for_x():
    """T5.2-01: In Fixture F, ca_candidates(X) yields {0, 2, 4}."""
    inst, task_x, task_y, task_z = _make_fixture_f()
    state = PlacementState(inst)
    candidates = ca_candidates(inst, state, task_x, lookahead_tasks=[task_y, task_z])
    assert set(candidates) == {0, 2, 4}


# ---------------------------------------------------------------------------
# T5.2-02 & T5.2-03: Blocking penalty B
# ---------------------------------------------------------------------------


def test_blocking_at_start_0_and_4():
    """T5.2-02 & T5.2-03: At start=0, B=21 (kills Y); at start=4, B=0."""
    inst, task_x, task_y, task_z = _make_fixture_f()
    state = PlacementState(inst)
    lookahead = [task_y, task_z]

    # Start 0: kills Y
    _, b_0, _, _ = evaluate_ca_placement(inst, state, task_x, 0, lookahead, lambda_b=1.0)
    assert b_0 == 21.0

    # Start 4: kills neither
    _, b_4, _, _ = evaluate_ca_placement(inst, state, task_x, 4, lookahead, lambda_b=1.0)
    assert b_4 == 0.0


# ---------------------------------------------------------------------------
# T5.2-04: Scores at 0, 2, 4
# ---------------------------------------------------------------------------


def test_scores_fixture_f():
    """T5.2-04: In Fixture F, scores for X at 0, 2, 4 are 10, 10, 31."""
    inst, task_x, task_y, task_z = _make_fixture_f()
    state = PlacementState(inst)
    lookahead = [task_y, task_z]

    score_0, _, _, _ = evaluate_ca_placement(inst, state, task_x, 0, lookahead, lambda_b=1.0)
    score_2, _, _, _ = evaluate_ca_placement(inst, state, task_x, 2, lookahead, lambda_b=1.0)
    score_4, _, _, _ = evaluate_ca_placement(inst, state, task_x, 4, lookahead, lambda_b=1.0)

    assert score_0 == 10.0
    assert score_2 == 10.0
    assert score_4 == 31.0


# ---------------------------------------------------------------------------
# T5.2-05: Conflict-creation penalty C
# ---------------------------------------------------------------------------


def test_conflict_creation_penalty():
    """T5.2-05: When u has 5 feasible starts and placement removes 2, C = w_u * 2/5."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))

    # Tasks providing flush alignment candidate starts at 10, 20, 30, 40
    tasks_la = [
        Task(
            id=i,
            corridor_id=1,
            asset_id=1,
            window_start=i * 10 - 10,
            window_end=i * 10,
            duration=10,
            criticality=1,
            urgency=1,
            demands={},
            depends_on=(),
        )
        for i in range(1, 5)
    ]
    # u has window [0, 50), duration 10.
    # Candidates for u: window_start (0), latest_start (40), and flush alignments (10, 20, 30, 40)
    # -> exactly 5 candidate starts: [0, 10, 20, 30, 40]
    u = Task(
        id=10,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=50,
        duration=10,
        criticality=2,
        urgency=1,
        demands={},
        depends_on=(),
    )
    # t1 has window [0, 20), duration 20. Placing t1 at 0 removes starts 0 and 10 (2 starts removed)
    t1 = Task(
        id=99,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=20,
        duration=20,
        criticality=3,
        urgency=1,
        demands={},
        depends_on=(),
    )
    inst = Instance(
        tasks=tuple(tasks_la + [u, t1]),
        corridors=(corridor,),
        resources=(res,),
        timetable=(),
        horizon=1440,
    )
    state = PlacementState(inst)
    lookahead = tasks_la + [u]

    _, _, _, conflict_c = evaluate_ca_placement(inst, state, t1, 0, lookahead, lambda_c=1.0)
    # u before=5, after=3 -> 1 - 3/5 = 2/5
    expected_c = float(u.weight) * (2.0 / 5.0)
    assert abs(conflict_c - expected_c) < 1e-6


# ---------------------------------------------------------------------------
# T5.2-06: Resource fit term R
# ---------------------------------------------------------------------------


def test_resource_fit_term():
    """T5.2-06: Resource capacity 2, existing usage 1 over interval -> R = 0.5."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    res = Resource(type="crew", capacity=2, availability=(Interval(0, 1440),))
    # Existing task using 1 unit on asset 2
    existing = Task(id=1, corridor_id=1, asset_id=2, window_start=0, window_end=50, duration=20,
                    criticality=1, urgency=1, demands={"crew": 1}, depends_on=())
    new_task = Task(id=2, corridor_id=1, asset_id=1, window_start=0, window_end=50, duration=20,
                    criticality=1, urgency=1, demands={"crew": 1}, depends_on=())
    inst = Instance(
        tasks=(existing, new_task),
        corridors=(corridor,),
        resources=(res,),
        timetable=(),
        horizon=1440,
    )
    state = PlacementState(inst)
    state.place(existing, 0)

    fit_r = compute_fit_term(inst, state, new_task, 0)
    assert abs(fit_r - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# T5.2-07: Lookahead off (lookahead_k=0)
# ---------------------------------------------------------------------------


def test_lookahead_off():
    """T5.2-07: When lookahead_k=0, B=0, C=0, score = w_t + lambda_r*w_t*R."""
    inst, task_x, task_y, task_z = _make_fixture_f()
    state = PlacementState(inst)
    lookahead = lookahead_set(inst, state, lookahead_k=0)
    assert lookahead == []

    score, b, r, c = evaluate_ca_placement(inst, state, task_x, 0, lookahead)
    assert b == 0.0
    assert c == 0.0
    assert score == float(task_x.weight)


# ---------------------------------------------------------------------------
# T5.2-08: Lookahead cap
# ---------------------------------------------------------------------------


def test_lookahead_cap():
    """T5.2-08: lookahead_set with k=3 on 10 tasks returns at most 3 tasks."""
    inst = generate_extended(n=10, seed=1)
    state = PlacementState(inst)
    la = lookahead_set(inst, state, lookahead_k=3)
    assert len(la) == 3


# ---------------------------------------------------------------------------
# T5.2-09: Placement state restored exactly after evaluation
# ---------------------------------------------------------------------------


def test_state_restored_after_evaluation():
    """T5.2-09: Evaluating candidate placements leaves placement state identical to initial."""
    inst = generate_extended(n=15, seed=42)
    state = PlacementState(inst)

    task_to_place = inst.tasks[0]
    lookahead = lookahead_set(inst, state, lookahead_k=5)

    starts_before = dict(state.placed_starts)
    usage_before = {r.type: list(state._resource_usage[r.type]) for r in inst.resources}

    for s in ca_candidates(inst, state, task_to_place, lookahead)[:3]:
        evaluate_ca_placement(inst, state, task_to_place, s, lookahead)

    assert state.placed_starts == starts_before
    for r in inst.resources:
        assert state._resource_usage[r.type] == usage_before[r.type]


# ---------------------------------------------------------------------------
# T5.2-10: No feasible candidate
# ---------------------------------------------------------------------------


def test_no_feasible_candidate_returns_empty():
    """T5.2-10: Task whose window is completely blocked by trains returns [] without error."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tt = Timetable(corridor_id=1, intervals=(TrainInterval(0, 50),))
    task = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=50, duration=30,
                criticality=3, urgency=1, demands={}, depends_on=())
    inst = Instance(
        tasks=(task,),
        corridors=(corridor,),
        resources=(res,),
        timetable=(tt,),
        horizon=1440,
    )
    state = PlacementState(inst)
    candidates = ca_candidates(inst, state, task)
    assert candidates == []
