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
