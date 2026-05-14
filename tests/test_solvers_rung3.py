"""Unit tests for `bonsai_eval.solvers.rungs.rung3_bonsai` (Plan 38 §P2.5 readiness).

The real `bonsai` CLI is mocked at the `_run_bonsai` seam — these tests cover
the rung-3 solver's orchestration (init / add staging, setup.files
materialization, baseline_hashes capture, path-traversal rejection) without
invoking the real Bonsai binary. Integration with a live `bonsai` install is
P2.5's job (key-gated, paid).
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bonsai_eval.solvers import rungs as rungs_module

REPO_ROOT = Path(__file__).resolve().parent.parent
MINIMAL_FIXTURE = REPO_ROOT / "fixtures" / "configs" / "minimal" / ".bonsai.yaml"
BACKEND_FIXTURE = REPO_ROOT / "fixtures" / "configs" / "backend" / ".bonsai.yaml"
SECURITY_FIXTURE = REPO_ROOT / "fixtures" / "configs" / "security" / ".bonsai.yaml"
TECH_LEAD_FIXTURE = REPO_ROOT / "fixtures" / "configs" / "tech-lead" / ".bonsai.yaml"


# --- helpers ---------------------------------------------------------------


def _success() -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=["bonsai"], returncode=0, stdout=b"", stderr=b"")


def _failure(code: int, stderr: str = "boom") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=["bonsai"], returncode=code, stdout=b"", stderr=stderr.encode("utf-8")
    )


class _FakeState:
    """Minimal stand-in for inspect-ai's TaskState — only attrs the solver touches."""

    def __init__(self) -> None:
        self.metadata: dict[str, Any] = {}


# --- fixtures sanity -------------------------------------------------------


def test_fixture_configs_exist_for_every_workspace_template() -> None:
    """Every workspace_template used in scenarios must have a matching fixture config."""
    assert MINIMAL_FIXTURE.exists(), MINIMAL_FIXTURE
    assert BACKEND_FIXTURE.exists(), BACKEND_FIXTURE
    assert SECURITY_FIXTURE.exists(), SECURITY_FIXTURE
    assert TECH_LEAD_FIXTURE.exists(), TECH_LEAD_FIXTURE


def test_minimal_fixture_is_tech_lead_only() -> None:
    assert rungs_module._is_tech_lead_only_config(MINIMAL_FIXTURE)


def test_tech_lead_fixture_is_tech_lead_only() -> None:
    assert rungs_module._is_tech_lead_only_config(TECH_LEAD_FIXTURE)


def test_backend_fixture_is_not_tech_lead_only() -> None:
    assert not rungs_module._is_tech_lead_only_config(BACKEND_FIXTURE)


def test_security_fixture_is_not_tech_lead_only() -> None:
    assert not rungs_module._is_tech_lead_only_config(SECURITY_FIXTURE)


# --- _materialize_bonsai_workspace -----------------------------------------


def test_init_only_for_tech_lead_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """tech-lead fixture → exactly one CLI call (init, no add)."""
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        return _success()

    monkeypatch.setattr(rungs_module, "_run_bonsai", fake_run)
    rungs_module._materialize_bonsai_workspace(MINIMAL_FIXTURE, tmp_path, "bonsai")
    assert len(calls) == 1, calls
    assert calls[0][:2] == ["bonsai", "init"]
    assert "--non-interactive" in calls[0]
    assert "--from-config" in calls[0]
    assert str(MINIMAL_FIXTURE) in calls[0]


def test_init_then_add_for_non_tech_lead_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """backend overlay → init bootstrap (minimal) + add (backend overlay)."""
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        return _success()

    monkeypatch.setattr(rungs_module, "_run_bonsai", fake_run)
    rungs_module._materialize_bonsai_workspace(BACKEND_FIXTURE, tmp_path, "bonsai")
    assert len(calls) == 2, calls
    # init with the bootstrap minimal config
    assert calls[0][:2] == ["bonsai", "init"]
    assert str(MINIMAL_FIXTURE) in calls[0]
    # add with the backend overlay fixture
    assert calls[1][:2] == ["bonsai", "add"]
    assert str(BACKEND_FIXTURE) in calls[1]


def test_init_invalid_config_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rungs_module,
        "_run_bonsai",
        lambda args, cwd: _failure(rungs_module.BONSAI_EXIT_INVALID_CONFIG, "shape rejected"),
    )
    with pytest.raises(ValueError, match="shape rejected"):
        rungs_module._materialize_bonsai_workspace(MINIMAL_FIXTURE, tmp_path, "bonsai")


def test_init_runtime_failure_raises_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rungs_module,
        "_run_bonsai",
        lambda args, cwd: _failure(rungs_module.BONSAI_EXIT_RUNTIME, "generator borked"),
    )
    with pytest.raises(RuntimeError, match="generator borked"):
        rungs_module._materialize_bonsai_workspace(MINIMAL_FIXTURE, tmp_path, "bonsai")


def test_init_wrong_cwd_raises_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rungs_module,
        "_run_bonsai",
        lambda args, cwd: _failure(rungs_module.BONSAI_EXIT_WRONG_CWD, "already initialised"),
    )
    with pytest.raises(RuntimeError, match="already initialised"):
        rungs_module._materialize_bonsai_workspace(MINIMAL_FIXTURE, tmp_path, "bonsai")


# --- setup.files materialization -------------------------------------------


