# RAILOPT Streamlit prototype

Launch from the repository root after installing requirements and `pip install -e .`:

```sh
streamlit run app/streamlit_app.py
```

This is an interactive browser UI. The terminal only starts the local server.
The visual theme and assets come from the supplied RAILOPT Figma design, adapted
to native Streamlit controls and responsive columns.

## Included screens

- **Command Center:** actual instance counts, current schedule, coverage and recommendation.
- **Dataset Studio:** generated/uploaded JSON inspection, task table, distributions and export.
- **Scheduling Workspace:** asset timeline with train occupancy, corridor filter,
  resource usage, task inspector, unscheduled tasks and schedule export.
- **Adaptive Intelligence:** the five real complexity features, calibrated threshold,
  recommendation and backend routing explanation.
- **Performance Analytics:** explicit comparison of algorithms on the current instance,
  runtime/objective/coverage/count charts and CSV export.
- **Validation Center:** independent C1–C5 checks, violation details, revalidation and JSON export.

Algorithm Laboratory (including step playback) and Experiment History are deferred.
There is no account system, notification service or persistent run history. The
prototype displays actual backend data, not the example measurements from Figma.
The timeline displays at most 30 asset lanes; use the corridor filter and full task
table for larger instances. Resource capacity lines do not depict availability
windows; the independent validator checks availability as part of C4.

## Data and execution

All domain operations go through `rbp.api`; `rbp.viz` only formats presentation.
Facade functions `generate_instance`, `load_instance`, `list_algorithms`, `run`,
`compare` and `select` return JSON-serializable dictionaries/lists. Invalid inputs
raise `APIError`, which the UI presents as a message.

Use the sidebar's Generate/Upload JSON controls. Uploads use the project's version-1
instance JSON schema, parsed only with `json`. Export any generated instance for
a schema example. The extended generator can return fewer tasks than requested
when it cannot produce feasible candidates; the preview always shows the actual count.

`config/defaults.yaml` controls the 2,000-task UI limit, 10,080-minute horizon cap,
5 MB upload cap and 150-task ILP guard. `.streamlit/config.toml` enforces the same
5 MB upload limit at the server. Keep both upload settings aligned when changing
them. Uploads also limit corridors/timetables to 20 and resources to 32. Brute force
is limited to 16 tasks. WIS-DP and brute force require simplified instances.

The UI defaults to a five-second ILP budget, adjustable up to the configured
30-second maximum. The selector receives the same solver budget. Time-limited
results are explicitly labeled; feasibility does not imply optimality.

`st.cache_data` keys executions by the canonical instance SHA-256, instance content,
algorithm and run configuration. Run and Compare share this cache. Repeated clicks
reuse the original result and runtime; a changed seed/instance/config gets a new
key. Generating or loading an instance clears the active result and comparison.
Cached results are process-local and bounded to 64 entries; restarting the server
clears them. No uploaded files or secrets are saved to the repository.

## Focused checks

```sh
pytest tests/test_api.py tests/test_app.py tests/test_import_boundaries.py -q
```

These use tiny instances and one short exact solve, covering JSON serialization,
failure inputs, size guards, reproducibility, cache reuse, all six screens and the
UI import boundary. No Phase 9 experiment grid is rerun.
