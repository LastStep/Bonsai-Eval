"""Telemetry pipeline — Plan 38 Phase P1.

Stages (run in order via `bonsai_eval.telemetry.run_all`):

1. `fetch_codeburn` — codeburn JSON export (placeholder when CLI absent)
2. `parse_transcripts` — `~/.claude/projects/*.jsonl` → `data/transcripts.parquet`
                        (drops `tool_input.content` + `tool_result.content` — privacy)
3. `collect_git`     — git log + gh PR/issue history → `data/git.parquet`, `data/pulls.parquet`
4. `join`            — three parquets → `data/joined.parquet`

P1.5 analysis notebook (`notebooks/proof_of_work.ipynb`) consumes `joined.parquet`.
"""
