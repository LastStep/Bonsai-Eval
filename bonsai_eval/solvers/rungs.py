"""The 3 rungs — Plan 38 §P0.3 Solver Strategy revision (2026-05-08).

Rungs 1 + 2 are thin wrappers around `inspect_swe` drop-ins
(`mini_swe_agent`, `claude_code`). Rung 3 is custom: it materializes a `station/`
workspace via `bonsai init` + `bonsai add` then invokes `inspect_swe.claude_code`
with the materialized dir as `cwd`.

All 3 factories enforce pre-registration via `assert_preregistration` at entry.
A solver caller that wants to run a different model / temp / tool-set must open
a new pre-reg claim and update `ACTIVE_PREREGISTRATION` in
`bonsai_eval.preregistration` — they cannot smuggle overrides through here.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from inspect_ai.agent import as_solver
from inspect_ai.solver import Generate, Solver, TaskState, chain, solver
from inspect_swe import claude_code, mini_swe_agent

from bonsai_eval.preregistration import (
    ACTIVE_PREREGISTRATION,
    PreregistrationConfig,
    PreregistrationViolation,
    assert_preregistration,
)

# `inspect-swe` version pin — Plan 38 §Risks #8. This must equal the version
# pinned in pyproject.toml; mismatch indicates a botched dependency upgrade.
INSPECT_SWE_VERSION_PIN = "0.2.51"

# `mini-swe-agent` CLI version pin — distinct from the inspect-swe package
# version. `inspect_swe.mini_swe_agent(version=...)` validates this against
# the mini-swe-agent CLI semver (must be >= 2.0.0; see
# `inspect_swe/_mini_swe_agent/setup.py:validate_version`). 2.2.3 is the
# pinned `"stable"` default in inspect-swe 0.2.51 — we encode it explicitly
# here for reproducibility instead of relying on the moving sentinel.
MINI_SWE_AGENT_VERSION = "2.2.3"

# Rung-1 system prompt floor — pinned text. This is the field's accepted
# "minimal harness" framing for mini-swe-agent (per Plan 38 §Risks #5).
RUNG1_SYSTEM_PROMPT = (
    "You are an autonomous software engineer. You have access to a single "
    "tool: bash. Use it to read, write, and run code as needed to complete "
    "the user's task. When done, stop."
)

# Bonsai non-interactive exit codes (mirrors `internal/nonint/runner.go`):
#   0 — success
#   2 — invalid config (shape rejected)
#   3 — runtime error (generator / save failure)
#   4 — wrong CWD for init (.bonsai.yaml already present)
BONSAI_EXIT_OK = 0
BONSAI_EXIT_INVALID_CONFIG = 2
BONSAI_EXIT_RUNTIME = 3
BONSAI_EXIT_WRONG_CWD = 4


def _validate_versions_match_preregistration(cfg: PreregistrationConfig) -> None:
    """Raise `PreregistrationViolation` if module constants drift from the pre-reg config."""
    mismatches: list[str] = []
    if cfg.mini_swe_agent_version != MINI_SWE_AGENT_VERSION:
        mismatches.append(
            f"  MINI_SWE_AGENT_VERSION: module={MINI_SWE_AGENT_VERSION!r}, "
            f"pre-reg={cfg.mini_swe_agent_version!r}"
        )
    if cfg.inspect_swe_version != INSPECT_SWE_VERSION_PIN:
        mismatches.append(
            f"  INSPECT_SWE_VERSION_PIN: module={INSPECT_SWE_VERSION_PIN!r}, "
            f"pre-reg={cfg.inspect_swe_version!r}"
        )
    if mismatches:
        raise PreregistrationViolation(
            "Solver-stack version drift — module constants do not match the "
            "locked pre-registration claim:\n" + "\n".join(mismatches)
        )


def _validate_preregistration(cfg: PreregistrationConfig | None) -> PreregistrationConfig:
    """Resolve to ACTIVE_PREREGISTRATION, then assert match. Returns the validated cfg."""
    effective = cfg if cfg is not None else ACTIVE_PREREGISTRATION
    assert_preregistration(effective, ACTIVE_PREREGISTRATION)
    _validate_versions_match_preregistration(effective)
    return effective


def rung1_raw_api(
    *,
    preregistration: PreregistrationConfig | None = None,
    **kwargs: Any,
) -> Solver:
    """Rung 1 — `inspect_swe.mini_swe_agent` drop-in (raw-API minimal loop).

    Tool loop is bash-only, matching mini-swe-agent's literal "minimal" framing.
    `version=` and `system_prompt=` are pinned for reproducibility.
    """
    cfg = _validate_preregistration(preregistration)
    agent = mini_swe_agent(
        model=cfg.model,
        system_prompt=RUNG1_SYSTEM_PROMPT,
        version=MINI_SWE_AGENT_VERSION,
        **kwargs,
    )
    return as_solver(agent)


def rung2_bare_cc(
    *,
    preregistration: PreregistrationConfig | None = None,
    cwd: str | Path | None = None,
    home_dir: Path | None = None,
    **kwargs: Any,
) -> Solver:
    """Rung 2 — `inspect_swe.claude_code` drop-in (bare Claude Code).

    Runs from a fresh temp dir by default — no `.claude/`, no `CLAUDE.md`,
    no `station/` materialization in the sandbox cwd. Workspace-file
    inheritance from the *host* `~/.claude/` is also suppressed by redirecting
    `HOME` to an empty tmp dir per Plan 38 §Risks #1 (re-opened 2026-05-14).

    See module-level docstring for the rationale.
    """
    cfg = _validate_preregistration(preregistration)
    if home_dir is None:
        raise ValueError(
            "rung2_bare_cc requires home_dir to prevent ambient "
            "~/.claude inheritance — pass an empty tmp dir per plan §Risks #1"
        )

    env = {"HOME": str(home_dir)}

    agent_kwargs: dict[str, Any] = dict(kwargs)
    if cwd is not None:
        agent_kwargs["cwd"] = str(cwd)

    agent = claude_code(
        model=cfg.model,
        env=env,
        **agent_kwargs,
    )
    return as_solver(agent)


# --- Rung 3 -----------------------------------------------------------------


# Subprocess-runner indirection so tests can monkeypatch the `bonsai` CLI.
# The real implementation calls `subprocess.run` exactly; tests replace this
# module attribute with a fake that records args + writes deterministic
# fixture output to the workspace. NO real `bonsai init` runs in pytest.
def _run_bonsai(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True)


def _decode_bonsai_error(
    result: subprocess.CompletedProcess[bytes], op: str, cfg_path: Path
) -> str:
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    return (
        f"bonsai {op} exit {result.returncode} for {cfg_path}:\nstderr: {stderr}\nstdout: {stdout}"
    )


def _raise_for_bonsai_exit(
    result: subprocess.CompletedProcess[bytes], op: str, cfg_path: Path
) -> None:
    """Translate a bonsai non-zero exit into a typed Python exception.

    Mirrors `internal/nonint/runner.go` exit codes:
      0 → success (caller checks separately)
      2 → invalid config        → ValueError (caller bug)
      3 → runtime failure       → RuntimeError
      4 → wrong CWD for op      → RuntimeError
      other → RuntimeError
    """
    if result.returncode == BONSAI_EXIT_OK:
        return
    msg = _decode_bonsai_error(result, op, cfg_path)
    if result.returncode == BONSAI_EXIT_INVALID_CONFIG:
        raise ValueError(msg)
    raise RuntimeError(msg)


# Bootstrap config used when the fixture targets a non-tech-lead agent. Resolved
# at call time so callers (notably tests) can override via the solver kwargs.
_DEFAULT_BOOTSTRAP_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures"
    / "configs"
    / "minimal"
    / ".bonsai.yaml"
)


def _materialize_bonsai_workspace(
    bonsai_config: Path,
    workspace: Path,
    bonsai_binary: str,
    bootstrap_config: Path | None = None,
) -> None:
    """Materialize a Bonsai workspace from `bonsai_config` inside `workspace`.

    Bonsai init only accepts a tech-lead-only config (exit 2 otherwise — see
    `internal/nonint/runner.go:RunInit`). For non-tech-lead fixtures we:
      1. init with `bootstrap_config` (the minimal tech-lead config) so the
         workspace skeleton + .bonsai.yaml exist; then
      2. add the fixture as an overlay via `bonsai add --from-config`.

    For tech-lead-only fixtures, init alone covers it — no add step.

    Exit-code translation lives in `_raise_for_bonsai_exit`.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    tech_only = _is_tech_lead_only_config(bonsai_config)
    init_cfg = bonsai_config if tech_only else (bootstrap_config or _DEFAULT_BOOTSTRAP_CONFIG_PATH)
    if not init_cfg.exists():
        raise FileNotFoundError(f"init config not found: {init_cfg}")
    init_result = _run_bonsai(
        [bonsai_binary, "init", "--non-interactive", "--from-config", str(init_cfg)],
        cwd=workspace,
    )
    _raise_for_bonsai_exit(init_result, "init", init_cfg)
    if tech_only:
        return
    add_result = _run_bonsai(
        [bonsai_binary, "add", "--non-interactive", "--from-config", str(bonsai_config)],
        cwd=workspace,
    )
    _raise_for_bonsai_exit(add_result, "add", bonsai_config)


