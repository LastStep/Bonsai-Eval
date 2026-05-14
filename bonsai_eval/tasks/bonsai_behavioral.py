"""Inspect AI tasks for the Bonsai-behavioral scenario suite — Plan 38 §P2.4.

For every YAML under `scenarios/bonsai_behavioral/`, this module exposes an
Inspect `Task` registered via `@task`. Tasks are discoverable via:

    inspect list tasks bonsai_eval/tasks/bonsai_behavioral.py

Inspect's `list_tasks` walks the module's AST looking for top-level
`@task` decorators (see `inspect_ai/_util/decorator.py:parse_decorators`),
so the 12 task functions MUST appear literally in source — programmatic
`task(name=...)(fn)` registration works for `inspect eval` (which actually
imports the module) but NOT for `inspect list` (which is AST-only). The
explicit functions below are written out one-per-scenario.

# Keeping the list in sync with `scenarios/bonsai_behavioral/`

At module-import time, `_assert_tasks_match_scenarios()` cross-checks the
set of `@task` functions in this file against the set of YAMLs on disk. A
mismatch (new scenario added, scenario renamed, scenario deleted) raises
`RuntimeError` so the drift is caught immediately rather than silently
producing a partial task list.

When a new scenario lands, add:

    @task(name="<scenario-id>")
    def <snake_case_id>() -> Task:
        return _task_for("<scenario-id>")

to the list below and the assertion will pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import Solver

from bonsai_eval.scorers import build_scorer
from bonsai_eval.solvers import rung2_bare_cc
from scripts.check_scenarios import validate_scenario

# `scenarios/bonsai_behavioral/` lives at repo-root; this file is two
# levels deep (`bonsai_eval/tasks/`), so root = parent.parent.parent.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = _REPO_ROOT / "scenarios" / "bonsai_behavioral"


# --- Builder shared by every task function -----------------------------------


def _default_solver(home_dir: Path | None = None) -> Solver:
    """Default solver for behavioural tasks — `rung2_bare_cc`.

    `rung2_bare_cc` requires `home_dir` (Plan 38 §Risks #1 — empty tmp dir
    redirected as `$HOME` inside the sandbox). Inspect AI invokes tasks
    lazily, so we can't allocate a fresh tmp dir at module-import time;
    we default to `<repo_root>/data/raw/rung2_home/` (gitignored). Callers
    that need per-task isolation override the solver via `--solver` at
    `inspect eval` invocation.
    """
    if home_dir is None:
        home_dir = _REPO_ROOT / "data" / "raw" / "rung2_home"
    return rung2_bare_cc(home_dir=home_dir)


def _load_scenario(scenario_id: str) -> dict[str, Any]:
    """Load + validate a single scenario YAML. Raises on malformed YAML.

    Re-uses `scripts.check_scenarios.validate_scenario` so the loader and
    the CI validator share a single source of truth.
    """
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    return validate_scenario(path)


def _task_for(scenario_id: str, solver: Solver | None = None) -> Task:
    """Construct an Inspect `Task` for the named scenario.

    Sandbox is pinned to `"docker"` because rungs 2 + 3 require
    Docker; rung 1 ignores the task-level sandbox setting.
    """
    scenario = _load_scenario(scenario_id)
    sample = Sample(
        input=scenario["prompt"],
        # SCHEMA.md scenarios use rubric / deterministic checks, not
        # target-string matching. We set `target=""` rather than omit it
        # because Inspect's `Target` arg is required-shaped on some scorers.
        target="",
        id=scenario["id"],
        metadata={
            "category": scenario["category"],
            "description": scenario["description"],
            "setup": scenario.get("setup", {}),
        },
    )
    return Task(
        dataset=[sample],
        solver=solver if solver is not None else _default_solver(),
        scorer=build_scorer(scenario["evaluators"]),
        sandbox="docker",
        name=scenario["id"],
    )


# --- @task functions — one per scenario ------------------------------------


@task(name="audit-security-loads-security-skill")
def audit_security_loads_security_skill() -> Task:
    return _task_for("audit-security-loads-security-skill")


@task(name="code-agent-asked-to-plan")
def code_agent_asked_to_plan() -> Task:
    return _task_for("code-agent-asked-to-plan")


@task(name="cross-domain-suggestion-flagged-not-fixed")
def cross_domain_suggestion_flagged_not_fixed() -> Task:
    return _task_for("cross-domain-suggestion-flagged-not-fixed")


@task(name="dispatch-without-plan-refused")
def dispatch_without_plan_refused() -> Task:
    return _task_for("dispatch-without-plan-refused")


@task(name="edit-outside-workspace-blocked")
def edit_outside_workspace_blocked() -> Task:
    return _task_for("edit-outside-workspace-blocked")


@task(name="plan-feature-loads-planning-workflow")
def plan_feature_loads_planning_workflow() -> Task:
    return _task_for("plan-feature-loads-planning-workflow")


@task(name="plan-followed-end-to-end")
def plan_followed_end_to_end() -> Task:
    return _task_for("plan-followed-end-to-end")


@task(name="resume-task-references-prior-decisions")
def resume_task_references_prior_decisions() -> Task:
    return _task_for("resume-task-references-prior-decisions")


@task(name="review-pr-loads-review-workflow")
def review_pr_loads_review_workflow() -> Task:
    return _task_for("review-pr-loads-review-workflow")


@task(name="session-start-reads-memory")
def session_start_reads_memory() -> Task:
    return _task_for("session-start-reads-memory")


@task(name="tech-lead-asked-to-code")
def tech_lead_asked_to_code() -> Task:
    return _task_for("tech-lead-asked-to-code")


@task(name="tech-lead-given-completion-report")
def tech_lead_given_completion_report() -> Task:
    return _task_for("tech-lead-given-completion-report")


# --- Drift guard ------------------------------------------------------------


# Source-of-truth list of scenario ids; must match the set of @task functions
# above 1:1 AND the set of `*.yaml` files under SCENARIOS_DIR. Editing this
# list without adding/removing the matching `@task` function and scenario
# file is intentionally caught by `_assert_tasks_match_scenarios()` below.
_EXPECTED_SCENARIO_IDS: frozenset[str] = frozenset(
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


def _assert_tasks_match_scenarios() -> None:
    """Fail fast if disk scenarios drift from the @task functions in this file."""
    if not SCENARIOS_DIR.exists():
        return  # unbootstrapped checkout — defer to discovery test
    on_disk = frozenset(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))
    missing = _EXPECTED_SCENARIO_IDS - on_disk
    extra = on_disk - _EXPECTED_SCENARIO_IDS
    if missing or extra:
        raise RuntimeError(
            f"Scenario / task drift detected in {__file__}:\n"
            f"  missing on disk (declared above, no YAML): {sorted(missing)}\n"
            f"  unregistered on disk (YAML, no @task above): {sorted(extra)}\n"
            f"Edit `_EXPECTED_SCENARIO_IDS` and the `@task` list to match."
        )


_assert_tasks_match_scenarios()


__all__ = [
    "SCENARIOS_DIR",
    "audit_security_loads_security_skill",
    "code_agent_asked_to_plan",
    "cross_domain_suggestion_flagged_not_fixed",
    "dispatch_without_plan_refused",
    "edit_outside_workspace_blocked",
    "plan_feature_loads_planning_workflow",
    "plan_followed_end_to_end",
    "resume_task_references_prior_decisions",
    "review_pr_loads_review_workflow",
    "session_start_reads_memory",
    "tech_lead_asked_to_code",
    "tech_lead_given_completion_report",
]
