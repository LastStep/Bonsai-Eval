"""End-to-end telemetry-join test on synthetic fixtures — non-API.

Verifies that `bonsai_eval.telemetry.run_all` produces the expected outputs
when pointed at a synthetic transcripts root + git repo, without any network
or API calls.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from bonsai_eval.telemetry import collect_git, join, parse_transcripts


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_synthetic_repo(repo: Path) -> None:
    """Build a 3-commit synthetic repo with explicit author dates so rework
    detection (which needs a sub-second-resolved time delta) works reliably.
    """
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    def commit(msg: str, when: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", msg, f"--date={when}"],
            check=True,
            capture_output=True,
            env={
                "GIT_COMMITTER_DATE": when,
                "GIT_AUTHOR_DATE": when,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
                "PATH": "/usr/bin:/bin",
            },
        )

    (repo / "README.md").write_text("hi\n")
    _git(repo, "add", ".")
    commit("feat(core): initial scaffold", "2026-04-15T10:00:00 +0000")
    (repo / "README.md").write_text("hi v2\n")
    _git(repo, "add", ".")
    commit("fix(core): typo", "2026-04-15T11:00:00 +0000")  # 1h later → rework
    (repo / "extra.md").write_text("x\n")
    _git(repo, "add", ".")
    commit("docs(readme): expand", "2026-04-15T12:00:00 +0000")


def test_collect_git_picks_up_synthetic_commits(tmp_path: Path) -> None:
    repo = tmp_path / "synthetic-repo"
    _make_synthetic_repo(repo)
    df = collect_git.collect_commits(repo)
    assert len(df) == 3
    assert set(df["commit_type"]) == {"feat", "fix", "docs"}
    fix_row = df[df["commit_type"] == "fix"].iloc[0]
    assert fix_row["scope"] == "core"
    assert bool(fix_row["is_rework"]) is True


def test_join_handles_empty_inputs(tmp_path: Path) -> None:
    """Joiner must produce an empty-but-valid parquet when nothing exists."""
    out = tmp_path / "joined.parquet"
    n = join.join_all(
        transcripts_path=tmp_path / "missing-tx.parquet",
        git_path=tmp_path / "missing-git.parquet",
        pulls_path=tmp_path / "missing-pulls.parquet",
        output_path=out,
    )
    assert n == 0
    assert out.exists()


def test_run_all_with_synthetic_inputs(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Drive `run_all` end-to-end pointed at a synthetic transcripts root + repo."""
    # Synthetic Claude transcripts root.
    projects = tmp_path / "claude_projects" / "synthetic"
    projects.mkdir(parents=True)
    line = json.dumps(
        {
            "type": "tool_use",
            "sessionId": "synthetic-1",
            "timestamp": "2026-04-15T12:00:00Z",
            "message": {
                "tool_name": "Read",
                "tool_input": {"path": "CLAUDE.md", "content": "DROP ME"},
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 60,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 0,
                },
            },
        }
    )
    (projects / "session.jsonl").write_text(line + "\n")

    # Synthetic Bonsai-like git repo.
    repo = tmp_path / "Bonsai"
    _make_synthetic_repo(repo)

    monkeypatch.setenv("CLAUDE_PROJECTS_ROOT", str(tmp_path / "claude_projects"))
    monkeypatch.setenv("BONSAI_REPO_PATH", str(repo))
    monkeypatch.setenv("TRANSCRIPT_MAX_AGE_DAYS", str(365 * 10))

    # Run the parser + collector + joiner directly (run_all's stages).
    parse_transcripts.parse_to_parquet(
        root=tmp_path / "claude_projects",
        output_path=tmp_path / "transcripts.parquet",
    )
    collect_git.write_parquets(repo=repo, output_dir=tmp_path)
    n = join.join_all(
        transcripts_path=tmp_path / "transcripts.parquet",
        git_path=tmp_path / "git.parquet",
        pulls_path=tmp_path / "pulls.parquet",
        output_path=tmp_path / "joined.parquet",
    )
    assert n >= 1
    joined = pd.read_parquet(tmp_path / "joined.parquet")
    assert "rework_commits" in joined.columns
