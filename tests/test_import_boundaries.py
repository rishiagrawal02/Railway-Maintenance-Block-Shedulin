"""Architecture guard: automated AST inspection of import boundaries."""

import ast
from pathlib import Path


def extract_imports_from_source(source: str) -> list[str]:
    """Parse python source and return a list of imported module strings."""
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def check_module_imports(source_file_path: Path, source_code: str | None = None) -> list[str]:
    """Check a single file's imports against architectural boundary rules."""
    path_str = source_file_path.as_posix()
    if source_code is None:
        source_code = source_file_path.read_text(encoding="utf-8")

    imported_modules = extract_imports_from_source(source_code)
    violations = []

    # Check boundaries
    is_models = "src/rbp/models" in path_str
    is_validation = "src/rbp/validation" in path_str
    is_constraints = "src/rbp/constraints" in path_str
    is_algorithms = "src/rbp/algorithms" in path_str
    is_app = "app/" in path_str

    for mod in imported_modules:
        if is_models:
            # models must import nothing from rbp
            if mod == "rbp" or mod.startswith("rbp."):
                violations.append(f"{path_str} (models) illegally imports '{mod}'")

        elif is_validation:
            # validation imports ONLY rbp.models
            if (mod == "rbp" or mod.startswith("rbp.")) and not (
                mod == "rbp.models" or mod.startswith("rbp.models.")
            ):
                violations.append(f"{path_str} (validation) illegally imports '{mod}'")

        elif is_constraints:
            # constraints must not import validation or algorithms
            if mod.startswith("rbp.validation") or mod.startswith("rbp.algorithms"):
                violations.append(f"{path_str} (constraints) illegally imports '{mod}'")

        elif is_algorithms:
            # algorithms must not import validation
            if mod.startswith("rbp.validation"):
                violations.append(f"{path_str} (algorithms) illegally imports '{mod}'")

        elif is_app:
            # app may only import rbp.api from rbp
            if (mod == "rbp" or mod.startswith("rbp.")) and not (
                mod == "rbp.api" or mod.startswith("rbp.api.") or mod.startswith("rbp.viz")
            ):
                violations.append(f"{path_str} (app) illegally imports '{mod}'")

    return violations


def test_import_boundaries():
    """T0.3-07: AST scan of all python files in src/rbp and app/."""
    repo_root = Path(__file__).resolve().parent.parent
    all_violations = []

    for folder in [repo_root / "src" / "rbp", repo_root / "app"]:
        if not folder.exists():
            continue
        for py_file in folder.rglob("*.py"):
            violations = check_module_imports(py_file)
            all_violations.extend(violations)

    err_msg = "Architectural boundary violations found:\n" + "\n".join(all_violations)
    assert not all_violations, err_msg


def test_import_boundary_violation_detected():
    """T0.3-08: Injected boundary violation is reliably caught by the checker."""
    bad_validation_source = "from rbp.constraints.predicates import c1_window_ok"
    fake_path = Path("src/rbp/validation/bad_validator.py")
    violations = check_module_imports(fake_path, source_code=bad_validation_source)

    assert len(violations) == 1
    assert "illegally imports 'rbp.constraints.predicates'" in violations[0]
