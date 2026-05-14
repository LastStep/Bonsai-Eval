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

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from inspect_ai.agent import as_solver
from inspect_ai.solver import Solver
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


def _validate_versions_match_preregistration(cfg: PreregistrationConfig) -> None:
    """Raise `PreregistrationViolation` if module constants drift from the pre-reg config.

    Plan 38 §"Pre-Registration" + §P0.3 require pre-reg integrity to be
    machine-checkable. The solver-stack versions live in two places:

      1. `MINI_SWE_AGENT_VERSION` / `INSPECT_SWE_VERSION_PIN` in this module
         (used at the actual `mini_swe_agent(version=...)` call site).
      2. `mini_swe_agent_version` / `inspect_swe_version` on the pre-reg config
         (the contract recorded with the claim).

    If they diverge — e.g. someone bumps the constant without updating the
    locked claim — every rung's entry point should fail loudly rather than
    silently measuring a different stack than what was pre-registered.

    TODO(hardening): replace the constant-based check with
    `importlib.metadata.version("inspect-swe")` and the equivalent for
    `mini-swe-agent` once the metadata path is verified in CI. Package
    metadata reads are environment-dependent, so we keep the constant-based
    check for now to avoid spurious CI failures.
    """
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
    `HOME` to an empty tmp dir per Plan 38 §Risks #1 (re-opened 2026-05-14):
    `inspect_swe.claude_code()` writes `~/.claude/settings.json` via
    `_seed_claude_config()` AND inherits user skills / MCP servers / CLAUDE.md.

    Args:
        cwd: Optional sandbox-internal working directory string. Interpreted
            **inside the Docker container**, not on the host — pass a path
            that exists in the container image (or rely on the agent's
            default cwd by leaving this `None`). We do NOT `mkdir` on the
            host because the container filesystem is isolated.
        home_dir: REQUIRED. Path string used as the agent's `HOME` inside
            the sandbox. The caller MUST supply this (typically an empty
            tmp dir under `pytest`'s `tmp_path`, used purely as a string)
            to prevent ambient `~/.claude/` inheritance. `_seed_claude_config`
            runs `mkdir -p "$HOME/.claude"` inside the sandbox, so the path
            doesn't need to pre-exist in the container. Passing `None`
            raises `ValueError`.

    Sandbox: requires a Docker sandbox configured on the Inspect `Task`
    (e.g. `Task(..., sandbox="docker")`). `inspect_swe.claude_code` cannot
    run under `LocalSandboxEnvironment` — the bridged-tools plumbing needs
    sandbox isolation. We do NOT pass a `user=` override (conflicts with
    local sandboxes; not needed for Docker). The Inspect Task's default
    sandbox is picked up automatically by the agent; callers can route to a
    named sandbox via `**kwargs` if needed.
    """
    cfg = _validate_preregistration(preregistration)
    if home_dir is None:
        raise ValueError(
            "rung2_bare_cc requires home_dir to prevent ambient "
            "~/.claude inheritance — pass an empty tmp dir per plan §Risks #1"
        )

    # HOME redirect — see Plan 38 §Risks #1 (re-opened 2026-05-14). The
    # `env=` dict is layered into the sandbox process env by `claude_code`.
    # `_seed_claude_config()` runs `mkdir -p "$HOME/.claude"` inside the
    # sandbox, so this path is created on demand in the container.
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


def rung3_bonsai(
    *,
    bonsai_config: Path,
    preregistration: PreregistrationConfig | None = None,
    bonsai_binary: str = "bonsai",
    **kwargs: Any,
) -> Solver:
    """Rung 3 — bare CC plus a Bonsai-materialized `station/` workspace.

    Runs `bonsai init` + `bonsai add` against `bonsai_config` (a fixture path
    pointing at a `.bonsai.yaml`) inside a fresh temp dir, then invokes
    `inspect_swe.claude_code` with that dir as `cwd`. This is the only solver
    we own end-to-end.

    `bonsai_binary` is overrideable for tests / non-default install paths.
    """
    cfg = _validate_preregistration(preregistration)

    if not bonsai_config.exists():
        raise FileNotFoundError(f"bonsai_config not found: {bonsai_config}")
    if shutil.which(bonsai_binary) is None and not Path(bonsai_binary).exists():
        raise FileNotFoundError(
            f"bonsai binary not found: {bonsai_binary} "
            "(install Bonsai first: `go install ./cmd/bonsai` from the Bonsai repo)"
        )

    workspace = Path(tempfile.gettempdir()) / f"bonsai-eval-rung3-{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, exist_ok=True)

    # Stage the .bonsai.yaml fixture into the workspace, then materialize.
    shutil.copy(bonsai_config, workspace / ".bonsai.yaml")
    # Note: `bonsai init` is interactive in normal use; in P2 we'll either
    # author non-interactive flags or feed a scripted answer file. For the
    # bootstrap we record the contract; smoke testing happens in P0.2 (key-gated).
    subprocess.run(
        [bonsai_binary, "init", "--non-interactive"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [bonsai_binary, "add", "--from-config", ".bonsai.yaml"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )

    agent = claude_code(
        model=cfg.model,
        cwd=str(workspace),
        **kwargs,
    )
    return as_solver(agent)
