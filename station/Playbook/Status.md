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
| **Plan 38 P2 build (P2.3–P2.4)** — scorers (deterministic + Haiku judge with position-swap) + Inspect task wiring across 12 scenarios × 3 solvers. [plan](Plans/Active/38-bonsai-eval-bootstrap.md) §P2.3–P2.4 | 38 | tl | P2.1+P2.2 shipped (PR #3 squash `7328ecf`). Carry-forward: F5 (session-start sensor injection vs Read tool) — P2.3 scorer must read transcript injection events, not only tool calls. F-adv-4 (dispatch-guard empty `workspaces={}`) → Backlog P1, fix before P2.5. |

## Pending

| Task | Plan | Agent | Blocked By |
|------|------|-------|------------|
| Plan 38 P2.5 — 108-run validation (12 × 3 × 3) on Haiku, budget $20 | 38 | tl | P2.1–P2.4 build review |
| Plan 38 P3 — pre-registration + paid run + public artifact | 38 | tl | P2.5 results |

## Recently Done

| Task | Plan | Agent | Date |
|------|------|-------|------|
| **Plan 38 P2.1+P2.2** — scenario YAML schema (`scenarios/SCHEMA.md`), 12 starter scenarios across 5 categories (role/plan-gating/scope/memory/workflow), validator (`scripts/check_scenarios.py`), 53 tests. Two review cycles (initial F1+F2+F3+F7+F9; adversarial F-adv-1/2/3/5/6). Squash `7328ecf`. | 38 | tl + gp | 2026-05-14 |
| **Plan 38 P0.2 key-gated verification** — wired 3 smoke tests (A/B/C all green on Haiku, $0.017), fixed rung-1 version pin (`MINI_SWE_AGENT_VERSION="2.2.3"`), rung-2 HOME redirect per §Risks #1 (re-opened), pre-reg version-field machine-enforcement. Squash `92239a3`. | 38 | tl + gp | 2026-05-14 |
| **Bonsai workspace bootstrap** — `bonsai init --non-interactive --from-config .bonsai-init.yaml` against Bonsai v0.4.2. First dogfood of the non-interactive flag pair. 38 files materialised, `bonsai validate` clean. | — | tl | 2026-05-13 |
| **Plan 38 P0+P1 shipped** — key-independent harness, judge stubs, telemetry pipeline. Commit `08fca07`. | 38 | tl + gp | 2026-05-07 |
