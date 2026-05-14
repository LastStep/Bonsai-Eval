"""Unit tests for `bonsai_eval.scorers.test_based` (Plan 38 §P2.3).

Covers both backends (sandbox mode + subprocess fallback). The sandbox
path is exercised with a mock `sandbox_factory` that mimics the Inspect
`SandboxEnvironment.exec` protocol — we do NOT instantiate Docker. The
subprocess fallback uses real `bash -lc` execution against tiny commands
(`true`, `false`, `exit 42`) anchored at `tmp_path`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bonsai_eval.scorers.test_based import evaluate_test_based

# --- Sandbox mocks ----------------------------------------------------------


@dataclass
class _MockExecResult:
    success: bool
    returncode: int
    stdout: str
    stderr: str


class _MockSandbox:
    """Minimal stand-in for `inspect_ai.util.SandboxEnvironment`."""

    def __init__(self, returncode: int, *, stdout: str = "", stderr: str = "") -> None:
        self._rc = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.calls: list[dict[str, Any]] = []

    async def exec(
        self,
        cmd: list[str],
        input: Any = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        user: str | None = None,
        timeout: int | None = None,
        timeout_retry: bool = True,
        concurrency: bool = True,
    ) -> _MockExecResult:
        self.calls.append({"cmd": cmd, "timeout": timeout})
        return _MockExecResult(
            success=self._rc == 0,
            returncode=self._rc,
            stdout=self._stdout,
            stderr=self._stderr,
        )


def _make_factory(sandbox: _MockSandbox) -> Any:
    def factory() -> _MockSandbox:
        return sandbox

    return factory


# --- Sandbox-mode tests -----------------------------------------------------


def test_sandbox_mode_passes_on_expected_exit_zero(tmp_path: Path) -> None:
    sb = _MockSandbox(returncode=0, stdout="ok\n")
    evaluator = {
        "type": "test_based",
        "command": "pytest -k smoke",
        "expected_exit_code": 0,
    }
    passed, detail = asyncio.run(
        evaluate_test_based(evaluator, workspace_root=tmp_path, sandbox_factory=_make_factory(sb))
    )
    assert passed, detail
    assert "[sandbox]" in detail
    assert sb.calls[0]["cmd"] == ["bash", "-lc", "pytest -k smoke"]
    assert sb.calls[0]["timeout"] == 30


def test_sandbox_mode_fails_on_unexpected_exit(tmp_path: Path) -> None:
    sb = _MockSandbox(returncode=1, stderr="exit code 1")
    evaluator = {
        "type": "test_based",
        "command": "make lint",
        "expected_exit_code": 0,
    }
    passed, detail = asyncio.run(
        evaluate_test_based(evaluator, workspace_root=tmp_path, sandbox_factory=_make_factory(sb))
    )
    assert not passed
    assert "actual_exit=1" in detail


def test_sandbox_mode_passes_when_expected_nonzero_matches(tmp_path: Path) -> None:
    """A scenario can assert "this MUST fail" via `expected_exit_code: 1`."""
    sb = _MockSandbox(returncode=1)
    evaluator = {
        "type": "test_based",
        "command": "false",
        "expected_exit_code": 1,
    }
    passed, _ = asyncio.run(
        evaluate_test_based(evaluator, workspace_root=tmp_path, sandbox_factory=_make_factory(sb))
    )
    assert passed


def test_sandbox_mode_handles_exec_exception(tmp_path: Path) -> None:
    """A sandbox that raises mid-exec must NOT bubble — scorer reports a failure."""

    class _ExplodingSandbox:
        async def exec(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("sandbox crashed")

    evaluator = {
        "type": "test_based",
        "command": "x",
        "expected_exit_code": 0,
    }
    passed, detail = asyncio.run(
        evaluate_test_based(
            evaluator,
            workspace_root=tmp_path,
            sandbox_factory=lambda: _ExplodingSandbox(),
        )
    )
    assert not passed
    assert "RuntimeError" in detail


# --- Subprocess fallback ---------------------------------------------------


def test_subprocess_fallback_passes_on_true(tmp_path: Path) -> None:
    """No sandbox available → host subprocess. `true` exits 0."""
    evaluator = {
        "type": "test_based",
        "command": "true",
        "expected_exit_code": 0,
    }

    def no_sandbox() -> None:
        raise RuntimeError("no sandbox in test env")

    passed, detail = asyncio.run(
        evaluate_test_based(evaluator, workspace_root=tmp_path, sandbox_factory=no_sandbox)
    )
    assert passed, detail
    assert "[subprocess]" in detail


def test_subprocess_fallback_fails_on_nonzero(tmp_path: Path) -> None:
    evaluator = {
        "type": "test_based",
        "command": "exit 42",
        "expected_exit_code": 0,
    }

    def no_sandbox() -> None:
        raise RuntimeError("no sandbox")

    passed, detail = asyncio.run(
        evaluate_test_based(evaluator, workspace_root=tmp_path, sandbox_factory=no_sandbox)
    )
    assert not passed
    assert "actual_exit=42" in detail


def test_subprocess_fallback_runs_in_workspace_root(tmp_path: Path) -> None:
    """`cwd=workspace_root` must be honoured."""
    (tmp_path / "marker.txt").write_text("found me")
    evaluator = {
        "type": "test_based",
        "command": "test -f marker.txt",
        "expected_exit_code": 0,
    }
    passed, _ = asyncio.run(
        evaluate_test_based(
            evaluator,
            workspace_root=tmp_path,
            sandbox_factory=lambda: (_ for _ in ()).throw(RuntimeError("no sandbox")),
        )
    )
    assert passed
