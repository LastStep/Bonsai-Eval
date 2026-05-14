"""Structural validator for Bonsai-Eval scenario YAML files.

Discovers `scenarios/bonsai_behavioral/*.yaml`, loads each via PyYAML, and
asserts the structural contract documented in `scenarios/SCHEMA.md`:

- All required top-level fields present (`id`, `description`, `category`,
  `prompt`, `setup`, `evaluators`).
- `id` matches the filename stem (kebab-case).
- `category` is one of the five documented values.
- `setup.workspace_template` is a non-empty string.
- `evaluators` is a non-empty list and every entry has a `type` in the allowed
  set with the type-specific required fields.

Schema doc reference: `scenarios/SCHEMA.md` (Plan 38 §P2.1).

Usage:
    uv run python scripts/check_scenarios.py
    uv run python scripts/check_scenarios.py --scenarios-dir scenarios/bonsai_behavioral

Exit code 0 on success; 1 with diagnostics on any structural failure.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

# --- Schema constants (mirror scenarios/SCHEMA.md) ---

ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "role-discipline",
        "plan-gating",
        "scope-boundaries",
        "memory-continuity",
        "workflow-invocation",
    }
)

ALLOWED_EVALUATOR_TYPES: frozenset[str] = frozenset({"deterministic", "test_based", "llm_judge"})

ALLOWED_DETERMINISTIC_CHECKS: frozenset[str] = frozenset(
    {
        "file_unchanged",
        "file_exists",
        "file_contains",
        "hook_event_fired",
        "tool_call_made",
        "tool_call_not_made",
    }
)

REQUIRED_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "id",
    "description",
    "category",
    "prompt",
    "setup",
    "evaluators",
)

DEFAULT_SCENARIOS_DIR = Path("scenarios/bonsai_behavioral")

# Path to the installed station's sensor hooks. Used to validate
# `hook_event_fired.hook` values against the set of real hook stems
# (e.g. `scope-guard-files`, `dispatch-guard`). Resolved relative to the
# repo root (parent of `scripts/`).
DEFAULT_SENSORS_DIR = Path(__file__).resolve().parent.parent / "station" / "agent" / "Sensors"


def discover_known_hooks(sensors_dir: Path = DEFAULT_SENSORS_DIR) -> frozenset[str]:
    """Return the set of valid hook ids — stems of `*.sh` files in `sensors_dir`.

    If the directory does not exist (e.g. running the validator from an
    unbootstrapped checkout), return an empty set; hook-name validation is
    then skipped rather than producing spurious failures.
    """
    if not sensors_dir.exists():
        return frozenset()
    return frozenset(p.stem for p in sensors_dir.glob("*.sh") if p.is_file())


KNOWN_HOOKS: frozenset[str] = discover_known_hooks()


class ScenarioValidationError(Exception):
    """Raised when a scenario file fails the structural schema."""


def _ensure(condition: object, msg: str) -> None:
    """Raise ScenarioValidationError if `condition` is falsy.

    Accepts `object` (not just `bool`) so callers can pass the natural
    short-circuit pattern `isinstance(x, str) and x` — which has type
    `bool | str` — without wrapping in `bool(...)` everywhere.
    """
    if not condition:
        raise ScenarioValidationError(msg)


def _validate_deterministic(evaluator: dict[str, Any], ctx: str) -> None:
    check = evaluator.get("check")
    _ensure(
        isinstance(check, str) and check in ALLOWED_DETERMINISTIC_CHECKS,
        f"{ctx}: deterministic evaluator `check` must be one of "
        f"{sorted(ALLOWED_DETERMINISTIC_CHECKS)}, got {check!r}",
    )
    # Per-check required args (per SCHEMA.md "Evaluators" table).
    if check in {"file_unchanged", "file_exists"}:
        _ensure(
            isinstance(evaluator.get("path"), str) and evaluator["path"],
            f"{ctx}: deterministic check {check!r} requires a non-empty `path`",
        )
    elif check == "file_contains":
        _ensure(
            isinstance(evaluator.get("path"), str) and evaluator["path"],
            f"{ctx}: deterministic check `file_contains` requires `path`",
        )
        _ensure(
            isinstance(evaluator.get("pattern"), str) and evaluator["pattern"],
            f"{ctx}: deterministic check `file_contains` requires `pattern`",
        )
    elif check == "hook_event_fired":
        _ensure(
            isinstance(evaluator.get("hook"), str) and evaluator["hook"],
            f"{ctx}: deterministic check `hook_event_fired` requires `hook`",
        )
        # Cross-check against installed sensor hooks. Skip if the sensors
        # directory wasn't discovered (KNOWN_HOOKS is empty) — that keeps
        # the validator usable from an unbootstrapped checkout.
        if KNOWN_HOOKS:
            hook_id = evaluator["hook"]
            _ensure(
                hook_id in KNOWN_HOOKS,
                f"{ctx}: hook_event_fired references unknown hook {hook_id!r}; "
                f"known hooks (stems of station/agent/Sensors/*.sh): "
                f"{sorted(KNOWN_HOOKS)}",
            )
    elif check in {"tool_call_made", "tool_call_not_made"}:
        _ensure(
            isinstance(evaluator.get("tool"), str) and evaluator["tool"],
            f"{ctx}: deterministic check {check!r} requires `tool`",
        )
        # `path` vs `command` is keyed off the tool's own argument schema —
        # the Claude/Inspect `Bash` tool takes `command`, every other tool
        # takes a `path`-style argument. See SCHEMA.md §Evaluators.
        tool = evaluator["tool"]
        if tool == "Bash":
            _ensure(
                "path" not in evaluator,
                f"{ctx}: deterministic check {check!r} with `tool: Bash` must not set "
                f"`path` (the Bash tool's argument is `command`, not `path`)",
            )
            _ensure(
                isinstance(evaluator.get("command"), str) and evaluator["command"],
                f"{ctx}: deterministic check {check!r} with `tool: Bash` requires a "
                f"non-empty `command` (substring matched against the bash command string)",
            )
        else:
            _ensure(
                "command" not in evaluator,
                f"{ctx}: deterministic check {check!r} with `tool: {tool}` must not set "
                f"`command` (only `tool: Bash` uses `command`; other tools use `path`)",
            )
            # `path` is recommended for non-Bash tool_call_* checks but not
            # strictly required (e.g. `tool_call_made: Task` with no path arg
            # is meaningful — matches any Task dispatch).
            if "path" in evaluator:
                _ensure(
                    isinstance(evaluator["path"], str) and evaluator["path"],
                    f"{ctx}: deterministic check {check!r} `path` must be a non-empty string when set",
                )


def _validate_test_based(evaluator: dict[str, Any], ctx: str) -> None:
    _ensure(
        isinstance(evaluator.get("command"), str) and evaluator["command"],
        f"{ctx}: test_based evaluator requires a non-empty `command`",
    )
    _ensure(
        isinstance(evaluator.get("expected_exit_code"), int),
        f"{ctx}: test_based evaluator requires integer `expected_exit_code`",
    )


def _validate_llm_judge(evaluator: dict[str, Any], ctx: str) -> None:
    _ensure(
        isinstance(evaluator.get("model"), str) and evaluator["model"],
        f"{ctx}: llm_judge evaluator requires a `model` alias string",
    )
    _ensure(
        isinstance(evaluator.get("rubric"), str) and evaluator["rubric"],
        f"{ctx}: llm_judge evaluator requires a non-empty `rubric`",
    )
    if "swap_positions" in evaluator:
        _ensure(
            isinstance(evaluator["swap_positions"], bool),
            f"{ctx}: llm_judge evaluator `swap_positions` must be a boolean",
        )


def _validate_evaluator(evaluator: Any, ctx: str) -> None:
    _ensure(isinstance(evaluator, dict), f"{ctx}: evaluator must be a mapping")
    etype = evaluator.get("type")
    _ensure(
        isinstance(etype, str) and etype in ALLOWED_EVALUATOR_TYPES,
        f"{ctx}: evaluator `type` must be one of {sorted(ALLOWED_EVALUATOR_TYPES)}, got {etype!r}",
    )
    if etype == "deterministic":
        _validate_deterministic(evaluator, ctx)
    elif etype == "test_based":
        _validate_test_based(evaluator, ctx)
    elif etype == "llm_judge":
        _validate_llm_judge(evaluator, ctx)


def validate_scenario(path: Path) -> dict[str, Any]:
    """Validate a single scenario YAML file. Returns the parsed dict on success."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ScenarioValidationError(f"{path}: YAML parse error: {exc}") from exc

    _ensure(isinstance(data, dict), f"{path}: top-level must be a mapping")

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        _ensure(field in data, f"{path}: missing required top-level field `{field}`")

    scenario_id = data["id"]
    _ensure(
        isinstance(scenario_id, str) and scenario_id,
        f"{path}: `id` must be a non-empty string",
    )
    _ensure(
        scenario_id == path.stem,
        f"{path}: `id` ({scenario_id!r}) must equal filename stem ({path.stem!r})",
    )

    _ensure(
        isinstance(data["description"], str) and data["description"],
        f"{path}: `description` must be a non-empty string",
    )
    _ensure(
        isinstance(data["prompt"], str) and data["prompt"].strip(),
        f"{path}: `prompt` must be a non-empty string",
    )

    category = data["category"]
    _ensure(
        isinstance(category, str) and category in ALLOWED_CATEGORIES,
        f"{path}: `category` must be one of {sorted(ALLOWED_CATEGORIES)}, got {category!r}",
    )

    setup = data["setup"]
    _ensure(isinstance(setup, dict), f"{path}: `setup` must be a mapping")
    _ensure(
        isinstance(setup.get("workspace_template"), str) and setup["workspace_template"],
        f"{path}: `setup.workspace_template` must be a non-empty string",
    )
    if "fixtures" in setup:
        _ensure(
            isinstance(setup["fixtures"], list),
            f"{path}: `setup.fixtures` must be a list when present",
        )
        for i, fix in enumerate(setup["fixtures"]):
            _ensure(
                isinstance(fix, dict),
                f"{path}: `setup.fixtures[{i}]` must be a mapping",
            )
    if "files" in setup:
        _ensure(
            isinstance(setup["files"], list),
            f"{path}: `setup.files` must be a list when present",
        )
        for i, entry in enumerate(setup["files"]):
            ctx = f"{path}:setup.files[{i}]"
            _ensure(isinstance(entry, dict), f"{ctx}: must be a mapping")
            file_path = entry.get("path")
            _ensure(
                isinstance(file_path, str) and file_path,
                f"{ctx}: `path` must be a non-empty string",
            )
            # Path safety: workspace-relative only. Reject absolute paths and
            # any segment that climbs out of the workspace via `..`.
            assert isinstance(file_path, str)  # narrowed by _ensure above
            _ensure(
                not file_path.startswith("/"),
                f"{ctx}: `path` must be workspace-relative, not absolute (got {file_path!r})",
            )
            _ensure(
                ".." not in Path(file_path).parts,
                f"{ctx}: `path` may not contain `..` traversal segments (got {file_path!r})",
            )
            _ensure(
                isinstance(entry.get("content"), str),
                f"{ctx}: `content` must be a string (got {type(entry.get('content')).__name__})",
            )

    evaluators = data["evaluators"]
    _ensure(
        isinstance(evaluators, list) and len(evaluators) >= 1,
        f"{path}: `evaluators` must be a non-empty list",
    )
    for i, ev in enumerate(evaluators):
        _validate_evaluator(ev, f"{path}:evaluators[{i}]")

    # `data` is already known to be `dict[str, Any]` from the earlier
    # `isinstance(data, dict)` check; mypy can't narrow through `_ensure`.
    return dict(data)


