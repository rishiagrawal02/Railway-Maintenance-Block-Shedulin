"""JSON-only application facade; all scheduling stays behind this boundary."""

import hashlib
import json
from dataclasses import asdict

from rbp.config import load_config
from rbp.generation.extended import generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.io.input_checks import InstanceError
from rbp.io.serialize import InstanceLoadError, instance_from_dict, instance_to_dict
from rbp.metrics.runner import ALGORITHMS, run_algorithm
from rbp.models.schedule import Schedule
from rbp.models.simplified import is_simplified
from rbp.selector.selector import select as choose
from rbp.validation.validator import validate_schedule


class APIError(ValueError):
    """A user-facing input or execution error."""


def get_version():
    return "1.0.0"


def limits():
    cfg = load_config()
    return {
        "max_tasks_ui": cfg["ui"]["max_tasks_ui"],
        "upload_max_mb": cfg["ui"].get("upload_max_mb", 5),
        "max_horizon": cfg["ui"].get("max_horizon", 10080),
        "ilp_max_tasks": cfg["selector"]["ilp_max_tasks"],
        "ilp_time_limit_s": cfg["ilp"]["time_limit_s"],
    }


def to_json(data):
    return json.dumps(data, sort_keys=True, allow_nan=False, indent=2)


def instance_hash(data):
    return hashlib.sha256(to_json(data).encode()).hexdigest()


def _instance(data):
    caps = limits()
    if not isinstance(data, dict):
        raise APIError("The JSON root must be an object.")
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise APIError("The instance must contain a tasks list.")
    if len(tasks) > caps["max_tasks_ui"]:
        raise APIError(f"Task limit exceeded: maximum {caps['max_tasks_ui']} tasks.")
    horizon = data.get("horizon")
    if type(horizon) is not int or not 1 <= horizon <= caps["max_horizon"]:
        raise APIError(f"Horizon must be an integer between 1 and {caps['max_horizon']}.")
    try:
        if not isinstance(data.get("meta", {}), dict):
            raise APIError("Instance metadata must be an object.")
        for key, maximum in (("corridors", 20), ("resources", 32), ("timetable", 20)):
            items = data.get(key)
            if not isinstance(items, list) or len(items) > maximum:
                raise APIError(f"{key} must be a list of at most {maximum} entries.")
        for task in tasks:
            if not isinstance(task, dict):
                raise APIError("Every task must be an object.")
            for field in (
                "id",
                "corridor_id",
                "asset_id",
                "window_start",
                "window_end",
                "duration",
                "criticality",
                "urgency",
            ):
                if type(task.get(field)) is not int:
                    raise APIError(f"Task field {field} must be an integer.")
            demands = task.get("demands")
            deps = task.get("depends_on")
            if not isinstance(demands, dict) or any(
                not isinstance(k, str) or type(v) is not int or v < 0 for k, v in demands.items()
            ):
                raise APIError("E_DEMAND: demands must contain non-negative integer quantities.")
            if not isinstance(deps, list) or any(type(v) is not int for v in deps):
                raise APIError("Task prerequisites must be integer IDs.")
        inst = instance_from_dict(data)
        for resource in inst.resources:
            if type(resource.capacity) is not int or resource.capacity < 0:
                raise APIError("Resource capacity must be a non-negative integer.")
        return inst
    except InstanceError as exc:
        raise APIError("; ".join(str(error) for error in exc.errors)) from exc
    except (InstanceLoadError, TypeError, ValueError, KeyError, AttributeError) as exc:
        raise APIError(f"Invalid instance JSON: {exc}") from exc


def _reject_constant(value):
    raise APIError(f"Invalid JSON number: {value}")


def load_instance(content):
    """Load UTF-8 JSON bytes/text, never a user-controlled filesystem path."""
    if not isinstance(content, (str, bytes)):
        raise APIError("Upload a JSON file.")
    raw = content.encode("utf-8") if isinstance(content, str) else content
    if len(raw) > limits()["upload_max_mb"] * 1024 * 1024:
        raise APIError("Upload exceeds the configured size cap.")
    try:
        data = json.loads(raw, parse_constant=_reject_constant)
        return instance_to_dict(_instance(data))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise APIError("Malformed JSON. Upload a complete UTF-8 instance JSON file.") from exc


def generate_instance(kind="extended", n=40, corridors=2, seed=3, horizon=1440):
    caps = limits()
    for name, value, low, high in (
        ("Task count", n, 1, caps["max_tasks_ui"]),
        ("Corridors", corridors, 1, 20),
        ("Seed", seed, 0, 2**32 - 1),
        ("Horizon", horizon, 120, caps["max_horizon"]),
    ):
        if type(value) is not int or not low <= value <= high:
            raise APIError(f"{name} must be an integer between {low} and {high}.")
    if kind == "simplified":
        inst = generate_simplified(n=n, seed=seed, horizon=horizon)
    elif kind == "extended":
        inst = generate_extended(n=n, seed=seed, n_corridors=corridors, horizon=horizon)
    else:
        raise APIError("Choose simplified or extended.")
    data = instance_to_dict(inst)
    _instance(data)
    return data


