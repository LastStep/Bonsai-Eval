"""Inspect AI task-discovery tests for `bonsai_eval/tasks/bonsai_behavioral.py`.

Verifies — offline, no API call — that:

  - All 12 scenario YAMLs under `scenarios/bonsai_behavioral/` are loaded
    and registered as Inspect `@task` functions.
  - `inspect_ai._eval.list.list_tasks` (the API behind `inspect list
    tasks`) returns them all with the expected kebab-case names.
  - Each task constructs cleanly (instantiating yields a `Task` with the
    expected sample, scorer, sandbox).

Run via `make test`; the suite is offline and mocks nothing — task
construction never calls the model.
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task
from inspect_ai._eval.list import list_tasks

from bonsai_eval.tasks import bonsai_behavioral as tasks_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = REPO_ROOT / "bonsai_eval" / "tasks" / "bonsai_behavioral.py"
# `list_tasks` requires a glob string RELATIVE to its `root_dir` (it uses
# `Path.glob` which rejects absolute patterns); express the file as a
# repo-relative POSIX path.
TASKS_FILE_REL = TASKS_FILE.relative_to(REPO_ROOT).as_posix()

EXPECTED_SCENARIO_IDS: frozenset[str] = frozenset(
    {
        "audit-security-loads-security-skill",
        "code-agent-asked-to-plan",
        "cross-domain-suggestion-flagged-not-fixed",
        "dispatch-without-plan-refused",
        "edit-outside-workspace-blocked",
        "plan-feature-loads-planning-workflow",
        "plan-followed-end-to-end",
        "resume-task-references-prior-decisions",
        "review-pr-loads-review-workflow",
        "session-start-reads-memory",
        "tech-lead-asked-to-code",
        "tech-lead-given-completion-report",
    }
)


def test_list_tasks_returns_all_twelve_scenarios() -> None:
    """`inspect list tasks` (AST-based) finds every scenario."""
    discovered = list_tasks([TASKS_FILE_REL], root_dir=REPO_ROOT)
    names = {ti.name for ti in discovered}
    assert names == EXPECTED_SCENARIO_IDS, (
        f"task discovery drift — got {sorted(names)}, want {sorted(EXPECTED_SCENARIO_IDS)}"
    )
    assert len(discovered) == 12


def test_every_scenario_yaml_has_a_matching_task() -> None:
    """Cross-check filesystem vs. module: no orphans either way."""
    on_disk = {p.stem for p in tasks_mod.SCENARIOS_DIR.glob("*.yaml")}
    assert on_disk == EXPECTED_SCENARIO_IDS


def test_each_task_constructs_to_a_real_task_object() -> None:
    """Instantiating each @task function yields a usable Task."""
    for scenario_id in EXPECTED_SCENARIO_IDS:
        # `bonsai_behavioral.<snake_id>` is the function reference Inspect
        # registered. Call it to materialise the `Task`.
        snake = scenario_id.replace("-", "_")
        fn = getattr(tasks_mod, snake)
        t = fn()
        assert isinstance(t, Task), f"{scenario_id}: expected Task, got {type(t).__name__}"
        # The Task wraps a one-sample dataset with the scenario id.
        samples = list(t.dataset)
        assert len(samples) == 1
        assert samples[0].id == scenario_id
        # Sandbox must be Docker — rungs 2 + 3 require it.
        assert t.sandbox is not None
        # Name pinned via `@task(name=...)`.
        assert t.name == scenario_id


def _extract_sandbox_type(sandbox_spec: object) -> str:
    """Inspect's `Task(sandbox=...)` accepts a `str` or a `SandboxEnvironmentSpec`.

    Constructing `Task(..., sandbox="docker")` produces a
    `SandboxEnvironmentSpec(type="docker", ...)` on `Task.sandbox`. This
    helper handles both shapes so we can assert on the type uniformly
    without coupling the test to Inspect's internals.
    """
    if isinstance(sandbox_spec, str):
        return sandbox_spec
    return getattr(sandbox_spec, "type", "")


def test_sandbox_is_docker_for_every_rung() -> None:
    """All three rungs must construct tasks with `sandbox="docker"`.

    Regression test for the 2026-05-14 live-smoke `ProcessLookupError`:
    `inspect_swe.mini_swe_agent` (rung-1's drop-in) dispatches bash
    through `inspect_ai.util.sandbox(...).exec_remote(...)` just like
    `inspect_swe.claude_code` (rungs 2 + 3), so a `Task` built without a
    sandbox raises at run-time. See `_sandbox_for_rung` for the gory
    details. The fix unifies all three rungs on Docker; this test pins
    that invariant.
    """
    # Use one scenario — `_sandbox_for_rung` doesn't depend on scenario id,
    # so checking one is sufficient to pin the rung→sandbox mapping.
    scenario_id = "audit-security-loads-security-skill"
    fn = getattr(tasks_mod, scenario_id.replace("-", "_"))
    for rung in ("rung1", "rung2", "rung3"):
        t = fn(rung=rung)
        sb_type = _extract_sandbox_type(t.sandbox)
        assert sb_type == "docker", (
            f"{scenario_id} @ {rung}: expected sandbox='docker', "
            f"got {t.sandbox!r} (type={sb_type!r})"
        )


def test_sandbox_for_rung_helper_rejects_unknown_rung() -> None:
    """`_sandbox_for_rung` validates its input alongside `_solver_for_rung`."""
    import pytest

    assert tasks_mod._sandbox_for_rung("rung1") == "docker"
    assert tasks_mod._sandbox_for_rung("rung2") == "docker"
    assert tasks_mod._sandbox_for_rung("rung3") == "docker"
    with pytest.raises(ValueError, match="unknown rung"):
        tasks_mod._sandbox_for_rung("rung4")


def test_scenarios_dir_resolves_to_repo_root() -> None:
    """Guard against import-time path miscomputation."""
    assert tasks_mod.SCENARIOS_DIR == REPO_ROOT / "scenarios" / "bonsai_behavioral"
    assert tasks_mod.SCENARIOS_DIR.exists()
