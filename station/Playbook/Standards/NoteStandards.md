---
tags: [standards, notes, brevity]
description: How to write into Status, Backlog, memory, and any project tracker. Brevity rule.
---

# Bonsai-Eval — Note Standards

> Single source of truth for how we write into project trackers. Applies to `Playbook/Status.md`, `Playbook/Backlog.md`, `Playbook/Roadmap.md`, `agent/Core/memory.md` Work State, and any other surface that gets re-read every session.

## The rule

**Three lines max per entry. Always link out.**

```
[1] One-liner: active verb, what shipped/changed/blocked.
[2] (optional) One sentence for non-obvious context — gotcha, decision, follow-up.
[3] Links: [plan](path) · [PR #N](url) · [CI](url, optional)
```

Hard cap: 3 lines as rendered. If it doesn't fit, the prose is wrong, not the cap.

## What goes where

| Detail | Lives in |
|--------|----------|
| Phase-by-phase breakdown | The plan file (`Plans/Archive/NN-slug.md`) |
| Commit-level walkthrough | The PR description |
| Process narrative (rate-limit recovery, rebase saga) | `Logs/YYYY-MM-DD-slug.md` |
| Code review nits, security findings | The PR comments + Backlog |
| Cross-cutting gotchas that bite again | `memory.md` Notes (one line each) |

The tracker is the **index**, not the artifact. The link is the artifact.

## Examples

**Good** (Status.md Recently Done row):
```
| Plan NN — feature shipped: short outcome. [plan](Plans/Archive/NN-slug.md) · [PR #N](https://github.com/owner/repo/pull/N) | NN | agent | YYYY-MM-DD |
```

**Bad** (anything > 3 lines, or any of):
- Embedding commit hashes for every phase
- Quoting code or error strings
- Re-stating what's in the linked plan
- Process meta-commentary

## Ban list

These phrases pad without adding signal — strip on sight:

- "Process:", "Net:", "Closes:", "Plan archived." — implied by being in Recently Done
- CI count green ("8/8 green") — green is the default; only mention failures
- Re-stating phase letters (A/B/C/D) — if the reader needs them, they click into the plan

## When to deviate

Never. If the task genuinely needs more context, the reader clicks the link. If the link is missing, that's the bug — fix the link, not the entry.

## Memory Work State

Same shape, prose form:

```
**Current task:** Idle. Last ship (YYYY-MM-DD): Plan NN — title. One-sentence outcome. [plan](path) · [PR #N](url).
```

That's it. No phase-by-phase. No process. The reader who needs more clicks through.

## Backlog entries

Same 3-line cap. Bullet form:

```
- **[Tag] Short title** — One-line description of the gap or risk. *(added YYYY-MM-DD, source: link)*
```

When closed: replace with single HTML comment `<!-- [Tag] resolved YYYY-MM-DD via Plan NN / PR #N -->`.
