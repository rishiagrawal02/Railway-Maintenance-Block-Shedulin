"""RAILOPT: presentation-only Streamlit shell over rbp.api."""

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import rbp.api as api
import rbp.viz as viz

PAGES = {
    "Command Center": "Your maintenance operations, at a glance.",
    "Dataset Studio": "Generate, inspect and validate a scheduling instance.",
    "Scheduling Workspace": "Plan maintenance blocks around live instance constraints.",
    "Adaptive Intelligence": "Understand the features behind the algorithm recommendation.",
    "Performance Analytics": "Compare measured results on the current dataset.",
    "Validation Center": "Independent verification of every scheduled maintenance block.",
}


@st.cache_data(max_entries=64, show_spinner=False)
def cached_run(instance_hash, instance, algorithm, config):
    if instance_hash != api.instance_hash(instance):
        raise api.APIError("Instance cache key mismatch.")
    return api.run(instance, algorithm, config)


@st.cache_data(max_entries=32, show_spinner=False)
def cached_selection(instance):
    return api.select(instance)


def render_figure(fig):
    try:
        st.pyplot(fig)
    finally:
        plt.close(fig)


def replace_instance(instance):
    st.session_state.instance = instance
    st.session_state.result = None
    st.session_state.comparison = []


def run_current(algorithm, config):
    instance = st.session_state.instance
    with st.spinner(f"Running {algorithm} and validating its schedule…"):
        st.session_state.result = cached_run(
            api.instance_hash(instance), instance, algorithm, config
        )


def metrics(result):
    if result is None:
        st.info("No schedule yet. Choose an algorithm and click Run in the sidebar.")
        return
    report = result["validation"]
    if report["valid"]:
        st.success(f"Schedule validated · {report['total_violations']} violations")
    else:
        st.error(f"Schedule has {report['total_violations']} violations. Open Validation Center.")
    if result["metrics"]["status"] == "TIMEOUT":
        st.warning("Solver time limit reached. This schedule is not proven optimal.")
    st.dataframe(pd.DataFrame([result["metrics"]]), hide_index=True, width="stretch")


def kpis(instance, result):
    m = result["metrics"] if result else {}
    entries = [
        ("Maintenance tasks", len(instance["tasks"]), "Validated instance", "imgIconDatabase"),
        ("Scheduled blocks", m.get("scheduled", "—"), "Current schedule", "imgIconCalendar"),
        ("Active corridors", len(instance["corridors"]), "Network coverage", "imgIconTrain"),
        (
            "Weighted coverage",
            f"{m['coverage']:.1%}" if m else "—",
            "Priority weight scheduled",
            "imgIconShield",
        ),
    ]
    for column, entry in zip(st.columns(4), entries):
        with column:
            st.html(viz.card(*entry))


def overview(instance, result):
    kpis(instance, result)
    left, right = st.columns([2.2, 1])
    with left, st.container(border=True):
        st.subheader("Maintenance timeline")
        if result:
            render_figure(viz.timeline(instance, api.schedule_rows(instance, result)))
            st.caption(
                "Bars show criticality; inspect numeric criticality in Scheduling Workspace."
            )
        else:
            st.info("Your maintenance timeline will appear after the first run.")
    with right, st.container(border=True):
        st.subheader("Scheduling intelligence")
        decision = cached_selection(instance)
        st.metric("Recommended algorithm", decision["algorithm"])
        st.metric("Complexity score", f"{decision['score']:.3f}")
        st.caption(f"Calibrated threshold: {decision['threshold']:.3f}")
        st.caption(
            "Recommendations use the configured selector; choose SELECTOR to apply this route."
        )
    with st.container(border=True):
        st.subheader("Current run")
        metrics(result)
    st.html(
        '<div class="workflow">01 · Prepare dataset &nbsp; → &nbsp; 02 · Schedule blocks'
        " &nbsp; → &nbsp; 03 · Review performance &nbsp; → &nbsp; 04 · Validate constraints</div>"
    )


def dataset(instance, result):
    left, right = st.columns([1, 2])
    with left, st.container(border=True):
        st.subheader("Instance configuration")
        st.caption(
            "Generate an instance or upload JSON in the sidebar. "
            "New datasets clear current results."
        )
        st.metric("Horizon", f"{instance['horizon']:,} min")
        st.metric("Resources", len(instance["resources"]))
        st.metric("Tasks", len(instance["tasks"]))
        st.success("Input validation passed")
        st.download_button(
            "Export instance JSON",
            api.to_json(instance),
            "instance.json",
            "application/json",
            width="stretch",
        )
        st.caption(f"Dataset fingerprint: {api.instance_hash(instance)}")
    with right, st.container(border=True):
        st.subheader("Task preview")
        st.dataframe(pd.DataFrame(instance["tasks"]), hide_index=True, width="stretch", height=380)
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.subheader("Tasks by corridor")
        if instance["tasks"]:
            counts = pd.DataFrame(instance["tasks"]).groupby("corridor_id").size()
            render_figure(viz.bars(counts.index, counts.values, "Task count"))
        else:
            st.info("This instance has no tasks.")
    with right, st.container(border=True):
        st.subheader("Resource capacities")
        resources = instance["resources"]
        if resources:
            render_figure(
                viz.bars(
                    [r["type"] for r in resources],
                    [r["capacity"] for r in resources],
                    "Available units",
                )
            )
        else:
            st.info("This simplified instance has no shared resource constraints.")