def _is_tech_lead_only_config(bonsai_config: Path) -> bool:
    """True iff the fixture config has exactly one agent and it is `tech-lead`.

    For non-tech-lead fixtures we need to follow `bonsai init` (which requires
    a tech-lead) with `bonsai add` overlays per agent — but our fixtures are
    single-agent files, so the contract is simpler: tech-lead fixtures go
    through init alone; everything else gets init-then-add with a tech-lead
    bootstrap config first. Per the SCHEMA's `workspace_template` semantics,
    a fixture file describes exactly one agent (the one named in template).
    """
    try:
        cfg = yaml.safe_load(bonsai_config.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    agents = cfg.get("agents") or {}
    return isinstance(agents, dict) and list(agents.keys()) == ["tech-lead"]


def _materialize_setup_files(workspace: Path, files: list[dict[str, Any]]) -> None:
    """Write each `{path, content}` entry under `workspace`.

    Path safety: workspace-relative only. Absolute paths and any `..`
    traversal are rejected at runtime even though the schema validator
    already enforces it — defense in depth.
    """
    for entry in files:
        rel = entry.get("path")
        content = entry.get("content", "")
        if not isinstance(rel, str) or not rel:
            raise ValueError(f"setup.files entry missing or empty path: {entry!r}")
        if rel.startswith("/"):
            raise ValueError(f"setup.files path must be workspace-relative, got {rel!r}")
        if ".." in Path(rel).parts:
            raise ValueError(f"setup.files path may not contain `..` traversal: {rel!r}")
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else str(content), encoding="utf-8")


