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

    print(f"check_scenarios: {len(scenarios)} scenarios OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
