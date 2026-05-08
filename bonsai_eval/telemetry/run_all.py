"""`make telemetry` entrypoint — runs all P1 stages in order.

This is the script that boots up the telemetry pipeline end-to-end on a
fresh clone. Designed to be safe even when:

- `codeburn` CLI is absent
- `~/.claude/projects/` doesn't exist
- `gh` CLI is absent
- the Bonsai repo isn't checked out at the default path

Each stage logs what it did + what it skipped. Exit code 0 unless a stage
that is supposed to run actually errored.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from bonsai_eval.telemetry import collect_git, fetch_codeburn, join, parse_transcripts


def repo_root() -> Path:
    """Bonsai-Eval repo root (assumes this file lives at bonsai_eval/telemetry/run_all.py)."""
    return Path(__file__).resolve().parents[2]


def main() -> int:
    root = repo_root()
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    data_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    transcripts_path = data_dir / "transcripts.parquet"
    git_path = data_dir / "git.parquet"
    pulls_path = data_dir / "pulls.parquet"
    joined_path = data_dir / "joined.parquet"

    # --- Stage 1: codeburn ---
    print("[1/4] codeburn fetch", flush=True)
    if fetch_codeburn.codeburn_available():
        codeburn_path = fetch_codeburn.fetch(output_dir=raw_dir)
        print(f"      -> {codeburn_path}", flush=True)
    else:
        print(
            "      codeburn CLI not on PATH; skipping (expected in CI / fresh clones)", flush=True
        )

    # --- Stage 2: transcripts ---
    print("[2/4] parse transcripts", flush=True)
    # If the user explicitly points us at an empty / synthetic root, honour it.
    # Otherwise the default ~/.claude/projects gets parsed.
    root_override = os.environ.get("CLAUDE_PROJECTS_ROOT")
    transcripts_root = (
        Path(root_override).expanduser()
        if root_override
        else parse_transcripts.default_projects_root()
    )
    if transcripts_root.exists():
        n = parse_transcripts.parse_to_parquet(root=transcripts_root, output_path=transcripts_path)
        print(f"      -> {transcripts_path} ({n} rows)", flush=True)
    else:
        # Write an empty parquet with the canonical schema so downstream
        # stages have something to load.
        empty = parse_transcripts.rows_to_dataframe([])
        parse_transcripts.write_parquet(empty, transcripts_path)
        print(
            f"      transcripts root {transcripts_root} not found; "
            f"wrote empty schema-stamped parquet -> {transcripts_path}",
            flush=True,
        )

    # --- Stage 3: git + gh ---
    print("[3/4] collect git + gh", flush=True)
    bonsai_repo = collect_git.default_bonsai_repo()
    n_commits, n_prs = collect_git.write_parquets(repo=bonsai_repo, output_dir=data_dir)
    print(
        f"      repo={bonsai_repo} commits={n_commits} prs={n_prs} -> {git_path}, {pulls_path}",
        flush=True,
    )

    # --- Stage 4: join ---
    print("[4/4] join", flush=True)
    n_joined = join.join_all(
        transcripts_path=transcripts_path,
        git_path=git_path,
        pulls_path=pulls_path,
        output_path=joined_path,
    )
    print(f"      -> {joined_path} ({n_joined} rows)", flush=True)

    print("done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
