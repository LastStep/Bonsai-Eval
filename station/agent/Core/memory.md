---
tags: [core, memory]
description: Tech Lead Agent working memory — flags, work state, notes.
---

# Working Memory

## Flags

<!-- Active flags go here. Format: - [FLAG] description -->

(none)

## Work State

**Current task:** **Plan 38 P2 build (P2.1–P2.4).** P0+P1 shipped 2026-05-07 (commit `08fca07`). P0.2 key-gated verification shipped 2026-05-14 (squash `92239a3`, PR #2): 3 smoke tests green on Haiku ($0.017 total), rung-1 version pin fixed, rung-2 HOME redirect per §Risks #1 (re-opened), pre-reg version-field machine-enforcement. Next: dispatch P2.1 (scenario YAML schema) + P2.2 (12 scenarios) build. [plan](../../Playbook/Plans/Active/38-bonsai-eval-bootstrap.md).

**Brevity rule:** this section follows the same NoteStandards as the Bonsai station — link out, don't re-state. Substantive context lives in [the plan](../../Playbook/Plans/Active/38-bonsai-eval-bootstrap.md).

## Notes

<!-- Session-to-session durable gotchas inherited from the Bonsai station handoff. Trim as eval-specific learnings accumulate. -->

- **`inspect_swe` is trusted-conditionally for rungs 1+2.** Org = 501(c)(3) JJ Allaire (Inspect AI lead) with UK AISI + Apollo Research contributors. Pre-1.0 (`0.2.51`), bus factor 82% jjallaire. *How to apply:* always exact-pin `inspect-swe==0.2.51`, commit `uv.lock`, fork mirrored at `LastStep/inspect_swe-frozen` as safety net. No upgrades during measurement windows. Re-evaluate if Meridian goes silent for 3+ months or if a v1.0 ships with breaking changes.
- **Public leaderboard numbers ≠ rung-1/rung-2 substitute.** Terminal-Bench / LiveCodeBench leaderboards omit temp / max_tokens / tool list / cost per entry. Always run own rung-1/2 under pre-registration to defend "apples-to-apples" claim.
- **Max-plan OAuth doesn't cover SDK-direct calls.** `claude` CLI uses Max OAuth; `anthropic` Python SDK + Inspect AI's `--model anthropic/...` substrate calls + judge models all require `ANTHROPIC_API_KEY`. Personal billing per Plan 38 Locked Decisions.
- **System Python is 3.10; harness needs 3.11+.** `uv` (already installed at `/home/rohan/.local/bin/uv`) bootstraps the right interpreter via `pyproject.toml`. Use `uv run` / `uv sync` for every Python invocation. Never `pip install` into the system interpreter.
- **`bonsai init/add --non-interactive --from-config <path>` is the rung-3 interface.** Ships in Bonsai v0.4.2. Exit codes: `0` success · `2` invalid input · `3` runtime · `4` config-conflict (already exists for init / missing for add). JSONL stdout, plain-stderr diagnostics, conflict-skipped semantics. Pin Bonsai version in `pyproject.toml` test deps when the rung-3 solver actually invokes the binary.
- **`inspect_swe.claude_code()` is NOT pristine "bare CC" out of the box.** Library actively writes `~/.claude/settings.json` (`_seed_claude_config()`, claude_code.py:364-387) and inherits all ambient `~/.claude/` state (skills, MCP servers, hooks, project CLAUDE.md). *How to apply:* rung-2 solver MUST redirect HOME via `claude_code(env={"HOME": tmp_path})` per test/run to keep the bare-CC isolation claim honest. Confirmed via inspect-swe v0.2.51 source read 2026-05-14. Plan §Risks #1 re-opened — prior "RESOLVED" was premature (smoke tests were stubs).
- **`inspect_swe.mini_swe_agent(version=...)` wants mini-swe-agent CLI semver, not inspect-swe pkg version.** Accepted: `"stable"` (→ 2.2.3), `"sandbox"`, `"latest"`, or exact like `"2.2.3"`. Validation at `_mini_swe_agent/setup.py:19-39`. Default `"stable"`. No commit-level pin — PyPI semver only. *How to apply:* pin `MINI_SWE_AGENT_VERSION = "2.2.3"` in solver, separate from `INSPECT_SWE_VERSION_PIN = "0.2.51"` (pyproject pin for inspect-swe pkg itself).
- **`inspect_swe.claude_code()` needs Docker.** Default `sandbox=None` resolves to Docker daemon via Inspect AI's `sandbox_env()`. No local-sandbox escape. *How to apply:* Docker daemon required for every rung-2 + rung-3 test run + every benchmark sweep. Confirmed available on dogfood machine 2026-05-14 (`docker ps` clean, v29.3.1). Was P3 assumption; pulled forward to P0.2. **First rung-2 invocation pulls `aisiuk/inspect-tool-support` (~4.33 GB)** — budget time on slow connections; subsequent runs are cached locally.
- **Inspect AI `ModelUsage` cache fields are DISJOINT from `input_tokens`, not a subset.** `input_tokens_cache_read` + `input_tokens_cache_write` are reported as separate buckets. Old cost formula `(input_tokens - cache_read) * rate` produces NEGATIVE costs on cache-heavy runs. *How to apply:* compute cost as `input_tokens * input_rate + cache_read * cache_read_rate + cache_write * cache_write_rate + output_tokens * output_rate`. Discovered 2026-05-14 while fixing P0.2 smoke-test cost fallback (Haiku 4.5 missing from inspect-ai's bundled pricing at v0.3.219).

## Feedback

<!-- User corrections + confirmed approaches inherited from Bonsai station; trim/extend as eval-specific patterns emerge. -->

- **Concise and direct wins.** User makes fast decisions with minimal elaboration. Mirror their energy — two sentences in, two sentences out.
- **Surface incidental findings proactively.** When hitting a workaround during setup/chores, flag it as a finding. Don't normalize broken behavior into your flow.
- **Brevity rule for trackers.** All writes into `Playbook/Status.md`, `Playbook/Backlog.md`, this memory's Work State, follow NoteStandards (when ported in) — 3 lines max per entry, link out for detail.
- **Worktrees inherit only committed HEAD.** Uncommitted plans/docs in main tree are invisible to dispatched agents. Commit station/ artifacts before dispatch. Agent worktrees base off `origin/main`, not local main — push local-only commits first.
- **Worktrees DON'T inherit gitignored `.env`.** Every key-gated dispatch needs to copy `.env` into the worktree before `make test-api`. Hit by 3 dispatches in a row 2026-05-14. *How to apply:* either dispatch prompt includes "copy `.env` from repo root into worktree first" step, or add a pre-test conftest hook that walks up the dir tree to find `.env` (currently only checks repo-root relative to conftest path). Lower-effort fix: document the copy step in dispatch.md.
- **`gh pr edit --body` broken for body updates 2026-05-14.** Wrapper prints GraphQL "Projects (classic) deprecated" error and silently no-ops. Workaround: `gh api -X PATCH /repos/<owner>/<repo>/pulls/<n> -f body='...'`. Verify via API response, not `gh pr view`.

## References

- **Sibling repo (Bonsai itself):** `/home/rohan/ZenGarden/Bonsai/` — the tool under evaluation. Sibling tech-lead memory at `Bonsai/station/agent/Core/memory.md` carries the full history of Plan 38 dispatch + Plan 39 (the `--non-interactive` flags that unblocked rung-3) + cross-cutting decisions.
- **Plan 38 — bootstrap:** [Plans/Active/38-bonsai-eval-bootstrap.md](../../Playbook/Plans/Active/38-bonsai-eval-bootstrap.md) — copied from Bonsai station 2026-05-13 on agent bootstrap. Active until P2+P3 ship.
- **`inspect_swe` safety-net fork:** https://github.com/LastStep/inspect_swe-frozen (pinned at `0.2.51`).
- **Bonsai v0.4.2 release:** https://github.com/LastStep/Bonsai/releases/tag/v0.4.2 — first version with non-interactive flags.
