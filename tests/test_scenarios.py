"""Scenario YAML structural validation tests — non-API.

Wraps `scripts/check_scenarios.py` (Plan 38 §P2.1 + §P2.2). Parametrized over
every scenario YAML under `scenarios/bonsai_behavioral/` so each one shows up
as its own test in the pytest output — easier to spot which scenario broke
than a single aggregated assertion.

Also includes a corpus-level test that the bundled starter suite is complete
(per plan §P2.2: 12 scenarios across 5 categories).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = REPO_ROOT / "scenarios" / "bonsai_behavioral"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_scenarios.py"


def _load_check_module() -> object:
    """Import `scripts/check_scenarios.py` as a module without polluting sys.path globally."""
    spec = importlib.util.spec_from_file_location("check_scenarios", CHECK_SCRIPT)
    assert spec is not None and spec.loader is not None, (
        f"could not load module spec for {CHECK_SCRIPT}"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_scenarios", module)
    spec.loader.exec_module(module)
    return module


CHECK = _load_check_module()


def _discover() -> list[Path]:
    return CHECK.discover_scenarios(SCENARIOS_DIR)  # type: ignore[attr-defined,no-any-return]


SCENARIO_PATHS: list[Path] = _discover()


@pytest.mark.parametrize(
    "scenario_path",
    SCENARIO_PATHS,
    ids=[p.stem for p in SCENARIO_PATHS],
)
def test_scenario_schema(scenario_path: Path) -> None:
    """Each scenario YAML must satisfy the SCHEMA.md contract."""
    data = CHECK.validate_scenario(scenario_path)  # type: ignore[attr-defined]
    # Spot-check: validate_scenario returned a dict with the right id.
    assert data["id"] == scenario_path.stem


def test_starter_suite_size() -> None:
    """Plan 38 §P2.2 specifies 12 starter scenarios; lock the count."""
    assert len(SCENARIO_PATHS) == 12, (
        f"expected 12 starter scenarios per Plan 38 §P2.2, found {len(SCENARIO_PATHS)}: "
        f"{[p.name for p in SCENARIO_PATHS]}"
    )


def test_starter_suite_category_coverage() -> None:
    """Plan 38 §P2.2: 3 role-discipline + 2 plan-gating + 2 scope-boundaries
    + 2 memory-continuity + 3 workflow-invocation."""
    import yaml

    counts: dict[str, int] = {}
    for path in SCENARIO_PATHS:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        counts[data["category"]] = counts.get(data["category"], 0) + 1

    expected = {
        "role-discipline": 3,
        "plan-gating": 2,
        "scope-boundaries": 2,
        "memory-continuity": 2,
        "workflow-invocation": 3,
    }
    assert counts == expected, f"category counts {counts} != plan-spec {expected}"


def test_check_script_runs_clean_on_starter_suite() -> None:
    """End-to-end: the validator script returns 0 against the bundled scenarios."""
    failures = CHECK.check_all(SCENARIOS_DIR)  # type: ignore[attr-defined]
    assert failures == [], f"check_scenarios reported failures: {failures}"


def test_validator_rejects_bash_tool_call_with_path(tmp_path: Path) -> None:
    """Review F1+F2: a `tool_call_*` evaluator with `tool: Bash` must use
    `command`, not `path` — the Claude/Inspect Bash tool's argument is named
    `command`. The validator must reject the `path` form so authors don't
    write scenarios that look right but match nothing at runtime.
    """
    import yaml as _yaml  # local import — kept out of module globals

    bad_scenario = {
        "id": "bad-bash-uses-path",
        "description": "Synthetic scenario: tool: Bash with path is invalid.",
        "category": "role-discipline",
        "prompt": "run something",
        "setup": {"workspace_template": "tech-lead"},
        "evaluators": [
            {
                "type": "deterministic",
                "check": "tool_call_made",
                "tool": "Bash",
                # Wrong on purpose — Bash tool's arg is `command`, not `path`.
                "path": "gh pr",
            }
        ],
    }
    bad_path = tmp_path / "bad-bash-uses-path.yaml"
    bad_path.write_text(_yaml.safe_dump(bad_scenario), encoding="utf-8")

    with pytest.raises(CHECK.ScenarioValidationError) as exc_info:  # type: ignore[attr-defined]
        CHECK.validate_scenario(bad_path)  # type: ignore[attr-defined]

    msg = str(exc_info.value)
    assert "Bash" in msg and "command" in msg, (
        f"validator should explain the Bash-needs-command rule; got: {msg!r}"
    )

    # And the corrected form (command, no path) should validate cleanly.
    good_scenario = dict(bad_scenario)
    good_scenario["id"] = "good-bash-uses-command"
    good_scenario["evaluators"] = [
        {
            "type": "deterministic",
            "check": "tool_call_made",
            "tool": "Bash",
            "command": "gh pr",
        }
    ]
    good_path = tmp_path / "good-bash-uses-command.yaml"
    good_path.write_text(_yaml.safe_dump(good_scenario), encoding="utf-8")
    CHECK.validate_scenario(good_path)  # type: ignore[attr-defined]  # must not raise

    # Symmetric: a non-Bash tool with `command` instead of `path` is rejected.
    wrong_tool_scenario = dict(bad_scenario)
    wrong_tool_scenario["id"] = "bad-read-uses-command"
    wrong_tool_scenario["evaluators"] = [
        {
            "type": "deterministic",
            "check": "tool_call_made",
            "tool": "Read",
            "command": "should-not-be-here",
        }
    ]
    wrong_tool_path = tmp_path / "bad-read-uses-command.yaml"
    wrong_tool_path.write_text(_yaml.safe_dump(wrong_tool_scenario), encoding="utf-8")
    with pytest.raises(CHECK.ScenarioValidationError) as exc_info_2:  # type: ignore[attr-defined]
        CHECK.validate_scenario(wrong_tool_path)  # type: ignore[attr-defined]
    assert "command" in str(exc_info_2.value)


# --- F-adv-6: validator coverage for the second-amend additions ---


def _make_base_scenario(scenario_id: str) -> dict[str, object]:
    """Minimal valid scenario skeleton used by the F-adv-6 tests."""
    return {
        "id": scenario_id,
        "description": "Synthetic scenario for validator tests.",
        "category": "plan-gating",
        "prompt": "stub prompt",
        "setup": {
            "workspace_template": "tech-lead",
            "fixtures": [{"bonsai_config": "minimal"}],
        },
        "evaluators": [
            {
                "type": "deterministic",
                "check": "file_exists",
                "path": "station/Playbook/Plans/Active/51-rename-cli-flag.md",
            }
        ],
    }


def test_validator_accepts_files_fixture(tmp_path: Path) -> None:
    """F-adv-6: `setup.files[]` with valid `path` + `content` is accepted."""
    import yaml as _yaml

    scenario = _make_base_scenario("good-files-entry")
    setup_obj = scenario["setup"]
    assert isinstance(setup_obj, dict)
    setup_obj["files"] = [
        {
            "path": "station/Playbook/Plans/Active/51-rename-cli-flag.md",
            "content": "# Plan 51\nTier-1 mechanical refactor.\n",
        }
    ]
    p = tmp_path / "good-files-entry.yaml"
    p.write_text(_yaml.safe_dump(scenario), encoding="utf-8")
    CHECK.validate_scenario(p)  # type: ignore[attr-defined]  # must not raise


def test_validator_rejects_files_path_with_parent_traversal(tmp_path: Path) -> None:
    """F-adv-6: paths containing `..` are rejected (sandbox escape guard)."""
    import yaml as _yaml

    scenario = _make_base_scenario("bad-files-traversal")
    setup_obj = scenario["setup"]
    assert isinstance(setup_obj, dict)
    setup_obj["files"] = [{"path": "../etc/passwd", "content": "root::0:0::/root:/bin/sh\n"}]
    p = tmp_path / "bad-files-traversal.yaml"
    p.write_text(_yaml.safe_dump(scenario), encoding="utf-8")
    with pytest.raises(CHECK.ScenarioValidationError) as exc_info:  # type: ignore[attr-defined]
        CHECK.validate_scenario(p)  # type: ignore[attr-defined]
    assert ".." in str(exc_info.value) or "traversal" in str(exc_info.value)


def test_validator_rejects_unknown_hook_name(tmp_path: Path) -> None:
    """F-adv-6: a `hook_event_fired.hook` value not matching any sensor stem
    under `station/agent/Sensors/*.sh` is rejected with a clear message.
    """
    import yaml as _yaml

    # Skip if the validator couldn't discover any sensor hooks (e.g.
    # running from an unbootstrapped checkout) — the cross-check is a no-op
    # in that mode by design.
    if not CHECK.KNOWN_HOOKS:  # type: ignore[attr-defined]
        pytest.skip("no sensor hooks discovered; hook-name cross-check disabled")

    scenario = _make_base_scenario("bad-unknown-hook")
    scenario["evaluators"] = [
        {
            "type": "deterministic",
            "check": "hook_event_fired",
            # Typo of a real hook name — must be rejected.
            "hook": "scope-guard-fil",
        }
    ]
    p = tmp_path / "bad-unknown-hook.yaml"
    p.write_text(_yaml.safe_dump(scenario), encoding="utf-8")
    with pytest.raises(CHECK.ScenarioValidationError) as exc_info:  # type: ignore[attr-defined]
        CHECK.validate_scenario(p)  # type: ignore[attr-defined]
    msg = str(exc_info.value)
    assert "unknown hook" in msg and "scope-guard-fil" in msg
