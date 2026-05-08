# `data/` Schemas

The `data/` directory is regenerate-only — `data/raw/` and `data/*.parquet`
are gitignored. Scripts under `bonsai_eval/telemetry/` are the artifact;
the parquets here are reproducible from a fresh clone via `make telemetry`.

## `data/transcripts.parquet`

Source: `~/.claude/projects/*.jsonl` (configurable via `CLAUDE_PROJECTS_ROOT`).
Producer: `bonsai_eval.telemetry.parse_transcripts`.

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | str | Claude Code session UUID |
| `project_slug` | str | leaf-dir name under `~/.claude/projects/` |
| `timestamp` | str (ISO 8601) | event timestamp |
| `event_type` | str | `user`, `assistant`, `tool_use`, ... |
| `tool_name` | str \| null | `Read`, `Edit`, `Write`, `Bash`, ... |
| `tool_input_path` | str \| null | only the `path` field — never `content` |
| `hook_event_name` | str \| null | `PreToolUse`, `SessionStart`, ... |
| `subagent_type` | str \| null | dispatched-agent type, when applicable |
| `input_tokens` | int \| null | from `message.usage.input_tokens` |
| `output_tokens` | int \| null | from `message.usage.output_tokens` |
| `cache_read_tokens` | int \| null | C1 numerator |
| `cache_creation_tokens` | int \| null | |

**Privacy guarantee.** `tool_input.content` and `tool_result.content` are
explicitly dropped before parquet write — see
`bonsai_eval.telemetry.parse_transcripts.assert_no_content_columns` and
`tests/test_privacy.py`.

## `data/git.parquet`

Source: `git log` on the Bonsai repo (configurable via `BONSAI_REPO_PATH`).
Producer: `bonsai_eval.telemetry.collect_git`.

| Column | Type | Notes |
|--------|------|-------|
| `sha` | str | full commit SHA |
| `author` | str | |
| `email` | str | |
| `timestamp` | str (ISO 8601) | author date |
| `subject` | str | first line of commit message |
| `commit_type` | str \| null | `feat`, `fix`, `refactor`, ... |
| `scope` | str \| null | parsed from `feat(scope):` prefix |
| `breaking` | bool | `feat!:` or `feat(scope)!:` |
| `is_rework` | bool | `fix(scope)` within 24h of a prior `feat(scope)` |

## `data/pulls.parquet`

Source: `gh pr list --state merged`.
Producer: `bonsai_eval.telemetry.collect_git.collect_pulls`.

Columns: `number`, `title`, `author`, `createdAt`, `mergedAt`, `labels`.

## `data/joined.parquet`

Per-day, per-project join. Used by the analysis notebook.

| Column | Type | Notes |
|--------|------|-------|
| `date` | date | UTC day |
| `project_slug` | str | |
| `input_tokens` | int | |
| `output_tokens` | int | |
| `cache_read_tokens` | int | |
| `cache_creation_tokens` | int | |
| `tool_calls` | int | |
| `commits` | int | |
| `feat_commits` | int | |
| `fix_commits` | int | |
| `rework_commits` | int | |
| `prs_merged` | int | |
