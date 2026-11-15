# Railway Maintenance Block Planning (RBP)

Adaptive Hybrid Scheduling for Railway Maintenance Block Planning (DAA).

## Quickstart

### 1. Environment Setup
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

### 2. Run Checks and Tests
```bash
# Automated checks (ruff linting + pytest)
pytest
ruff check .
```

### 3. Launch UI Prototype
```bash
streamlit run app/streamlit_app.py
```

### 4. Reproduce the experiments
```bash
python -m rbp.experiments.runner config/experiments/e1.yaml --dry-run
python -m rbp.experiments.runner config/experiments/e1.yaml
python -m rbp.experiments.runner config/experiments/e2.yaml
python -m rbp.experiments.runner config/experiments/e3.yaml
python scripts/make_report.py
```

See [experiment instructions](docs/EXPERIMENTS.md) for resume, independent repeats,
solver budgets and provenance. Raw `results/` files are ignored; compact summaries
and figures live in `reports/`.

## Architecture
- `src/rbp/models`: Immutable domain entities (`Task`, `Corridor`, `Resource`, `Timetable`, `Instance`, `Schedule`).
- `src/rbp/io`: Instance validation, JSON & CSV serialization.
- `src/rbp/constraints`: Predicates C1-C5 and placement state.
- `src/rbp/validation`: Independent schedule validator (zero shared predicate code).
- `src/rbp/generation`: Deterministic synthetic instance generators.
- `src/rbp/algorithms`: WIS-DP, Brute-Force oracle, NAIVE-GREEDY, CA-GREEDY, ILP-EXACT.
- `src/rbp/selector`: Normalized complexity features, score, and adaptive routing rule.
- `src/rbp/metrics`: Standard evaluation metrics and uniform runner.
- `src/rbp/experiments`: Reproducible experiment grids with full provenance.
- `src/rbp/api.py`: Facade module interfacing with the UI.
