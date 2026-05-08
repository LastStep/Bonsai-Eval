"""Joiner — Plan 38 §P1.4.

Loads `transcripts.parquet`, `git.parquet`, `pulls.parquet` and produces
`joined.parquet` keyed on (date, project_slug). Notebook-friendly shape.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _date_col(df: pd.DataFrame, src: str) -> pd.Series:
    return pd.to_datetime(df[src], utc=True, errors="coerce").dt.date


def join_all(
    *,
    transcripts_path: Path,
    git_path: Path,
    pulls_path: Path,
    output_path: Path,
) -> int:
    """Build the joined per-day DataFrame and write parquet. Returns row count."""
    transcripts = pd.read_parquet(transcripts_path) if transcripts_path.exists() else pd.DataFrame()
    git = pd.read_parquet(git_path) if git_path.exists() else pd.DataFrame()
    pulls = pd.read_parquet(pulls_path) if pulls_path.exists() else pd.DataFrame()

    # Per-day, per-project transcript aggregates — token totals + tool-call counts.
    if not transcripts.empty:
        transcripts = transcripts.copy()
        transcripts["date"] = _date_col(transcripts, "timestamp")
        agg = (
            transcripts.groupby(["date", "project_slug"], dropna=False)
            .agg(
                input_tokens=("input_tokens", "sum"),
                output_tokens=("output_tokens", "sum"),
                cache_read_tokens=("cache_read_tokens", "sum"),
                cache_creation_tokens=("cache_creation_tokens", "sum"),
                tool_calls=("tool_name", "count"),
            )
            .reset_index()
        )
    else:
        agg = pd.DataFrame(
            columns=[
                "date",
                "project_slug",
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
                "tool_calls",
            ]
        )

    # Per-day commit counts (project_slug = "bonsai" — single-repo collector for now).
    if not git.empty:
        git = git.copy()
        git["date"] = _date_col(git, "timestamp")
        commit_agg = (
            git.groupby("date")
            .agg(
                commits=("sha", "count"),
                feat_commits=("commit_type", lambda s: int((s == "feat").sum())),
                fix_commits=("commit_type", lambda s: int((s == "fix").sum())),
                rework_commits=("is_rework", lambda s: int(s.fillna(False).sum())),
            )
            .reset_index()
        )
        commit_agg["project_slug"] = "bonsai"
    else:
        commit_agg = pd.DataFrame(
            columns=[
                "date",
                "commits",
                "feat_commits",
                "fix_commits",
                "rework_commits",
                "project_slug",
            ]
        )

    if not pulls.empty:
        pulls = pulls.copy()
        pulls["date"] = _date_col(pulls, "mergedAt")
        pr_agg = (
            pulls.dropna(subset=["date"])
            .groupby("date")
            .agg(prs_merged=("number", "count"))
            .reset_index()
        )
        pr_agg["project_slug"] = "bonsai"
    else:
        pr_agg = pd.DataFrame(columns=["date", "prs_merged", "project_slug"])

    joined = agg.merge(commit_agg, on=["date", "project_slug"], how="outer")
    joined = joined.merge(pr_agg, on=["date", "project_slug"], how="outer")
    joined = joined.sort_values(["date", "project_slug"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(output_path, index=False)
    return len(joined)
