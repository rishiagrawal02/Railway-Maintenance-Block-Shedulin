"""Presentation helpers for the RAILOPT prototype. No scheduling decisions."""

import base64
from html import escape
from pathlib import Path

from matplotlib.figure import Figure

PALETTE = ["#38BDF8", "#14B8A6", "#818CF8", "#F59E0B", "#F472B6"]


def icon(name):
    path = Path(__file__).parent / "assets" / f"{name}.svg"
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/svg+xml;base64,{raw}" alt="" />'


def brand():
    return (
        f'<div class="brand">{icon("imgIconTrain1")}<div>RAILOPT<small>'
        "RAILWAY MAINTENANCE<br>BLOCK SCHEDULING</small></div></div>"
    )


def heading(title, subtitle, instance_id):
    return (
        f'<div class="page-heading"><div><div class="eyebrow">OPERATIONS PLATFORM</div>'
        f"<h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>"
        f'<span class="dataset-chip">DATASET / {escape(instance_id[:8])}</span></div>'
    )


def card(label, value, detail, asset="imgIconChart"):
    return (
        f'<div class="kpi"><div class="kpi-label">{escape(label)}{icon(asset)}</div>'
        f'<div class="kpi-value">{escape(str(value))}</div>'
        f'<div class="kpi-detail">{escape(detail)}</div></div>'
    )


def stylesheet():
    return """<style>
    .stApp {background:#0B1220;color:#F8FAFC}
    [data-testid="stSidebar"] {background:#0E192B;border-right:1px solid #2B405B}
    [data-testid="stSidebar"]>div:first-child {padding-top:1.2rem}
    .block-container {padding-top:2rem;padding-bottom:3rem;max-width:1700px}
    header[data-testid="stHeader"] {background:transparent}
    h1,h2,h3 {letter-spacing:-.035em}
    h1 {font-size:30px!important;font-weight:600!important;padding:0!important}
    h3 {font-size:20px!important}
    .brand {display:flex;gap:13px;align-items:center;margin:12px 0 28px;font-weight:700;
      font-size:27px;letter-spacing:.045em}
    .brand img {width:36px;height:36px}
    .brand small {display:block;font-size:9px;line-height:1.6;color:#94A3B8;letter-spacing:.13em}
    .page-heading {display:flex;justify-content:space-between;align-items:center;margin:0 0 22px}
    .page-heading p {color:#94A3B8;font-size:14px;margin:7px 0 0}
    .eyebrow {font-size:10px;letter-spacing:.17em;color:#38BDF8;margin-bottom:9px}
    .dataset-chip {font:12px monospace;color:#94A3B8;border:1px solid #2B405B;
      padding:10px 14px;border-radius:8px;white-space:nowrap}
    .kpi {border:1px solid #2B405B;background:#152238;border-radius:16px;padding:20px;
      min-height:148px;margin-bottom:16px}
    .kpi-label {display:flex;align-items:center;justify-content:space-between;
      color:#94A3B8;font-size:13px}
    .kpi-label img {width:22px;height:22px}
    .kpi-value {font-size:34px;font-weight:600;letter-spacing:-.04em;margin:8px 0 3px}
    .kpi-detail {font-size:12px;color:#64748B}
    [data-testid="stVerticalBlockBorderWrapper"]>div {border-color:#2B405B!important;
      border-radius:16px!important;background:#152238}
    button {border-radius:8px!important}
    [data-testid="stSidebar"] [data-testid="stRadio"] label {padding:8px 0}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
      background:#1A365B;border-radius:8px;border-left:3px solid #38BDF8}
    .workflow {border-left:2px solid #38BDF8;padding:12px 16px;color:#94A3B8;font-size:13px}
    @media(max-width:800px) {.page-heading {display:block}.dataset-chip {display:inline-block;
      margin-top:12px}.block-container {padding:1rem}.kpi {padding:14px}}
    </style>"""


def _figure(height=3.6):
    fig = Figure(figsize=(10, height), facecolor="#152238", layout="constrained")
    ax = fig.subplots()
    ax.set_facecolor("#152238")
    ax.tick_params(colors="#94A3B8", labelsize=9)
    ax.xaxis.label.set_color("#94A3B8")
    ax.yaxis.label.set_color("#94A3B8")
    for spine in ax.spines.values():
        spine.set_color("#2B405B")
    ax.grid(axis="x", color="#2B405B", linewidth=0.5)
    ax.set_axisbelow(True)
    return fig, ax


def timeline(instance, rows, corridor=None, occupancy=True):
    from rbp.viz.gantt import gantt_figure

    selected = [r for r in rows if corridor is None or r["corridor_id"] == corridor]
    subset = {**instance, "tasks": selected}
    starts = {r["id"]: r["start"] for r in selected if r["start"] is not None}
    return gantt_figure(subset, starts, show_trains=occupancy)[0]


def bars(labels, values, xlabel):
    fig, ax = _figure(3)
    ax.barh([str(label) for label in labels], values, color=PALETTE[0])
    ax.set_xlabel(xlabel)
    ax.invert_yaxis()
    return fig


def resource_chart(instance, rows):
    fig, ax = _figure()
    for index, resource in enumerate(instance["resources"]):
        events = {0: 0, instance["horizon"]: 0}
        for row in rows:
            if row["start"] is not None:
                demand = row["demands"].get(resource["type"], 0)
                events[row["start"]] = events.get(row["start"], 0) + demand
                events[row["end"]] = events.get(row["end"], 0) - demand
        used, values = 0, []
        times = sorted(events)
        for time in times:
            used += events[time]
            values.append(used)
        color = PALETTE[index % len(PALETTE)]
        ax.step(times, values, where="post", color=color, label=resource["type"])
        ax.axhline(resource["capacity"], color=color, linestyle="--", alpha=0.6)
    if instance["resources"]:
        ax.legend(facecolor="#152238", labelcolor="#F8FAFC", fontsize=8)
    ax.set_xlabel("Minutes · dashed lines = resource capacities")
    ax.set_ylabel("Units in use")
    return fig
