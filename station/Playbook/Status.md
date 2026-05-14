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
| **Plan 38 P2 build (P2.1–P2.4)** — scenario YAML schema, 12 scenarios across 5 categories, scorers (deterministic + Haiku judge), Inspect task wiring. [plan](Plans/Active/38-bonsai-eval-bootstrap.md) §P2.1–P2.4 | 38 | tl | Substrate verified via P0.2 smoke (PR #2 merged `92239a3`). Next: dispatch P2.1+P2.2 build. P2.5 (108 runs) gates on build review. |

## Pending

| Task | Plan | Agent | Blocked By |
|------|------|-------|------------|
| Plan 38 P2.5 — 108-run validation (12 × 3 × 3) on Haiku, budget $20 | 38 | tl | P2.1–P2.4 build review |
| Plan 38 P3 — pre-registration + paid run + public artifact | 38 | tl | P2.5 results |

## Recently Done

| Task | Plan | Agent | Date |
|------|------|-------|------|
| **Plan 38 P0.2 key-gated verification** — wired 3 smoke tests (A/B/C all green on Haiku, $0.017), fixed rung-1 version pin (`MINI_SWE_AGENT_VERSION="2.2.3"`), rung-2 HOME redirect per §Risks #1 (re-opened), pre-reg version-field machine-enforcement. Squash `92239a3`. | 38 | tl + gp | 2026-05-14 |
| **Bonsai workspace bootstrap** — `bonsai init --non-interactive --from-config .bonsai-init.yaml` against Bonsai v0.4.2. First dogfood of the non-interactive flag pair. 38 files materialised, `bonsai validate` clean. | — | tl | 2026-05-13 |
| **Plan 38 P0+P1 shipped** — key-independent harness, judge stubs, telemetry pipeline. Commit `08fca07`. | 38 | tl + gp | 2026-05-07 |
