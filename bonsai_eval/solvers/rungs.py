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
    assert_preregistration,
)

# `inspect-swe` version pin — Plan 38 §Risks #8. This must equal the version
# pinned in pyproject.toml; mismatch indicates a botched dependency upgrade.
INSPECT_SWE_VERSION_PIN = "0.2.51"

# Rung-1 system prompt floor — pinned text. This is the field's accepted
# "minimal harness" framing for mini-swe-agent (per Plan 38 §Risks #5).
RUNG1_SYSTEM_PROMPT = (
    "You are an autonomous software engineer. You have access to a single "
    "tool: bash. Use it to read, write, and run code as needed to complete "
    "the user's task. When done, stop."
)


def _validate_preregistration(cfg: PreregistrationConfig | None) -> PreregistrationConfig:
    """Resolve to ACTIVE_PREREGISTRATION, then assert match. Returns the validated cfg."""
    effective = cfg if cfg is not None else ACTIVE_PREREGISTRATION
    assert_preregistration(effective, ACTIVE_PREREGISTRATION)
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
        version=INSPECT_SWE_VERSION_PIN,
        **kwargs,
    )
    return as_solver(agent)


def rung2_bare_cc(
    *,
    preregistration: PreregistrationConfig | None = None,
    cwd: str | Path | None = None,
    **kwargs: Any,
) -> Solver:
    """Rung 2 — `inspect_swe.claude_code` drop-in (bare Claude Code).

    Runs from a fresh temp dir by default — no `.claude/`, no `CLAUDE.md`,
    no `station/` materialization. Workspace-file inheritance is suppressed
    here; the P0.2 Case C smoke test verifies absence of ambient state in
    the live process. Caller may override `cwd` to a pre-prepared empty dir.
    """
    cfg = _validate_preregistration(preregistration)
    target_cwd = (
        str(cwd)
        if cwd is not None
        else str(Path(tempfile.gettempdir()) / f"bonsai-eval-rung2-{uuid.uuid4().hex}")
    )
    Path(target_cwd).mkdir(parents=True, exist_ok=True)
    agent = claude_code(
        model=cfg.model,
        cwd=target_cwd,
        **kwargs,
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