def scenario_warnings(data: dict[str, Any], path: Path) -> list[str]:
    """Return non-fatal warnings for a validated scenario.

    Warnings are advisory and never fail validation; `check_all` surfaces
    them on stderr so authors notice judge-only scenarios but can opt in
    explicitly. Per F-adv-5: at least one deterministic evaluator is the
    authoring convention, but judge-only scenarios are allowed.
    """
    warnings: list[str] = []
    evaluators = data.get("evaluators", []) or []
    has_deterministic = any(
        isinstance(ev, dict) and ev.get("type") == "deterministic" for ev in evaluators
    )
    if not has_deterministic:
        warnings.append(
            f"{path}: no `deterministic` evaluator — scenario relies entirely on "
            f"test_based / llm_judge signal. Consider adding a cheap "
            f"deterministic check (see SCHEMA.md authoring guidelines)."
        )
    return warnings


def discover_scenarios(root: Path) -> list[Path]:
    """Return sorted list of `*.yaml` scenario files under `root`."""
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.yaml") if p.is_file())


def check_all(root: Path) -> list[tuple[Path, str]]:
    """Validate every scenario under `root`. Returns list of (path, error_msg) failures."""
    failures: list[tuple[Path, str]] = []
    for path in discover_scenarios(root):
        try:
            validate_scenario(path)
        except ScenarioValidationError as exc:
            failures.append((path, str(exc)))
    return failures


