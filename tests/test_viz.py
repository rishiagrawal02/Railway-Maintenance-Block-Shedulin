"""Focused visualization and comparison contracts, without experiment grids."""

import time
from unittest.mock import patch

import matplotlib.pyplot as plt
import pytest

from rbp import api
from rbp.viz.gantt import CRITICALITY_COLORS, gantt_figure


def test_gantt_empty_bars_trains_and_unscheduled():
    instance = api.generate_instance("simplified", n=20)
    fig, table = gantt_figure(instance, {}, show_trains=False)
    assert not fig.axes[0].collections
    assert len(table) == 20
    plt.close(fig)
    starts = {t["id"]: t["window_start"] for t in instance["tasks"]}
    corridor = instance["tasks"][0]["corridor_id"]
    instance["timetable"] = [
        {
            "corridor_id": corridor,
            "intervals": [{"start": i * 20, "end": i * 20 + 5} for i in range(5)],
        }
    ]
    fig, table = gantt_figure(instance, starts)
    ax = fig.axes[0]
    assert sum(len(c.get_paths()) for c in ax.collections) == 20
    assert len(ax.patches) == 5
    assert table.empty
    for collection in ax.collections:
        ids = [int(i) for i in collection.get_gid().split(":")[1].split(",")]
        for task_id, path in zip(ids, collection.get_paths()):
            task = next(t for t in instance["tasks"] if t["id"] == task_id)
            assert path.vertices[:, 0].min() == starts[task_id]
            assert path.vertices[:, 0].max() == starts[task_id] + task["duration"]
    assert len(CRITICALITY_COLORS) == 5
    plt.close(fig)


def test_thousand_tasks_render_quickly():
    instance = api.generate_instance("simplified", n=1000)
    starts = {t["id"]: t["window_start"] for t in instance["tasks"]}
    start = time.perf_counter()
    fig, _ = gantt_figure(instance, starts, show_trains=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    FigureCanvasAgg(fig).draw()
    assert sum(len(c.get_paths()) for c in fig.axes[0].collections) == 1000
    assert time.perf_counter() - start < 10
    plt.close(fig)


def test_comparison_failure_isolated_and_optimum_verified():
    instance = api.generate_instance(n=6)
    original = api.run

    def run(data, name, config):
        if name == "ILP-EXACT":
            raise RuntimeError("Simulated solver failure")
        return original(data, name, config)

    with patch("rbp.api.run", side_effect=run):
        results = api.compare(instance, ["NAIVE-GREEDY", "CA-GREEDY", "WIS-DP", "ILP-EXACT"])
    assert [r["metrics"]["status"] for r in results] == ["OK", "OK", "NOT_APPLICABLE", "ERROR"]
    assert all(r["metrics"]["gap"] is None for r in results)
    simple = api.generate_instance("simplified", n=6)
    results = api.compare(simple, ["WIS-DP", "CA-GREEDY"])
    optimum = results[0]["metrics"]["objective"]
    assert results[0]["metrics"]["optimal"]
    assert results[1]["metrics"]["gap"] == pytest.approx(
        (optimum - results[1]["metrics"]["objective"]) / optimum
    )
