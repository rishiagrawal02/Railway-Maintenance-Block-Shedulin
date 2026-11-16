"""Reusable Gantt figure and unscheduled-task table for domain or facade data."""

from dataclasses import asdict

import pandas as pd
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle

CRITICALITY_COLORS = {1: "#38BDF8", 2: "#14B8A6", 3: "#818CF8", 4: "#F59E0B", 5: "#EF4444"}


def gantt_figure(instance, schedule, show_trains=True):
    """Return (Figure, unscheduled DataFrame). One lane per corridor/asset.

    Accepts domain Instance/Schedule or facade instance/starts dictionaries.
    Task rectangles are batched by criticality; train patches span corridor lanes.
    """
    if not isinstance(instance, dict):
        tasks = [
            dict(
                id=t.id,
                corridor_id=t.corridor_id,
                asset_id=t.asset_id,
                duration=t.duration,
                criticality=t.criticality,
                window_start=t.window_start,
                window_end=t.window_end,
            )
            for t in instance.tasks
        ]
        timetables = [asdict(t) for t in instance.timetable]
        horizon = instance.horizon
    else:
        tasks, timetables, horizon = instance["tasks"], instance["timetable"], instance["horizon"]
    starts = schedule.starts if hasattr(schedule, "starts") else schedule
    starts = {int(k): v for k, v in starts.items()}
    lanes = sorted({(t["corridor_id"], t["asset_id"]) for t in tasks})
    positions = {lane: i for i, lane in enumerate(lanes)}
    fig = Figure(figsize=(12, max(3.6, min(24, len(lanes) * 0.35))), facecolor="#152238")
    ax = fig.subplots()
    ax.set_facecolor("#152238")
    for criticality, color in CRITICALITY_COLORS.items():
        vertices, ids = [], []
        for task in tasks:
            if task["id"] not in starts or task["criticality"] != criticality:
                continue
            start = starts[task["id"]]
            end = start + task["duration"]
            y = positions[(task["corridor_id"], task["asset_id"])]
            vertices.append(
                [(start, y - 0.28), (end, y - 0.28), (end, y + 0.28), (start, y + 0.28)]
            )
            ids.append(task["id"])
            if len(starts) <= 60:
                ax.text(
                    start + 1,
                    y,
                    f"T{task['id']}",
                    va="center",
                    fontsize=7,
                    color="#F8FAFC",
                    clip_on=True,
                    zorder=3,
                )
        if vertices:
            collection = PolyCollection(vertices, facecolors=color, zorder=2)
            collection.set_gid("tasks:" + ",".join(map(str, ids)))
            ax.add_collection(collection)
    if show_trains:
        for timetable in timetables:
            ys = [
                i
                for (corridor, asset), i in positions.items()
                if corridor == timetable["corridor_id"]
            ]
            if not ys:
                continue
            for interval in timetable["intervals"]:
                patch = Rectangle(
                    (interval["start"], min(ys) - 0.45),
                    interval["end"] - interval["start"],
                    max(ys) - min(ys) + 0.9,
                    facecolor="#64748B",
                    alpha=0.3,
                    zorder=1,
                )
                patch.set_gid("train")
                ax.add_patch(patch)
    ax.set_yticks(range(len(lanes)), [f"C{c} / A{a}" for c, a in lanes])
    ax.set_xlim(0, horizon)
    ax.set_ylim(max(0.5, len(lanes) - 0.5), -0.5)
    ax.set_xlabel("Minutes from horizon start", color="#94A3B8")
    ax.tick_params(colors="#94A3B8", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#2B405B")
    ax.legend(
        handles=[
            Patch(color=color, label=f"Criticality {level}")
            for level, color in CRITICALITY_COLORS.items()
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.15),
        ncol=5,
        facecolor="#152238",
        labelcolor="#F8FAFC",
        fontsize=8,
    )
    fig.tight_layout()
    columns = [
        "id",
        "corridor_id",
        "asset_id",
        "criticality",
        "duration",
        "window_start",
        "window_end",
    ]
    unscheduled = pd.DataFrame([t for t in tasks if t["id"] not in starts], columns=columns)
    return fig, unscheduled
