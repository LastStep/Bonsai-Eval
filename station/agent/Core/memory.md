---
tags: [core, memory]
description: Tech Lead Agent working memory — flags, work state, notes.
---

# Working Memory

## Flags

<!-- Active flags go here. Format: - [FLAG] description -->

(none)

## Work State

**Current task:** **Plan 38 P2 — 12 scenarios × 3 rungs validation run.** P0+P1 shipped 2026-05-07 (commit `08fca07`, key-independent harness, judge stubs, telemetry). P2 unblocked 2026-05-13 by Bonsai v0.4.2's `bonsai init/add --non-interactive --from-config` (Plan 39, sibling repo). Rung-3 solver at `bonsai_eval/solvers/rungs.py` can now materialise stations from fixture YAML. [plan](../../Playbook/Plans/Active/38-bonsai-eval-bootstrap.md).

**Outstanding manual prep:** `$ANTHROPIC_API_KEY` not in shell env (Max-plan OAuth doesn't cover SDK-direct calls; personal billing per Plan 38 Locked Decisions).

**Brevity rule:** this section follows the same NoteStandards as the Bonsai station — link out, don't re-state. Substantive context lives in [the plan](../../Playbook/Plans/Active/38-bonsai-eval-bootstrap.md).

## Notes

<!-- Session-to-session durable gotchas inherited from the Bonsai station handoff. Trim as eval-specific learnings accumulate. -->

- **`inspect_swe` is trusted-conditionally for rungs 1+2.** Org = 501(c)(3) JJ Allaire (Inspect AI lead) with UK AISI + Apollo Research contributors. Pre-1.0 (`0.2.51`), bus factor 82% jjallaire. *How to apply:* always exact-pin `inspect-swe==0.2.51`, commit `uv.lock`, fork mirrored at `LastStep/inspect_swe-frozen` as safety net. No upgrades during measurement windows. Re-evaluate if Meridian goes silent for 3+ months or if a v1.0 ships with breaking changes.
- **Public leaderboard numbers ≠ rung-1/rung-2 substitute.** Terminal-Bench / LiveCodeBench leaderboards omit temp / max_tokens / tool list / cost per entry. Always run own rung-1/2 under pre-registration to defend "apples-to-apples" claim.
- **Max-plan OAuth doesn't cover SDK-direct calls.** `claude` CLI uses Max OAuth; `anthropic` Python SDK + Inspect AI's `--model anthropic/...` substrate calls + judge models all require `ANTHROPIC_API_KEY`. Personal billing per Plan 38 Locked Decisions.
- **System Python is 3.10; harness needs 3.11+.** `uv` (already installed at `/home/rohan/.local/bin/uv`) bootstraps the right interpreter via `pyproject.toml`. Use `uv run` / `uv sync` for every Python invocation. Never `pip install` into the system interpreter.
- **`bonsai init/add --non-interactive --from-config <path>` is the rung-3 interface.** Ships in Bonsai v0.4.2. Exit codes: `0` success · `2` invalid input · `3` runtime · `4` config-conflict (already exists for init / missing for add). JSONL stdout, plain-stderr diagnostics, conflict-skipped semantics. Pin Bonsai version in `pyproject.toml` test deps when the rung-3 solver actually invokes the binary.

## Feedback

<!-- User corrections + confirmed approaches inherited from Bonsai station; trim/extend as eval-specific patterns emerge. -->

- **Concise and direct wins.** User makes fast decisions with minimal elaboration. Mirror their energy — two sentences in, two sentences out.
- **Surface incidental findings proactively.** When hitting a workaround during setup/chores, flag it as a finding. Don't normalize broken behavior into your flow.
- **Brevity rule for trackers.** All writes into `Playbook/Status.md`, `Playbook/Backlog.md`, this memory's Work State, follow NoteStandards (when ported in) — 3 lines max per entry, link out for detail.
- **Worktrees inherit only committed HEAD.** Uncommitted plans/docs in main tree are invisible to dispatched agents. Commit station/ artifacts before dispatch. Agent worktrees base off `origin/main`, not local main — push local-only commits first.

## References

- **Sibling repo (Bonsai itself):** `/home/rohan/ZenGarden/Bonsai/` — the tool under evaluation. Sibling tech-lead memory at `Bonsai/station/agent/Core/memory.md` carries the full history of Plan 38 dispatch + Plan 39 (the `--non-interactive` flags that unblocked rung-3) + cross-cutting decisions.
- **Plan 38 — bootstrap:** [Plans/Active/38-bonsai-eval-bootstrap.md](../../Playbook/Plans/Active/38-bonsai-eval-bootstrap.md) — copied from Bonsai station 2026-05-13 on agent bootstrap. Active until P2+P3 ship.
- **`inspect_swe` safety-net fork:** https://github.com/LastStep/inspect_swe-frozen (pinned at `0.2.51`).
- **Bonsai v0.4.2 release:** https://github.com/LastStep/Bonsai/releases/tag/v0.4.2 — first version with non-interactive flags.