def _capture_baseline_hashes(
    workspace: Path,
    evaluators: list[dict[str, Any]],
) -> dict[str, str]:
    """SHA-256 every path referenced by a `file_unchanged` evaluator.

    Captures BEFORE the agent runs so the scorer can detect drift. Returns a
    dict keyed by the evaluator's literal `path` value (so `build_scorer`'s
    lookup matches verbatim). Missing files map to no entry — the
    `file_unchanged` helper interprets absence as "never existed".
    """
    out: dict[str, str] = {}
    for ev in evaluators:
        if not isinstance(ev, dict):
            continue
        if ev.get("type") != "deterministic" or ev.get("check") != "file_unchanged":
            continue
        path = ev.get("path")
        if not isinstance(path, str) or not path:
            continue
        target = Path(path) if Path(path).is_absolute() else workspace / path
        if target.exists() and target.is_file():
            out[path] = hashlib.sha256(target.read_bytes()).hexdigest()
    return out


@solver
def rung3_setup_solver(
    *,
    bonsai_config: Path,
    scenario: dict[str, Any],
    workspace: Path,
    bonsai_binary: str = "bonsai",
    bootstrap_config: Path | None = None,
) -> Solver:
    """Setup-phase solver that materializes the workspace and stashes metadata.

    Runs ONCE per task as the first link in the rung-3 chain. After this
    solver returns, the chain hands off to `claude_code(...)` with `cwd`
    pointing at `workspace`.

    Side effects on `state.metadata`:
      - `workspace_root`: Path — for `build_scorer` to resolve relative paths
      - `baseline_hashes`: dict[str, str] — for `file_unchanged` checks
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        del generate  # setup-only — we never call the model here
        _materialize_bonsai_workspace(
            bonsai_config, workspace, bonsai_binary, bootstrap_config=bootstrap_config
        )
        setup_files = (scenario.get("setup") or {}).get("files") or []
        if setup_files:
            _materialize_setup_files(workspace, setup_files)
        baseline = _capture_baseline_hashes(workspace, scenario.get("evaluators") or [])
        state.metadata = state.metadata or {}
        state.metadata["workspace_root"] = str(workspace)
        state.metadata["baseline_hashes"] = baseline
        return state

    return solve


def rung3_bonsai(
    *,
    bonsai_config: Path,
    scenario: dict[str, Any] | None = None,
    preregistration: PreregistrationConfig | None = None,
    bonsai_binary: str = "bonsai",
    workspace: Path | None = None,
    home_dir: Path | None = None,
    bootstrap_config: Path | None = None,
    **kwargs: Any,
) -> Solver:
    """Rung 3 — bare CC plus a Bonsai-materialized `station/` workspace.

    Runs `bonsai init --non-interactive --from-config <bonsai_config>` inside
    a fresh `workspace` directory (created on demand if not supplied), writes
    any `scenario.setup.files`, captures baseline hashes for `file_unchanged`
    evaluators, then invokes `inspect_swe.claude_code` with that dir as `cwd`.
    HOME is redirected to `home_dir` (per Plan 38 §Risks #1) to suppress
    ambient `~/.claude/` inheritance.

    Args:
      bonsai_config: Path to a fixture YAML (Bonsai `--from-config` shape).
      scenario: The fully-loaded scenario dict (from `validate_scenario`).
        `setup.files` and `evaluators` are read off this. Passing `None`
        skips setup.files + baseline_hashes (rare; used only when callers
        want a raw materialized workspace).
      home_dir: REQUIRED. Empty dir to redirect $HOME inside the sandbox.
      workspace: Optional pre-allocated workspace path. When omitted, a
        unique tmp dir is minted under `tempfile.gettempdir()`. Callers
        (e.g. `scripts/run_validation.py`) mint workspace per
        `(scenario, rung, seed)` for hermeticity.

    Returns the chained solver: setup → claude_code agent.
    """
    cfg = _validate_preregistration(preregistration)

    if not bonsai_config.exists():
        raise FileNotFoundError(f"bonsai_config not found: {bonsai_config}")
    if shutil.which(bonsai_binary) is None and not Path(bonsai_binary).exists():
        raise FileNotFoundError(
            f"bonsai binary not found: {bonsai_binary} "
            "(install Bonsai first: `go install ./cmd/bonsai` from the Bonsai repo)"
        )
    if home_dir is None:
        raise ValueError(
            "rung3_bonsai requires home_dir to prevent ambient "
            "~/.claude inheritance — pass an empty tmp dir per plan §Risks #1"
        )

    if workspace is None:
        workspace = Path(tempfile.gettempdir()) / f"bonsai-eval-rung3-{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, exist_ok=True)

    scenario = scenario or {}
    setup = rung3_setup_solver(
        bonsai_config=bonsai_config,
        scenario=scenario,
        workspace=workspace,
        bonsai_binary=bonsai_binary,
        bootstrap_config=bootstrap_config,
    )

    env = {"HOME": str(home_dir)}
    agent_kwargs: dict[str, Any] = dict(kwargs)
    agent_kwargs.setdefault("cwd", str(workspace))
    agent_kwargs.setdefault("env", env)
    agent = claude_code(model=cfg.model, **agent_kwargs)

    return chain(setup, as_solver(agent))
