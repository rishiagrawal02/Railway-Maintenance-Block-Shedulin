"""Differential fuzz testing: algorithm predicates versus independent validator (Milestone 3.3)."""

import random

from rbp.constraints import PlacementState, is_feasible
from rbp.generation.extended import generate_extended
from rbp.models import Schedule
from rbp.validation import validate_schedule

# ---------------------------------------------------------------------------
# T3.3-07: Predicate versus validator differential fuzz test
# ---------------------------------------------------------------------------


def test_predicates_vs_validator_differential_fuzz():
    """T3.3-07: Across 20 instances with 200 probes each (4000+ probes),

    is_feasible always agrees with validate_schedule.
    """
    total_probes = 0
    disagreements: list[str] = []

    for seed in range(1, 21):
        instance = generate_extended(n=25, seed=seed)
        state = PlacementState(instance)
        rng = random.Random(seed * 1000 + 7)

        # Partially populate schedule with some valid placements
        unplaced = list(instance.tasks)
        rng.shuffle(unplaced)

        for _ in range(200):
            total_probes += 1

            # Pick a task to probe
            task = rng.choice(instance.tasks)
            # Pick a random candidate start time across horizon
            candidate_start = rng.randint(0, instance.horizon)

            # If task is currently placed in state, temporarily unplace it
            was_placed = state.is_placed(task.id)
            old_start = state.start_of(task.id) if was_placed else None
            if was_placed:
                state.unplace(task)

            # Check algorithm predicate verdict
            pred_verdict = is_feasible(instance, state, task, candidate_start)

            # Build tentative schedule and check independent validator verdict
            tentative_starts = dict(state.placed_starts)
            tentative_starts[task.id] = candidate_start
            tentative_sched = Schedule(starts=tentative_starts)
            val_report = validate_schedule(instance, tentative_sched)
            val_verdict = val_report.valid

            # Compare verdicts
            if pred_verdict != val_verdict:
                disagreements.append(
                    f"Seed {seed}, Task {task.id} at start={candidate_start}: "
                    f"predicates={pred_verdict}, validator={val_verdict}, "
                    f"violations={[v.code for v in val_report.violations]}"
                )

            # With 30% probability, if feasible, keep the placement in state to evolve it
            # Otherwise restore original placement state
            if pred_verdict and rng.random() < 0.3:
                state.place(task, candidate_start)
            elif was_placed:
                assert old_start is not None
                state.place(task, old_start)

    assert total_probes >= 4000, f"Expected at least 4000 probes, got {total_probes}"
    assert disagreements == [], (
        f"Found {len(disagreements)} disagreements between predicates and validator:\n"
        + "\n".join(disagreements[:10])
    )