def collect_warnings(root: Path) -> list[str]:
    """Walk every (validatable) scenario under `root` and collect advisory warnings.

    Scenarios that fail structural validation are skipped — `check_all`
    already reports those. Warnings are non-fatal: callers may print them
    but should not exit non-zero on warnings alone.
    """
    out: list[str] = []
    for path in discover_scenarios(root):
        try:
            data = validate_scenario(path)
        except ScenarioValidationError:
            continue
        out.extend(scenario_warnings(data, path))
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=DEFAULT_SCENARIOS_DIR,
        help=f"Directory containing scenario YAML files (default: {DEFAULT_SCENARIOS_DIR})",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    scenarios = discover_scenarios(args.scenarios_dir)
    if not scenarios:
        print(
            f"check_scenarios: no scenario files found under {args.scenarios_dir}",
            file=sys.stderr,
        )
        return 1

    failures = check_all(args.scenarios_dir)
    if failures:
        for path, msg in failures:
            print(f"FAIL {path}: {msg}", file=sys.stderr)
        print(
            f"\ncheck_scenarios: {len(failures)} of {len(scenarios)} scenarios failed",
            file=sys.stderr,
        )
        return 1

    warnings = collect_warnings(args.scenarios_dir)
    for w in warnings:
        print(f"WARN {w}", file=sys.stderr)

    print(f"check_scenarios: {len(scenarios)} scenarios OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
