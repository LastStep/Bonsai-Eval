# Bonsai-Eval

Eval harness and telemetry pipeline for measuring [Bonsai](https://github.com/LastStep/Bonsai) effectiveness. Two tracks: an **Inspect-AI**-based harness that runs identical scenarios across three execution rungs (raw API minimal loop, bare Claude Code, Claude Code + Bonsai workspace) so the value contributed by each layer can be isolated, plus a **telemetry pipeline** that ingests codeburn JSON, Claude Code transcripts (`~/.claude/projects/*.jsonl`), and Bonsai's git/PR history into parquet for the three pre-registered claims (cache reuse, rework reduction, throughput) over the 2026-04-14 dogfood cut-over.

## First-sprint scope (Plan 38)

| Phase | Scope | Status |
|-------|-------|--------|
| **P0** | Repo bootstrap, Inspect AI substrate, 3 rung factories, pre-registration config | Bootstrapped (key-gated tests pending `ANTHROPIC_API_KEY`) |
| **P1** | Telemetry pipeline (codeburn + transcripts + git/gh joiner + analysis notebook) | Bootstrapped on placeholder fixtures |
| **P2** | Bonsai-behavioral scenarios (12 starter scenarios, 3 rungs, 3 seeds) | Out-of-scope this dispatch |

P3 (standard benchmarks: Terminal-Bench v2, LiveCodeBench-50), P4 (Bonsai-config A/B sweep), P5 (SWE-bench Pro) are deferred to follow-up plans pending budget approval.

## Setup

```bash
# Install dependencies (uv auto-fetches Python 3.12 if needed)
uv sync

# Copy env template and fill in your key
cp .env.example .env
$EDITOR .env  # set ANTHROPIC_API_KEY

# Run non-API tests
make test

# Run lint + type-check
make lint

# Run telemetry pipeline against placeholder fixtures
make telemetry
```

## Make targets

| Target | What it does |
|--------|--------------|
| `make install` | `uv sync` — install/refresh deps from `uv.lock` |
| `make test` | non-API pytest (skips `requires_api` marker) |
| `make test-api` | API pytest — requires `ANTHROPIC_API_KEY`, will fail without it |
| `make lint` | `ruff check` + `mypy bonsai_eval` |
| `make format` | `ruff format .` |
| `make eval` | placeholder — `inspect eval bonsai_eval/tasks/ --model anthropic/claude-haiku-4-5` (needs key) |
| `make telemetry` | run all telemetry stages end-to-end on local data / placeholder fixtures |

## Repo layout

```
bonsai_eval/
  preregistration.py     # frozen pre-reg config + assertion
  solvers/
    rungs.py             # 3 rung factories (rung1_raw_api, rung2_bare_cc, rung3_bonsai)
  telemetry/
    fetch_codeburn.py    # P1.1
    parse_transcripts.py # P1.2 (drops tool_input.content + tool_result.content)
    collect_git.py       # P1.3
    join.py              # P1.4
    run_all.py           # `make telemetry` entrypoint
notebooks/
  proof_of_work.ipynb    # P1.5 — runs on placeholder fixtures only (Risk #7)
tests/
  fixtures/              # synthetic JSONL / git fixtures for P1.x
PROOF-OF-WORK.md         # P1.6 skeleton, formulas locked
```

## Privacy / data policy

`~/.claude/projects/*.jsonl` may contain user prompts and tool I/O (paths, secrets, URLs). The transcript parser drops `tool_input.content` and `tool_result.content` before writing parquet — enforced by an explicit assertion + unit test. Raw JSONL and derived parquet outputs are gitignored; scripts are the artifact.

## License

MIT — see [LICENSE](LICENSE).
