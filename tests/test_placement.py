"""Tests for placement engine (Milestone 5.1)."""


from rbp.algorithms.placement import earliest_feasible_start, event_starts
from rbp.constraints.predicates import is_feasible
from rbp.constraints.state import PlacementState
from rbp.generation.extended import generate_extended


def _brute_force_earliest_start(instance, state, task) -> int | None:
    """Ground truth: scan every integer minute from window_start to latest_start."""
    latest = task.window_end - task.duration
    for s in range(task.window_start, latest + 1):
        if is_feasible(instance, state, task, s):
            return s
    return None


def test_events_equal_brute_scan():
    """T5.1-08: earliest_feasible_start using event points matches integer minute scan

    across 200 random probes on extended instances.
    """
    total_probes = 0
    mismatches = []

    for seed in range(1, 26):
        inst = generate_extended(n=15, seed=seed)
        state = PlacementState(inst)

        # Place a few tasks in state to create blocking intervals
        for t in inst.tasks[:5]:
            cand = earliest_feasible_start(inst, state, t)
            if cand is not None:
                state.place(t, cand)

        # Probe remaining tasks
        for t in inst.tasks[5:]:
            total_probes += 1
            event_res = earliest_feasible_start(inst, state, t)
            brute_res = _brute_force_earliest_start(inst, state, t)
            if event_res != brute_res:
                mismatches.append(
                    f"Seed {seed}, Task {t.id}: event={event_res} != brute={brute_res}, "
                    f"window=[{t.window_start},{t.window_end}), dur={t.duration}, "
                    f"events={event_starts(inst, state, t)}"
                )

    assert total_probes >= 200
    assert mismatches == [], "Found mismatches:\n" + "\n".join(mismatches[:5])
