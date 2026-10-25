"""Tests for complexity features and weighted score (Milestone 8.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rbp.generation import generate_extended, generate_simplified
from rbp.models.corridor import Corridor
from rbp.models.instance import Instance
from rbp.models.interval import Interval
from rbp.models.resource import Resource
from rbp.models.task import Task
from rbp.models.timetable import Timetable
from rbp.selector.features import (
    Features,
    _count_overlapping_pairs_reference,
    _count_overlapping_pairs_sweep,
    complexity_score,
    compute_features,
    feature_f1_size,
    feature_f3_resource_contention,
    feature_f4_window_tightness,
    load_alpha,
)


def _make_hand_fixture_h() -> Instance:
    """Hand fixture H from playbook spec:

    Horizon 100, one corridor, one train [40, 50).
    Asset A (id 1): task 1 [0, 20) d10, task 2 [10, 30) d10.
    Asset B (id 2): task 3 [0, 50) d25, task 4 [60, 80) d20.
    One resource type R, capacity 2, available [0, 100), each task demands 1.
    """
    t1 = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=20, duration=10,
        criticality=1, urgency=0, demands={"R": 1},
    )
    t2 = Task(
        id=2, corridor_id=1, asset_id=1, window_start=10, window_end=30, duration=10,
        criticality=1, urgency=0, demands={"R": 1},
    )
    t3 = Task(
        id=3, corridor_id=1, asset_id=2, window_start=0, window_end=50, duration=25,
        criticality=1, urgency=0, demands={"R": 1},
    )
    t4 = Task(
        id=4, corridor_id=1, asset_id=2, window_start=60, window_end=80, duration=20,
        criticality=1, urgency=0, demands={"R": 1},
    )

    c1 = Corridor(id=1, traffic_level="MEDIUM", asset_ids=(1, 2))
    r1 = Resource(type="R", capacity=2, availability=(Interval(0, 100),))
    tt1 = Timetable(corridor_id=1, intervals=(Interval(40, 50),))

    return Instance(
        tasks=(t1, t2, t3, t4),
        corridors=(c1,),
        resources=(r1,),
        timetable=(tt1,),
        horizon=100,
        meta={"seed": 42},
    )


def test_t8_1_01_fixture_features():
    """T8.1-01: Fixture features on Hand fixture H match expected exact values:

    f1: 0.02, f2: 0.50, f3: 0.325, f4: 0.625, f5: 0.75.
    """
    inst = _make_hand_fixture_h()
    feats = compute_features(inst, n_ref=200)

    assert feats.f1_size == pytest.approx(0.02, abs=1e-4)
    assert feats.f2_conflict_density == pytest.approx(0.50, abs=1e-4)
    assert feats.f3_resource_contention == pytest.approx(0.325, abs=1e-4)
    assert feats.f4_window_tightness == pytest.approx(0.625, abs=1e-4)
    assert feats.f5_corridor_utilization == pytest.approx(0.75, abs=1e-4)


def test_t8_1_02_fixture_score():
    """T8.1-02: Fixture score on Hand fixture H with equal alpha=0.2 matches 0.444."""
    inst = _make_hand_fixture_h()
    feats = compute_features(inst, n_ref=200)
    score = complexity_score(feats, alpha=(0.2, 0.2, 0.2, 0.2, 0.2))

    assert score == pytest.approx(0.444, abs=1e-4)


def test_t8_1_03_bounds():
    """T8.1-03: Every feature must be in [0, 1] on 200 generated instances."""
    for seed in range(100):
        s_inst = generate_simplified(n=10, seed=seed)
        feats_s = compute_features(s_inst)
        for val in feats_s.as_tuple():
            assert 0.0 <= val <= 1.0

        e_inst = generate_extended(n=10, seed=seed)
        feats_e = compute_features(e_inst)
        for val in feats_e.as_tuple():
            assert 0.0 <= val <= 1.0


def test_t8_1_04_empty_instance():
    """T8.1-04: Empty instance (n=0): all features are 0.0 with no division error."""
    inst = Instance(tasks=(), corridors=(), resources=(), timetable=(), horizon=100)
    feats = compute_features(inst)

    assert feats.f1_size == 0.0
    assert feats.f2_conflict_density == 0.0
    assert feats.f3_resource_contention == 0.0
    assert feats.f4_window_tightness == 0.0
    assert feats.f5_corridor_utilization == 0.0


def test_t8_1_05_size_clipping():
    """T8.1-05: Size clipping: when n=1000 and n_ref=200, f1 is clipped to 1.0."""
    tasks = tuple(
        Task(
            id=i, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=10,
            criticality=1, urgency=0,
        )
        for i in range(1000)
    )
    inst = Instance(tasks=tasks, horizon=1000)
    f1 = feature_f1_size(inst, n_ref=200)
    assert f1 == 1.0


def test_t8_1_06_f2_sweep_equals_brute_force():
    """T8.1-06: f2 sweep-line algorithm matches O(n^2) brute force on 50 instances."""
    for seed in range(50):
        inst = generate_extended(n=15, seed=seed)
        asset_tasks: dict[int, list[Task]] = {}
        for t in inst.tasks:
            asset_tasks.setdefault(t.asset_id, []).append(t)

        for tasks in asset_tasks.values():
            sweep_count = _count_overlapping_pairs_sweep(tasks)
            ref_count = _count_overlapping_pairs_reference(tasks)
            assert sweep_count == ref_count


def test_t8_1_07_zero_availability_guard():
    """T8.1-07: Resource with no availability but demanded returns f3 = 1.0 without crash."""
    t1 = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=30,
        criticality=1, urgency=0, demands={"RES_ZERO": 1},
    )
    r_zero = Resource(type="RES_ZERO", capacity=2, availability=())
    inst = Instance(tasks=(t1,), resources=(r_zero,), horizon=100)

    f3 = feature_f3_resource_contention(inst)
    assert f3 == 1.0


def test_t8_1_08_alpha_validation_failure(tmp_path: Path):
    """T8.1-08: Alpha validation error when alpha sums to 0.9 or has 4 entries."""
    bad_cfg_sum = tmp_path / "bad_sum.json"
    bad_cfg_sum.write_text(json.dumps({"alpha": [0.2, 0.2, 0.2, 0.2, 0.1]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Alpha weights must sum to 1.0"):
        load_alpha(bad_cfg_sum)

    bad_cfg_len = tmp_path / "bad_len.json"
    bad_cfg_len.write_text(json.dumps({"alpha": [0.25, 0.25, 0.25, 0.25]}), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 5 numbers"):
        load_alpha(bad_cfg_len)

    feats = Features(0.1, 0.2, 0.3, 0.4, 0.5)
    with pytest.raises(ValueError, match="Alpha must have exactly 5"):
        complexity_score(feats, alpha=[0.5, 0.5])
    with pytest.raises(ValueError, match="Alpha must sum to 1.0"):
        complexity_score(feats, alpha=[0.2, 0.2, 0.2, 0.2, 0.1])


def test_t8_1_09_knob_monotonicity():
    """T8.1-09: Lower window_slack_factor increases f4 window tightness across 20 seeds."""
    tighter_higher_count = 0
    for seed in range(20):
        # Slack 0.5 (tighter) vs Slack 2.0 (looser)
        inst_tight = generate_extended(n=16, seed=seed, window_slack_factor=0.5)
        inst_loose = generate_extended(n=16, seed=seed, window_slack_factor=2.0)

        f4_tight = feature_f4_window_tightness(inst_tight)
        f4_loose = feature_f4_window_tightness(inst_loose)
        if f4_tight >= f4_loose:
            tighter_higher_count += 1

    # On majority of seeds, tightness is strictly greater or equal
    assert tighter_higher_count >= 18


def test_t8_1_10_determinism_and_no_mutation():
    """T8.1-10: Computing features twice gives equal values and leaves instance unchanged."""
    inst = generate_extended(n=12, seed=888)
    initial_tasks = list(inst.tasks)

    feats1 = compute_features(inst)
    feats2 = compute_features(inst)

    assert feats1 == feats2
    assert list(inst.tasks) == initial_tasks
