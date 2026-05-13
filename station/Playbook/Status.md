---
tags: [playbook, status]
description: Live task tracker. Update this file at the start and end of every working session.
---

# Bonsai-Eval — Status

> [!note]
> Move items between tables as work progresses. Link to the relevant plan in [Plans/Active/](Plans/Active/) or [Plans/Archive/](Plans/Archive/).
>
> **Brevity rule:** every row follows [Standards/NoteStandards.md](Standards/NoteStandards.md) — 3 lines max, link out for detail. Phase walkthroughs go in the plan; commit walkthroughs go in the PR; process narrative goes in `Logs/`.

---

## In Progress

| Task | Plan | Agent | Notes |
|------|------|-------|-------|
| **Plan 38 P2 — 12 scenarios × 3 rungs validation run** — rung-3 solver invokes Bonsai v0.4.2 `bonsai init --non-interactive` per scenario; rungs 1+2 via `inspect_swe==0.2.51` drop-in. Telemetry + judge harness from P1. [plan](Plans/Active/38-bonsai-eval-bootstrap.md) | 38 | tl | Manual prep: set `$ANTHROPIC_API_KEY`. Then `uv sync && uv run pytest -q` to verify env, then dispatch P2 work. |

## Pending

| Task | Plan | Agent | Blocked By |
|------|------|-------|------------|
| Plan 38 P3 — pre-registration + paid run + public artifact | 38 | tl | P2 dry-run results |

## Recently Done

| Task | Plan | Agent | Date |
|------|------|-------|------|
| **Bonsai workspace bootstrap** — `bonsai init --non-interactive --from-config .bonsai-init.yaml` against Bonsai v0.4.2. First dogfood of the non-interactive flag pair. 38 files materialised, `bonsai validate` clean. | — | tl | 2026-05-13 |
| **Plan 38 P0+P1 shipped** — key-independent harness, judge stubs, telemetry pipeline. Commit `08fca07`. | 38 | tl + gp | 2026-05-07 |