def workspace(instance, result):
    if result is None:
        metrics(result)
        return
    rows = api.schedule_rows(instance, result)
    if not rows:
        st.info("This instance has no tasks to inspect.")
        metrics(result)
        return
    left, right = st.columns([2.3, 1])
    with left, st.container(border=True):
        st.subheader("Maintenance block schedule")
        corridor = st.selectbox("Corridor", ["All"] + [c["id"] for c in instance["corridors"]])
        occupancy = st.checkbox("Show train occupancy", value=True)
        schedule_tab, resource_tab = st.tabs(["Schedule timeline", "Resource utilization"])
        with schedule_tab:
            render_figure(
                viz.timeline(instance, rows, None if corridor == "All" else corridor, occupancy)
            )
            st.caption("Every asset lane is shown. Gray shading indicates train occupancy.")
        with resource_tab:
            render_figure(viz.resource_chart(instance, rows))
    with right, st.container(border=True):
        st.subheader("Task inspector")
        task_id = st.selectbox("Task ID", [task["id"] for task in rows])
        row = next(task for task in rows if task["id"] == task_id)
        st.metric("Status", row["status"])
        st.write(f"Corridor {row['corridor_id']} · Asset {row['asset_id']}")
        st.write(f"Allowed window: {row['window_start']}–{row['window_end']} min")
        st.write(f"Duration: {row['duration']} min")
        st.write(f"Criticality: {row['criticality']}")
        if row["start"] is not None:
            st.write(f"Scheduled: {row['start']}–{row['end']} min")
        st.write("Resource demands", row["demands"])
        st.write("Prerequisites", row["depends_on"])
    metrics(result)
    st.subheader("All maintenance tasks")
    status = st.selectbox("Task status", ["All", "Scheduled", "Unscheduled"])
    filtered = [r for r in rows if status == "All" or r["status"] == status]
    st.dataframe(pd.DataFrame(filtered), hide_index=True, width="stretch")
    st.download_button(
        "Export schedule JSON", api.to_json(result), "schedule.json", "application/json"
    )


def intelligence(instance, result):
    decision = cached_selection(instance)
    left, right = st.columns([1.5, 1])
    with left, st.container(border=True):
        st.subheader("Instance complexity profile")
        render_figure(
            viz.bars(
                list(decision["features"]),
                list(decision["features"].values()),
                "Normalized feature value",
            )
        )
        for name, value in decision["features"].items():
            st.write(f"{name.replace('_', ' ').title()} · {value:.4f}")
            st.progress(min(1.0, max(0.0, value)))
        st.caption("Normalized features computed from this instance by the selector backend.")
    with right, st.container(border=True):
        st.subheader("Adaptive routing decision")
        st.metric("Complexity score", f"{decision['score']:.4f}")
        st.metric("Calibrated threshold", f"{decision['threshold']:.4f}")
        st.success(f"Recommended: {decision['algorithm']}")
        st.caption("The configured task cap also guards the exact solver route.")
    with st.container(border=True):
        st.subheader("Why this algorithm?")
        st.write(decision["reason"])
        st.caption("Choose SELECTOR in the sidebar and click Run to execute this recommendation.")


def analytics(instance, result, config):
    available = [item["name"] for item in api.list_algorithms(instance)]
    selected = st.multiselect(
        "Algorithms to compare", available, default=["NAIVE-GREEDY", "CA-GREEDY"]
    )
    if st.button("Compare algorithms", type="primary", disabled=not selected):
        with st.spinner("Comparing algorithms on the same instance…"):
            st.session_state.comparison = api.compare(
                instance,
                selected,
                config,
                run_fn=lambda data, name, options: cached_run(
                    api.instance_hash(data), data, name, options
                ),
            )
    comparison = st.session_state.comparison
    if not comparison:
        st.info(
            "Choose algorithms and compare to populate the charts. Results use this dataset only."
        )
        return
    table = pd.DataFrame([entry["metrics"] for entry in comparison])
    for entry in comparison:
        if entry.get("error"):
            st.warning(f"{entry['metrics']['algo']}: {entry['error']}")
    chart_data = table.dropna(subset=["objective"])
    for columns, specs in [
        (st.columns(2), [("runtime_s", "Runtime (seconds)"), ("objective", "Priority objective")]),
        (
            st.columns(2),
            [("coverage", "Weighted coverage (0–1)"), ("scheduled", "Scheduled task count")],
        ),
    ]:
        for column, (field, label) in zip(columns, specs):
            with column, st.container(border=True):
                st.subheader(label)
                render_figure(viz.bars(chart_data["algo"], chart_data[field], label))
    st.subheader("Measured comparison")
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(
        "Runtime is from the original execution, including on cache hits. "
        "An optimality gap is unavailable without a proven optimum."
    )
    st.download_button(
        "Export comparison CSV", table.to_csv(index=False), "comparison.csv", "text/csv"
    )


