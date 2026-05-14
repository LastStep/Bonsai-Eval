"""`type: test_based` evaluator — Plan 38 §P2.3 + SCHEMA.md §`test_based`.

Runs a shell command against the sandbox post-run; success = the command's
exit code equals `expected_exit_code`. Used for invariant tests (e.g.
`pytest -k smoke`, `make lint`, `node --check ...`).

Two execution backends, selected automatically:

  1. **Sandbox** — when an Inspect sandbox is available
     (`inspect_ai.util.sandbox()` returns a `SandboxEnvironment`), the
     command runs INSIDE the sandbox via `sandbox.exec(...)`. This is the
     rung-2 / rung-3 path: the agent's filesystem mutations live in the
     Docker sandbox; running the test command from outside would miss
     them. The exec is `await`ed inside the Inspect scorer coroutine.
  2. **Subprocess fallback** — when no sandbox is configured (rung-1 raw
     API, or local unit tests), the command runs as a host subprocess
     anchored at `workspace_root`. The dispatch brief only requires this
     when "post-run on the materialized workspace for rung-3", but having
     a fallback also keeps the helper unit-testable without spinning up
     Docker.

Both backends enforce a default 30-second timeout (overrideable via the
evaluator's optional `timeout` field, not currently in the schema — kept
as a function arg for future extension).
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from bonsai_eval.scorers.deterministic import CheckResult

_DEFAULT_TIMEOUT_S = 30


async def evaluate_test_based(
    evaluator: dict[str, Any],
    *,
    workspace_root: Path,
    sandbox_factory: Any = None,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> CheckResult:
    """Run `evaluator["command"]`; pass iff exit code == `expected_exit_code`.

    Args:
        evaluator: Evaluator dict from the scenario YAML, already structurally
            validated (`command`, `expected_exit_code` present).
        workspace_root: Where to anchor subprocess-mode `cwd`. Ignored in
            sandbox mode (the sandbox has its own filesystem).
        sandbox_factory: Optional async-callable returning a sandbox object
            with an `exec(...)` coroutine. Defaults to
            `inspect_ai.util.sandbox`. Override for unit tests.
        timeout_s: Hard kill timeout in seconds.

    Returns:
        `(passed, detail)`. `detail` includes the command, exit code, and
        truncated stdout/stderr to keep the per-evaluator message useful
        without flooding the Score's metadata.
    """
    command = evaluator["command"]
    expected_exit = int(evaluator.get("expected_exit_code", 0))

    if sandbox_factory is None:
        # Late import to avoid hard-coupling unit tests to inspect_ai.util.
        from inspect_ai.util import sandbox as _sandbox  # noqa: PLC0415

        sandbox_factory = _sandbox

    sb = None
    try:
        sb = sandbox_factory()
    except Exception:
        # No active sandbox — fall through to subprocess mode.
        sb = None

    if sb is not None and hasattr(sb, "exec"):
        try:
            result = await sb.exec(
                ["bash", "-lc", command],
                timeout=timeout_s,
            )
        except Exception as exc:
            return False, f"test_based: sandbox exec raised {type(exc).__name__}: {exc}"
        actual_exit = getattr(result, "returncode", None)
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        return _format_exit_result(
            command=command,
            expected=expected_exit,
            actual=actual_exit,
            stdout=stdout,
            stderr=stderr,
            mode="sandbox",
        )

    return await asyncio.to_thread(
        _run_subprocess,
        command=command,
        expected_exit=expected_exit,
        workspace_root=workspace_root,
        timeout_s=timeout_s,
    )


def _run_subprocess(
    *,
    command: str,
    expected_exit: int,
    workspace_root: Path,
    timeout_s: int,
) -> CheckResult:
    """Subprocess-mode execution. Synchronous; called via `asyncio.to_thread`."""
    try:
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"test_based: subprocess timed out after {timeout_s}s running {command!r}"
    except OSError as exc:
        return False, f"test_based: subprocess failed to start: {exc}"
    return _format_exit_result(
        command=command,
        expected=expected_exit,
        actual=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        mode="subprocess",
    )


def _format_exit_result(
    *,
    command: str,
    expected: int,
    actual: int | None,
    stdout: str,
    stderr: str,
    mode: str,
) -> CheckResult:
    """Pack the (passed, detail) tuple with truncated stdio for the explanation."""
    passed = actual == expected
    stdout_snip = _truncate(stdout, 400)
    stderr_snip = _truncate(stderr, 400)
    detail = (
        f"test_based[{mode}] cmd={command!r} "
        f"expected_exit={expected} actual_exit={actual} "
        f"stdout={stdout_snip!r} stderr={stderr_snip!r}"
    )
    return passed, detail


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


__all__ = ["evaluate_test_based"]
