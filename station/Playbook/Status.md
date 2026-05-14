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
| **Plan 38 P2.5 prep — fix sensor bugs blocking validation** | 38 | tl | P2.1–P2.4 build shipped (PRs #3, #4, #5 → squash `7328ecf`, `f7d0bb6`, `4219369`). 125 tests green. Blockers before P2.5 paid run: Backlog P1 F1 (`dispatch-guard` stderr→stdout) + F2 (`scope-guard-files` mis-scoped to `.env*` only). Then run 108-run validation. |

## Pending

| Task | Plan | Agent | Blocked By |
|------|------|-------|------------|
| Plan 38 P2.5 — 108-run validation (12 × 3 × 3) on Haiku, budget $20 | 38 | tl | P2.1–P2.4 build review |
| Plan 38 P3 — pre-registration + paid run + public artifact | 38 | tl | P2.5 results |

## Recently Done

| Task | Plan | Agent | Date |
|------|------|-------|------|
| **Plan 38 P2.3+P2.4** — scorers (deterministic + test_based + Haiku judge w/ position-swap, F5 dual-semantic for Read), 12 Inspect tasks (AST-discoverable, drift-guarded), judge prompt SHA-256 live in pre-reg, 61 new tests (53→125). Adversarial review surfaced F1+F2 station-sensor bugs → Backlog P1. Squash `4219369`. | 38 | tl + gp | 2026-05-14 |
| **dispatch-guard `workspaces={}` fix** — populated catalog 6 entries, 11 pytest cases. Squash `f7d0bb6`. | 38 (backlog) | tl + gp | 2026-05-14 |
| **Plan 38 P2.1+P2.2** — scenario YAML schema (`scenarios/SCHEMA.md`), 12 starter scenarios across 5 categories (role/plan-gating/scope/memory/workflow), validator (`scripts/check_scenarios.py`), 53 tests. Two review cycles (initial F1+F2+F3+F7+F9; adversarial F-adv-1/2/3/5/6). Squash `7328ecf`. | 38 | tl + gp | 2026-05-14 |
| **Plan 38 P0.2 key-gated verification** — wired 3 smoke tests (A/B/C all green on Haiku, $0.017), fixed rung-1 version pin (`MINI_SWE_AGENT_VERSION="2.2.3"`), rung-2 HOME redirect per §Risks #1 (re-opened), pre-reg version-field machine-enforcement. Squash `92239a3`. | 38 | tl + gp | 2026-05-14 |
| **Bonsai workspace bootstrap** — `bonsai init --non-interactive --from-config .bonsai-init.yaml` against Bonsai v0.4.2. First dogfood of the non-interactive flag pair. 38 files materialised, `bonsai validate` clean. | — | tl | 2026-05-13 |
| **Plan 38 P0+P1 shipped** — key-independent harness, judge stubs, telemetry pipeline. Commit `08fca07`. | 38 | tl + gp | 2026-05-07 |
