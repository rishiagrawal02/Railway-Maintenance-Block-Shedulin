# RAILOPT — Railway Maintenance Block Scheduling

A Python scheduling backend with a Streamlit browser prototype. WIS-DP is exact
for simplified fixed-interval instances. NAIVE-GREEDY and CA-GREEDY are heuristics;
CA-GREEDY has **no optimality guarantee**. The selector is a calibrated,
rule-based threshold router, not machine learning. CP-SAT reports proven optima
separately from time-limited incumbents.

## Install from a fresh clone

Reference environment: **Python 3.12** (measurements used 3.12.8), Git and Bash
(Git Bash on Windows for the reproduction script). Other Python versions are not
certified for reproducing the reference measurements. Check `py -0p` on Windows;
if 3.12 is missing, install it before continuing. Do not run tests after a failed
installation.

```bash
git clone --branch phase-11-release https://github.com/rishiagrawal02/Railway-Maintenance-Block-Shedulin.git
cd Railway-Maintenance-Block-Shedulin
git rev-parse HEAD
```

Windows PowerShell (activation is optional; explicit interpreter paths are reliable):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import rbp, streamlit, ortools; print(rbp.__file__)"
```

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python -c "import rbp, streamlit, ortools; print(rbp.__file__)"
```

`requirements.txt` pins direct dependencies, including NumPy, and includes `-e .`
to install this repository's `src/rbp` package. No separate editable-install step
is needed. Run commands from the repository root. `rbp.__file__` must point into
this clone, not another checkout. The direct pins are not a cross-platform lock
of every transitive dependency.

In the commands below, Windows PowerShell users can replace `python` with
`.\.venv\Scripts\python.exe`, or activate with `.\.venv\Scripts\Activate.ps1`.
In Windows Git Bash use `source .venv/Scripts/activate`.

## Test and release hygiene

```bash
python -m pytest
python scripts/gate_wis.py
python scripts/release_check.py
```

The first command includes slow tests. The correctness gate must print
`GATE wis-dp vs brute-force: 100/100`. The release check must exit 0. It inspects
**Git's index**, including staged files: threshold version, four golden hashes,
ignored-output hygiene, credential patterns and relative Markdown file links.
It never prints matched secret values. It is a heuristic scan of UTF-8 text,
not a complete security audit; link checks validate file targets, not anchors.
Before checking your own edits, stage only intended release files. A passing
hygiene scan does not replace tests or independent reproduction.

For a quick UI-only check (not the full release gate):

```bash
python -m pytest tests/test_api.py tests/test_app.py tests/test_viz.py tests/test_import_boundaries.py
```

## Launch the browser UI

```bash
python -m streamlit run app/streamlit_app.py
```

Open the printed localhost URL. Generate or upload an instance in the sidebar,
choose CA-GREEDY and click **Run**. Explore Command Center, Dataset Studio,
Scheduling Workspace, Adaptive Intelligence, Performance Analytics and Validation
Center. A valid schedule reports zero violations. The health endpoint
`http://localhost:8501/_stcore/health` returns HTTP 200 and `ok`.

Stop the server with Ctrl+C. Restart after updating backend code so Python does
not retain old imported modules. See [UI details](docs/UI.md) for limits, exports,
caching and solver budgets. Algorithm Laboratory, Experiment History and what-if
analysis remain deferred.

## Reproduce experiments with one command

With the environment activated, from Bash/Git Bash:

```bash
bash scripts/reproduce.sh
```

This runs the full tests, 100/100 gate, release hygiene, complete primary **and
repeat** E1–E3 grids, report generation and non-timing reference-summary comparison.
This is a substantial computation, not a smoke test. Do not run concurrent timing
studies. The script stops at the first failure and does not weaken checks.

Outputs go to ignored `results/reproduction/<commit>/primary`, `repeat` and
`reports`. Set `RBP_REPRO_ROOT` to a different unused directory under `results/`
for another independent run. The runner can resume compatible partial runs;
source/config/environment changes require a fresh output directory. New reports
never overwrite committed `reports/`.

**Reproducibility criterion:** primary/repeat row outcomes must agree under the
existing report audit; summary values other than runtime statistics must match
the committed reference within floating-point tolerance. Timing values, plot
pixels and provenance dates are not expected to be byte-identical. An unchanged
Git diff alone is not evidence of outcome agreement. A wall-limit-dependent
solver difference is reported as a failure for investigation, not normalized away.
The historical Phase 9 E2/E3 repeats were incomplete; this script does not pretend
those runs have already been independently reproduced.

Individual commands, including a small executed smoke grid:

```bash
python -m rbp.experiments.runner config/experiments/e1.yaml --dry-run --output-root results/smoke
python -m rbp.experiments.runner config/experiments/e1.yaml --output-root results/manual
python -m rbp.experiments.runner config/experiments/e2.yaml --output-root results/manual
python -m rbp.experiments.runner config/experiments/e3.yaml --output-root results/manual
python scripts/make_report.py --results-root results/manual --output results/manual/reports
```

The last command alone makes an exploratory report without repeat certification.
See [experiment provenance and resume rules](docs/EXPERIMENTS.md).

## Streamlit Community Cloud

Select this GitHub repository, the verified release branch/commit, Python 3.12,
and entrypoint `app/streamlit_app.py`. The root `requirements.txt` installs both
dependencies and the editable local package; `.streamlit/config.toml` sets headless
mode and the upload cap. The repository's source, configuration and local assets
must remain present. No secrets are required and no Dockerfile is needed.
This documents deployment setup; a hosted deployment has not been certified.
See Streamlit's [dependency instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
and [deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

## Repository map

| Location | Purpose |
| --- | --- |
| `src/rbp/models`, `io`, `generation` | Immutable inputs, JSON checks, seeded generators |
| `src/rbp/algorithms`, `constraints` | Solvers and placement feasibility |
| `src/rbp/validation` | Independent schedule checker |
| `src/rbp/selector` | Five features, calibration and rule-based routing |
| `src/rbp/metrics`, `experiments` | Validated runs, reproducible grids and reports |
| `src/rbp/api.py`, `viz`, `app/streamlit_app.py` | Facade, reusable figures and browser UI |
| `config`, `tests/data` | Budgets, experiment grids, threshold and golden hashes |
| `reports` | Committed historical summaries and figures |
| `scripts`, `tests`, `docs` | Entry points, checks and evidence |

Read [complexity derivations](docs/COMPLEXITY.md), [validation evidence](docs/VALIDATION.md)
and the [independent verification checklist](docs/RELEASE_VERIFICATION.md).
**Release status: candidate; independent fresh-clone reproduction is pending.**