def validation(instance, result):
    st.success("Instance input checks passed")
    if result is None:
        st.info("Schedule validation is pending. Run an algorithm first.")
        return
    if st.button("Revalidate schedule"):
        result["validation"] = api.validate(instance, result["starts"])
        st.session_state.result = result
    report = result["validation"]
    labels = [
        ("C1", "Time windows"),
        ("C2", "Train clearance"),
        ("C3", "Asset exclusivity"),
        ("C4", "Resource capacity"),
        ("C5", "Dependencies"),
    ]
    for column, (code, label) in zip(st.columns(5), labels):
        with column:
            count = report["counts_by_code"].get(code, 0)
            st.html(
                viz.card(code, "PASS" if count == 0 else f"{count} issues", label, "imgIconShield")
            )
    metrics(result)
    with st.container(border=True):
        st.subheader("Constraint details")
        if report["violations"]:
            st.dataframe(pd.DataFrame(report["violations"]), hide_index=True, width="stretch")
        else:
            st.success("All scheduled tasks satisfy the independent C1–C5 checks.")
        st.caption(
            "A valid schedule may leave tasks unscheduled. Validation checks feasibility; "
            "it does not prove optimality."
        )
    st.download_button(
        "Export validation report", api.to_json(report), "validation.json", "application/json"
    )


def main():
    st.set_page_config(
        page_title="RAILOPT · Maintenance Scheduling",
        page_icon="🚆",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.html(viz.stylesheet())
    if "instance" not in st.session_state:
        replace_instance(api.generate_instance())
    caps = api.limits()
    upload_invalid = False
    with st.sidebar:
        st.html(viz.brand())
        page = st.radio("WORKSPACE", list(PAGES), key="page")
        st.divider()
        with st.expander("Instance source", expanded=page == "Dataset Studio"):
            source = st.radio("Source", ["Generate", "Upload JSON"], horizontal=True)
            if source == "Generate":
                kind = st.selectbox("Instance kind", ["extended", "simplified"])
                n = st.number_input("Tasks", min_value=1, max_value=caps["max_tasks_ui"], value=40)
                corridors = st.number_input(
                    "Corridors", min_value=1, max_value=20, value=2, disabled=kind == "simplified"
                )
                seed = st.number_input("Seed", min_value=0, max_value=2**32 - 1, value=3)
                horizon = st.number_input(
                    "Horizon (minutes)", min_value=120, max_value=caps["max_horizon"], value=1440
                )
                if st.button("Generate instance", width="stretch"):
                    try:
                        replace_instance(
                            api.generate_instance(
                                kind, int(n), int(corridors), int(seed), int(horizon)
                            )
                        )
                    except api.APIError as exc:
                        st.error(str(exc))
            else:
                upload = st.file_uploader("Instance JSON", type=["json"])
                st.caption(f"Maximum {caps['upload_max_mb']} MB; {caps['max_tasks_ui']} tasks.")
                if upload is not None:
                    try:
                        loaded = api.load_instance(upload.getvalue())
                        if api.instance_hash(loaded) != api.instance_hash(
                            st.session_state.instance
                        ):
                            replace_instance(loaded)
                        st.success("JSON loaded and validated")
                    except api.APIError as exc:
                        st.error(str(exc))
                        upload_invalid = True
        instance = st.session_state.instance
        eligibility = {item["name"]: item for item in api.list_algorithms(instance)}
        algorithm = st.selectbox("Scheduling algorithm", list(eligibility), index=2)
        blocked = not eligibility[algorithm]["enabled"]
        if blocked:
            st.warning(eligibility[algorithm]["reason"])
        seconds = st.slider(
            "ILP time limit (seconds)",
            1,
            int(caps["ilp_time_limit_s"]),
            int(caps["ilp_time_limit_s"]),
        )
        config = {"time_limit_s": seconds}
        if upload_invalid:
            st.caption(
                "Upload rejected. The current dataset is unchanged; fix or remove the upload."
            )
        if st.button("Run", type="primary", width="stretch", disabled=blocked or upload_invalid):
            try:
                run_current(algorithm, config)
            except api.APIError as exc:
                st.error(str(exc))
        st.caption(
            "Local prototype · deterministic seed\n\nSix workspaces · RAILOPT v" + api.get_version()
        )
    st.html(viz.heading(page, PAGES[page], api.instance_hash(instance)))
    result = st.session_state.result
    try:
        if page == "Performance Analytics":
            analytics(instance, result, config)
        else:
            {
                "Command Center": overview,
                "Dataset Studio": dataset,
                "Scheduling Workspace": workspace,
                "Adaptive Intelligence": intelligence,
                "Validation Center": validation,
            }[page](instance, result)
    except api.APIError as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
