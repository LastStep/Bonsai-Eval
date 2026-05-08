"""Inspect AI substrate smoke tests — Plan 38 §P0.2.

All 3 cases require `ANTHROPIC_API_KEY` and incur paid API calls (target:
< $0.10 total). They are marked `@pytest.mark.requires_api` and SKIPPED in
default `make test` runs. Run via `make test-api` once a key is available.

This dispatch (key-independent slice) wrote the test file structure but does
NOT execute the cases. A later dispatch will run them and verify.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# All tests in this module hit the API.
pytestmark = pytest.mark.requires_api


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture(autouse=True)
def _skip_without_key() -> None:
    if not _has_api_key():
        pytest.skip("ANTHROPIC_API_KEY not set — skipping API-dependent test")


def test_case_a_bare_substrate(tmp_path: Path) -> None:
    """Case A — bare substrate: trivial Task, no-op Solver, deterministic Scorer.

    Plan 38 §P0.2 Case A: validates Inspect AI install with Haiku.
    Asserts score=1.0 on "write hello world in Python" with `print("hello world")` check.
    """
    pytest.skip("TODO: implement in key-gated dispatch — see Plan 38 §P0.2 Case A")


def test_case_b_mini_swe_agent_smoke(tmp_path: Path) -> None:
    """Case B — `inspect_swe.mini_swe_agent()` smoke (rung 1 drop-in).

    Plan 38 §P0.2 Case B: trivial task with `rung1_raw_api(model=haiku-4-5)`.
    Asserts score=1.0.
    """
    pytest.skip("TODO: implement in key-gated dispatch — see Plan 38 §P0.2 Case B")


def test_case_c_claude_code_workspace_suppression(tmp_path: Path) -> None:
    """Case C — `inspect_swe.claude_code()` smoke + workspace-suppression check.

    Plan 38 §P0.2 Case C: solver = `rung2_bare_cc` invoked from `tmp_path`.
    Asserts:
      (1) score=1.0
      (2) no `CLAUDE.md` / `.claude/` materialized in cwd
      (3) `claude` process inherits no `~/.claude/projects/-...-/CLAUDE.md`
          ambient state (probe via `inspect eval --log-format=json` + grep
          transcript for system-prompt content).

    If step (3) fails, document the gap and pivot to subprocess-driving
    `claude` with `--no-inherit-claude-md`-equivalent flag (escalate before P1).
    """
    # Even when this is implemented, we'll want to confirm the temp dir is
    # actually empty before the run.
    assert not any(tmp_path.iterdir()), "fixture sanity: tmp_path must start empty"
    # Defensive: confirm rung2 doesn't accidentally inherit ambient `~/.claude`.
    home_claude = Path.home() / ".claude"
    if home_claude.exists():
        # Just record presence — we don't manipulate the user's home dir.
        assert home_claude.is_dir()
    shutil.rmtree(tmp_path / "noop", ignore_errors=True)
    pytest.skip("TODO: implement in key-gated dispatch — see Plan 38 §P0.2 Case C")
