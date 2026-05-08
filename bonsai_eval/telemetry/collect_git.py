"""Git/GitHub collector — Plan 38 §P1.3.

Reads commits + merged PRs + issues from a target git repo (default: sibling
`../Bonsai`) and writes to `data/git.parquet` and `data/pulls.parquet`.

Detects rework: a `fix(scope)` commit within 24h of a `feat(scope)` commit
on the same scope contributes to C3 in the proof-of-work analysis.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|refactor|docs|test|chore|build|ci|perf|style|revert)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<bang>!)?:\s*"
    r"(?P<subject>.+)$"
)


def default_bonsai_repo() -> Path:
    """Resolve the Bonsai repo path — env override, else sibling `../Bonsai`."""
    override = os.environ.get("BONSAI_REPO_PATH")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "Bonsai"


def _git_log(repo: Path) -> list[dict[str, str]]:
    """Run `git log` with a JSON-friendly format, return one dict per commit."""
    if not (repo / ".git").exists():
        return []
    sep = "\x1e"  # record separator
    field = "\x1f"  # unit separator
    fmt = field.join(["%H", "%an", "%ae", "%aI", "%s"]) + sep
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", f"--format={fmt}"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[dict[str, str]] = []
    for record in proc.stdout.split(sep):
        record = record.strip()
        if not record:
            continue
        parts = record.split(field)
        if len(parts) < 5:
            continue
        sha, author, email, iso, subject = parts[:5]
        rows.append(
            {
                "sha": sha,
                "author": author,
                "email": email,
                "timestamp": iso,
                "subject": subject,
            }
        )
    return rows


def parse_subject(subject: str) -> tuple[str | None, str | None, bool]:
    """Return (commit_type, scope, breaking_flag) from a conventional-commit subject."""
    m = CONVENTIONAL_RE.match(subject)
    if not m:
        return None, None, False
    return m.group("type"), m.group("scope"), bool(m.group("bang"))


def annotate_rework(df: pd.DataFrame) -> pd.DataFrame:
    """Add `is_rework` column — True if this `fix(scope)` follows a `feat(scope)` within 24h."""
    if df.empty:
        df = df.copy()
        df["is_rework"] = pd.Series([], dtype="bool")
        return df
    df = df.copy()
    df["timestamp_dt"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.sort_values("timestamp_dt").reset_index(drop=True)
    is_rework: list[bool] = [False] * len(df)
    last_feat_at: dict[str, datetime] = {}
    # `itertuples` gives a positional index `Index` we can use directly as a
    # list offset — avoids the `Hashable` typing hazard from `iterrows`.
    for i, row in enumerate(df.itertuples(index=False)):
        scope = getattr(row, "scope", None)
        ctype = getattr(row, "commit_type", None)
        ts = getattr(row, "timestamp_dt", None)
        if ts is None or pd.isna(ts) or scope is None or ctype is None:
            continue
        if ctype == "feat":
            last_feat_at[scope] = ts.to_pydatetime()
        elif ctype == "fix":
            prev = last_feat_at.get(scope)
            if prev is not None and (ts.to_pydatetime() - prev).total_seconds() <= 86400:
                is_rework[i] = True
    df["is_rework"] = is_rework
    return df.drop(columns=["timestamp_dt"])


def collect_commits(repo: Path) -> pd.DataFrame:
    """Build the per-commit DataFrame with conventional-commit parsing + rework flag."""
    rows = _git_log(repo)
    df = pd.DataFrame(rows, columns=["sha", "author", "email", "timestamp", "subject"])
    if df.empty:
        df["commit_type"] = pd.Series([], dtype="object")
        df["scope"] = pd.Series([], dtype="object")
        df["breaking"] = pd.Series([], dtype="bool")
        df["is_rework"] = pd.Series([], dtype="bool")
        return df
    parsed = df["subject"].apply(parse_subject)
    df["commit_type"] = [p[0] for p in parsed]
    df["scope"] = [p[1] for p in parsed]
    df["breaking"] = [p[2] for p in parsed]
    df = annotate_rework(df)
    return df


def collect_pulls(repo: Path) -> pd.DataFrame:
    """Run `gh pr list --state merged` against `repo`. Empty DataFrame if `gh` absent."""
    if shutil.which("gh") is None or not (repo / ".git").exists():
        return pd.DataFrame(
            columns=["number", "title", "author", "createdAt", "mergedAt", "labels"]
        )
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state=merged",
                "--limit=500",
                "--json=number,title,author,createdAt,mergedAt,labels",
            ],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return pd.DataFrame(
            columns=["number", "title", "author", "createdAt", "mergedAt", "labels"]
        )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else []
    return pd.DataFrame(payload)


def write_parquets(
    *,
    repo: Path | None = None,
    output_dir: Path,
) -> tuple[int, int]:
    """Write `git.parquet` + `pulls.parquet`. Returns (commit_count, pr_count)."""
    repo = repo or default_bonsai_repo()
    output_dir.mkdir(parents=True, exist_ok=True)
    commits = collect_commits(repo)
    pulls = collect_pulls(repo)
    commits.to_parquet(output_dir / "git.parquet", index=False)
    pulls.to_parquet(output_dir / "pulls.parquet", index=False)
    return len(commits), len(pulls)