def test_setup_files_writes_content(tmp_path: Path) -> None:
    files = [
        {"path": "station/Playbook/Plans/Active/51-test.md", "content": "# Plan 51\nhi\n"},
        {"path": "station/Reports/Pending/r1.md", "content": "report body"},
    ]
    rungs_module._materialize_setup_files(tmp_path, files)
    p1 = tmp_path / "station/Playbook/Plans/Active/51-test.md"
    p2 = tmp_path / "station/Reports/Pending/r1.md"
    assert p1.read_text() == "# Plan 51\nhi\n"
    assert p2.read_text() == "report body"


def test_setup_files_rejects_absolute_path_at_runtime(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        rungs_module._materialize_setup_files(
            tmp_path, [{"path": "/etc/passwd", "content": "oops"}]
        )


def test_setup_files_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        rungs_module._materialize_setup_files(
            tmp_path, [{"path": "../escape.txt", "content": "oops"}]
        )


def test_setup_files_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing or empty path"):
        rungs_module._materialize_setup_files(tmp_path, [{"content": "x"}])


# --- baseline_hashes -------------------------------------------------------


def test_baseline_hashes_captures_file_unchanged_targets(tmp_path: Path) -> None:
    target = tmp_path / "sentinel.txt"
    target.write_text("alpha")
    expected = hashlib.sha256(b"alpha").hexdigest()
    evaluators = [
        {"type": "deterministic", "check": "file_unchanged", "path": "sentinel.txt"},
        # not file_unchanged → ignored
        {"type": "deterministic", "check": "file_exists", "path": "sentinel.txt"},
        # llm_judge → ignored
        {"type": "llm_judge", "model": "haiku", "rubric": "..."},
    ]
    baseline = rungs_module._capture_baseline_hashes(tmp_path, evaluators)
    assert baseline == {"sentinel.txt": expected}


def test_baseline_hashes_skips_missing_file(tmp_path: Path) -> None:
    evaluators = [
        {"type": "deterministic", "check": "file_unchanged", "path": "ghost.txt"},
    ]
    baseline = rungs_module._capture_baseline_hashes(tmp_path, evaluators)
    assert baseline == {}


def test_baseline_hashes_absolute_path(tmp_path: Path) -> None:
    # Absolute paths (e.g. /etc/passwd in edit-outside-workspace-blocked.yaml)
    # are hashed in place — not joined under the workspace.
    target = tmp_path / "abs.txt"
    target.write_text("beta")
    evaluators = [
        {"type": "deterministic", "check": "file_unchanged", "path": str(target)},
    ]
    baseline = rungs_module._capture_baseline_hashes(tmp_path, evaluators)
    assert baseline == {str(target): hashlib.sha256(b"beta").hexdigest()}


# --- rung3_setup_solver end-to-end (still mocked) -------------------------


def test_setup_solver_stashes_workspace_and_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: setup solver materializes, writes setup.files, captures hashes."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # bonsai is mocked; we still need to write a sentinel post-init so the
    # file_unchanged baseline can be captured.
    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        return _success()

    monkeypatch.setattr(rungs_module, "_run_bonsai", fake_run)

    scenario = {
        "id": "test-scn",
        "setup": {
            "files": [
                {"path": "station/Notes/sentinel.md", "content": "watch me"},
            ],
        },
        "evaluators": [
            {
                "type": "deterministic",
                "check": "file_unchanged",
                "path": "station/Notes/sentinel.md",
            },
        ],
    }
    setup = rungs_module.rung3_setup_solver(
        bonsai_config=MINIMAL_FIXTURE,
        scenario=scenario,
        workspace=workspace,
        bonsai_binary="bonsai",
    )
    state = _FakeState()
    asyncio.run(setup(state, MagicMock()))  # type: ignore[arg-type]

    assert state.metadata["workspace_root"] == str(workspace)
    sentinel = workspace / "station/Notes/sentinel.md"
    assert sentinel.read_text() == "watch me"
    expected = hashlib.sha256(b"watch me").hexdigest()
    assert state.metadata["baseline_hashes"] == {"station/Notes/sentinel.md": expected}


def test_setup_solver_propagates_invalid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rungs_module,
        "_run_bonsai",
        lambda args, cwd: _failure(rungs_module.BONSAI_EXIT_INVALID_CONFIG, "bad shape"),
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    setup = rungs_module.rung3_setup_solver(
        bonsai_config=MINIMAL_FIXTURE,
        scenario={"setup": {}, "evaluators": []},
        workspace=workspace,
        bonsai_binary="bonsai",
    )
    state = _FakeState()
    with pytest.raises(ValueError, match="bad shape"):
        asyncio.run(setup(state, MagicMock()))  # type: ignore[arg-type]


# --- subprocess timeout (L-3) ---------------------------------------------


def test_run_bonsai_wraps_timeout_as_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hung `bonsai` invocation must raise `RuntimeError`, not propagate
    `subprocess.TimeoutExpired` verbatim — that would leak a bare
    timeout traceback into the agent-facing solver error.
    """

    def fake_subprocess_run(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise subprocess.TimeoutExpired(cmd="bonsai", timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    with pytest.raises(RuntimeError, match="timed out"):
        rungs_module._run_bonsai(["bonsai", "init"], cwd=tmp_path)


def test_run_bonsai_passes_timeout_to_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_run_bonsai` must forward `timeout=_RUN_BONSAI_TIMEOUT_S` to
    `subprocess.run`. Without this, a hung bonsai blocks the sweep
    forever.
    """
    captured: dict[str, Any] = {}

    def fake_subprocess_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        captured.update(kwargs)
        captured["args"] = args
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    rungs_module._run_bonsai(["bonsai", "init"], cwd=tmp_path)
    assert captured.get("timeout") == rungs_module._RUN_BONSAI_TIMEOUT_S
