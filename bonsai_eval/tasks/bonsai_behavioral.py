"""Inspect AI tasks for the Bonsai-behavioral scenario suite — Plan 38 §P2.4 + §P2.5.

For every YAML under `scenarios/bonsai_behavioral/`, this module exposes an
Inspect `Task` registered via `@task`. Tasks are discoverable via:

    inspect list tasks bonsai_eval/tasks/bonsai_behavioral.py

Inspect's `list_tasks` walks the module's AST looking for top-level
`@task` decorators (see `inspect_ai/_util/decorator.py:parse_decorators`),
so the 12 task functions MUST appear literally in source — programmatic
`task(name=...)(fn)` registration works for `inspect eval` (which actually
imports the module) but NOT for `inspect list` (which is AST-only). The
explicit functions below are written out one-per-scenario.

# Per-task solver injection (P2.5)

Each task accepts a `rung: str = "rung2"` keyword argument that selects the
solver at task-construction time. Inspect AI's `inspect eval` forwards
`--arg rung=rung3` (or `task_args={"rung": "rung3"}` programmatically) into
the task function, so a single `@task` definition covers all three rungs.

Valid rung values:
  - `"rung1"` → `rung1_raw_api` — raw-API mini-swe-agent (docker sandbox)
  - `"rung2"` → `rung2_bare_cc` — bare Claude Code (docker sandbox)
  - `"rung3"` → `rung3_bonsai`  — bare CC + Bonsai-materialized workspace

All three rungs route bash through `inspect_ai.util.sandbox(...)`
(mini-swe-agent calls `sbox.exec_remote` just like claude-code does), so
every task is constructed with `sandbox="docker"`. See
`_sandbox_for_rung` for the live-smoke regression that drove this.

Per-`(scenario, rung, seed)` HOME / workspace isolation is the CALLER's
responsibility — `scripts/run_validation.py` mints a unique `data/raw/runs/
<scenario>-<rung>-<seed>-home` per run and passes it via `task_args`. When
invoked WITHOUT `home_dir` / `workspace`, the tasks fall back to a
deterministic-per-process tmp dir so `inspect eval <task>` still works for
exploratory smoke-testing.

# Keeping the list in sync with `scenarios/bonsai_behavioral/`

At module-import time, `_assert_tasks_match_scenarios()` cross-checks the
set of `@task` functions in this file against the set of YAMLs on disk. A
mismatch (new scenario added, scenario renamed, scenario deleted) raises
`RuntimeError` so the drift is caught immediately rather than silently
producing a partial task list.

When a new scenario lands, add:

    @task(name="<scenario-id>")
    def <snake_case_id>(rung: str = "rung2", **kwargs: Any) -> Task:
        return _task_for("<scenario-id>", rung=rung, **kwargs)

to the list below and the assertion will pass.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import Solver

from bonsai_eval.preregistration import ACTIVE_PREREGISTRATION
from bonsai_eval.scorers import build_scorer
from bonsai_eval.solvers import rung1_raw_api, rung2_bare_cc, rung3_bonsai
from scripts.check_scenarios import validate_scenario

# `scenarios/bonsai_behavioral/` lives at repo-root; this file is two
# levels deep (`bonsai_eval/tasks/`), so root = parent.parent.parent.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = _REPO_ROOT / "scenarios" / "bonsai_behavioral"
FIXTURES_DIR = _REPO_ROOT / "fixtures" / "configs"

VALID_RUNGS: frozenset[str] = frozenset({"rung1", "rung2", "rung3"})


# --- Builder shared by every task function -----------------------------------


def _load_scenario(scenario_id: str) -> dict[str, Any]:
    """Load + validate a single scenario YAML. Raises on malformed YAML.

    Re-uses `scripts.check_scenarios.validate_scenario` so the loader and
    the CI validator share a single source of truth.
    """
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    return validate_scenario(path)


def _resolve_bonsai_config(scenario: dict[str, Any]) -> Path:
    """Resolve `scenario.setup.fixtures[0].bonsai_config` to a fixture path.

    Schema guarantees `setup.fixtures` is a list of `{bonsai_config: <name>}`
    entries; we use the first. Returns `<repo>/fixtures/configs/<name>/.bonsai.yaml`.
    """
    fixtures = (scenario.get("setup") or {}).get("fixtures") or []
    if not fixtures:
        raise ValueError(
            f"scenario {scenario.get('id')!r} has no setup.fixtures — "
            "rung-3 cannot materialise a workspace without a fixture name"
        )
    name = fixtures[0].get("bonsai_config")
    if not isinstance(name, str) or not name:
        raise ValueError(
            f"scenario {scenario.get('id')!r} fixtures[0].bonsai_config is "
            f"missing or not a string: {fixtures[0]!r}"
        )
    return FIXTURES_DIR / name / ".bonsai.yaml"


def _ephemeral_home(scenario_id: str, rung: str, seed: int | None) -> Path:
    """Mint a deterministic-shaped HOME dir for a given (scenario, rung, seed).

    The directory is created on demand. `scripts/run_validation.py` minted
    its own paths under `data/raw/runs/`; this fallback lives under
    `tempfile.gettempdir()` so smoke-test `inspect eval <task>` invocations
    don't pollute the workspace.
    """
    suffix = uuid.uuid4().hex[:8] if seed is None else f"seed{seed}"
    root = Path(tempfile.gettempdir()) / f"bonsai-eval-{scenario_id}-{rung}-{suffix}-home"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _solver_for_rung(
    rung: str,
    scenario: dict[str, Any],
    *,
    home_dir: Path | None,
    workspace: Path | None,
    seed: int | None,
) -> Solver:
    """Dispatch on `rung` → matching solver factory.

    Per-rung wiring (Plan 38 §P0.3 + §Risks #1):
      - rung1: model only; no HOME / workspace.
      - rung2: bare CC + isolated HOME.
      - rung3: bare CC + Bonsai-materialized workspace + isolated HOME.
    """
    if rung not in VALID_RUNGS:
        raise ValueError(f"unknown rung {rung!r}; expected one of {sorted(VALID_RUNGS)}")
    scenario_id = scenario["id"]
    if rung == "rung1":
        return rung1_raw_api()
    effective_home = home_dir if home_dir is not None else _ephemeral_home(scenario_id, rung, seed)
    if rung == "rung2":
        return rung2_bare_cc(home_dir=effective_home)
    # rung == "rung3"
    bonsai_config = _resolve_bonsai_config(scenario)
    effective_workspace = (
        workspace
        if workspace is not None
        else (
            Path(tempfile.gettempdir())
            / f"bonsai-eval-{scenario_id}-rung3-{(seed if seed is not None else uuid.uuid4().hex[:8])}-ws"
        )
    )
    return rung3_bonsai(
        bonsai_config=bonsai_config,
        scenario=scenario,
        home_dir=effective_home,
        workspace=effective_workspace,
    )


def _sandbox_for_rung(rung: str) -> str | None:
    """All three rungs need a Docker sandbox.

    Rung-1's `inspect_swe.mini_swe_agent` drop-in resolves
    `inspect_ai.util.sandbox(...)` at run-time and dispatches bash via
    `sbox.exec_remote(...)` (see
    `inspect_swe/_mini_swe_agent/mini_swe_agent.py:142`). Without a
    sandbox declared on the `Task`, Inspect raises
    `ProcessLookupError: No sandbox environment has been provided for
    the current sample or task`. The P0.2 smoke `tests/test_substrate.py`
    Case B works precisely because it builds the task with
    `Task(sandbox="docker")` explicitly. Rungs 2 + 3 obviously need
    Docker (their `inspect_swe.claude_code` drop-in does the same
    sandbox-routed exec).

    The previous gating (`None if rung == "rung1" else "docker"`)
    surfaced as a live-smoke failure after P2.5 (2026-05-14); fix is to
    return `"docker"` uniformly.
    """
    if rung not in VALID_RUNGS:
        raise ValueError(f"unknown rung {rung!r}; expected one of {sorted(VALID_RUNGS)}")
    return "docker"


def _task_for(
    scenario_id: str,
    *,
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
    solver: Solver | None = None,
) -> Task:
    """Construct an Inspect `Task` for the named scenario at the chosen rung.

    Caller may pass `solver=` to fully override solver selection (for tests
    + advanced dispatch). Otherwise `_solver_for_rung` chooses based on
    `rung`. `home_dir` / `workspace` / `seed` flow into rung-specific
    factories; see `_solver_for_rung`.
    """
    scenario = _load_scenario(scenario_id)
    effective_solver = (
        solver
        if solver is not None
        else _solver_for_rung(rung, scenario, home_dir=home_dir, workspace=workspace, seed=seed)
    )
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
            "rung": rung,
            "seed": seed,
        },
    )
    return Task(
        dataset=[sample],
        solver=effective_solver,
        scorer=build_scorer(scenario["evaluators"]),
        sandbox=_sandbox_for_rung(rung),
        name=scenario["id"],
    )


# Pre-registered model — exported for `scripts/run_validation.py` so the CLI
# uses the same model identity the solvers will validate against.
ACTIVE_MODEL = ACTIVE_PREREGISTRATION.model


# --- @task functions — one per scenario ------------------------------------


@task(name="audit-security-loads-security-skill")
def audit_security_loads_security_skill(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "audit-security-loads-security-skill",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="code-agent-asked-to-plan")
def code_agent_asked_to_plan(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "code-agent-asked-to-plan",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="cross-domain-suggestion-flagged-not-fixed")
def cross_domain_suggestion_flagged_not_fixed(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "cross-domain-suggestion-flagged-not-fixed",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="dispatch-without-plan-refused")
def dispatch_without_plan_refused(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "dispatch-without-plan-refused",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="edit-outside-workspace-blocked")
def edit_outside_workspace_blocked(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "edit-outside-workspace-blocked",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="plan-feature-loads-planning-workflow")
def plan_feature_loads_planning_workflow(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "plan-feature-loads-planning-workflow",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="plan-followed-end-to-end")
def plan_followed_end_to_end(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "plan-followed-end-to-end",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="resume-task-references-prior-decisions")
def resume_task_references_prior_decisions(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "resume-task-references-prior-decisions",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="review-pr-loads-review-workflow")
def review_pr_loads_review_workflow(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "review-pr-loads-review-workflow",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="session-start-reads-memory")
def session_start_reads_memory(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "session-start-reads-memory",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="tech-lead-asked-to-code")
def tech_lead_asked_to_code(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "tech-lead-asked-to-code",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


@task(name="tech-lead-given-completion-report")
def tech_lead_given_completion_report(
    rung: str = "rung2",
    home_dir: Path | None = None,
    workspace: Path | None = None,
    seed: int | None = None,
) -> Task:
    return _task_for(
        "tech-lead-given-completion-report",
        rung=rung,
        home_dir=home_dir,
        workspace=workspace,
        seed=seed,
    )


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
    "ACTIVE_MODEL",
    "FIXTURES_DIR",
    "SCENARIOS_DIR",
    "VALID_RUNGS",
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