def list_algorithms(instance=None):
    inst = _instance(instance) if instance is not None else None
    rows = []
    for name in ALGORITHMS:
        reason = ""
        if inst is not None:
            if name in ("WIS-DP", "BRUTE-FORCE") and not is_simplified(inst):
                reason = "Not applicable: this algorithm requires a simplified instance."
            elif name == "ILP-EXACT" and len(inst.tasks) > limits()["ilp_max_tasks"]:
                reason = f"ILP disabled above {limits()['ilp_max_tasks']} tasks."
            elif name == "BRUTE-FORCE" and len(inst.tasks) > 16:
                reason = "Brute force is limited to 16 tasks in the prototype."
        rows.append({"name": name, "enabled": not reason, "reason": reason})
    return rows


def select(instance):
    return asdict(choose(_instance(instance)))


def validate(instance, starts):
    report = validate_schedule(
        _instance(instance), Schedule(starts={int(k): v for k, v in starts.items()})
    )
    return {
        **asdict(report),
        "counts_by_code": report.counts_by_code,
        "total_violations": report.total_violations,
    }


def run(instance, algorithm="CA-GREEDY", config=None):
    inst = _instance(instance)
    eligibility = {item["name"]: item for item in list_algorithms(instance)}
    if algorithm not in eligibility:
        raise APIError("Unknown algorithm.")
    if not eligibility[algorithm]["enabled"]:
        raise APIError(eligibility[algorithm]["reason"])
    cfg = load_config()
    options = config or {}
    if set(options) - {"time_limit_s"}:
        raise APIError("Unsupported run configuration.")
    seconds = options.get("time_limit_s", cfg["ilp"]["time_limit_s"])
    if type(seconds) not in (int, float) or not 0 < seconds <= limits()["ilp_time_limit_s"]:
        raise APIError("ILP time limit exceeds the configured maximum or is invalid.")
    ilp = {"time_limit_s": seconds, "num_workers": 1, "random_seed": cfg["ilp"]["seed"]}
    greedy = cfg["ca_greedy"]
    ca = {
        "lambda_b": greedy["lambda_block"],
        "lambda_r": greedy["lambda_resource"],
        "lambda_c": greedy["lambda_conflict"],
        "lookahead_k": greedy["lookahead_k"],
        "allow_skip_negative": greedy["allow_skip_negative"],
    }
    kwargs = {"ILP-EXACT": ilp, "CA-GREEDY": ca}.get(algorithm, {})
    if algorithm == "SELECTOR":
        kwargs = {"config": cfg, "solver_options": {"ILP-EXACT": ilp, "CA-GREEDY": ca}}
    record = run_algorithm(algorithm, inst, **kwargs)
    if record.status in ("ERROR", "NOT_APPLICABLE"):
        raise APIError(f"{algorithm} could not produce a schedule ({record.status}).")
    schedule = record.meta.get("schedule")
    if schedule is None:
        raise APIError("The solver returned no schedule. Try another algorithm.")
    starts = {str(k): v for k, v in schedule.starts.items()}
    metrics = {k: v for k, v in record.as_dict().items() if k != "meta"}
    return {
        "instance_hash": instance_hash(instance),
        "metrics": metrics,
        "starts": starts,
        "validation": validate(instance, starts),
        "decision": select(instance) if algorithm == "SELECTOR" else None,
    }


def compare(instance, algorithms=None, config=None, *, run_fn=None):
    """Keep one row per algorithm; only verified exact results supply an optimum."""
    names = algorithms if algorithms is not None else ["NAIVE-GREEDY", "CA-GREEDY"]
    execute = run_fn or run
    eligibility = {item["name"]: item for item in list_algorithms(instance)}
    results = []
    for name in names:
        try:
            if name in eligibility and not eligibility[name]["enabled"]:
                raise APIError(eligibility[name]["reason"])
            result = execute(instance, name, config)
            result = {**result, "metrics": {**result["metrics"], "gap": None}}
        except Exception as exc:
            status = (
                "NOT_APPLICABLE"
                if name in eligibility and not eligibility[name]["enabled"]
                else "ERROR"
            )
            result = {
                "instance_hash": instance_hash(instance),
                "error": str(exc),
                "metrics": {
                    "algo": name,
                    "status": status,
                    "objective": None,
                    "coverage": None,
                    "runtime_s": None,
                    "violations": None,
                    "gap": None,
                    "scheduled": None,
                    "optimal": False,
                },
            }
        results.append(result)
    optima = [
        r["metrics"]["objective"]
        for r in results
        if r["metrics"].get("optimal")
        and r.get("validation", {}).get("valid")
        and r["metrics"].get("status") == "OK"
        and r.get("instance_hash") == instance_hash(instance)
    ]
    optimum = optima[0] if optima and len(set(optima)) == 1 else None
    for result in results:
        metrics = result["metrics"]
        if optimum is not None and result.get("validation", {}).get("valid"):
            metrics["gap"] = (
                (optimum - metrics["objective"]) / optimum
                if optimum > 0
                else 0.0
                if metrics["objective"] == 0
                else None
            )
    return results


def schedule_rows(instance, result):
    """Presentation data, including explicit unscheduled tasks."""
    starts = result["starts"] if result else {}
    return [
        {
            **task,
            "start": starts.get(str(task["id"])),
            "end": starts[str(task["id"])] + task["duration"]
            if str(task["id"]) in starts
            else None,
            "status": "Scheduled" if str(task["id"]) in starts else "Unscheduled",
        }
        for task in instance["tasks"]
    ]
