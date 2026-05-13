---
tags: [playbook, backlog]
description: Prioritized backlog — bugs, features, debt, research, and improvement ideas. Self-maintained by agents via the backlog-hygiene routine.
---

# Bonsai-Eval — Backlog

> [!note]
> This is the intake queue for all work not yet in [Status.md](Status.md). Items flow from here into active work.
> For current active work, see [Status.md](Status.md). For long-term direction, see [Roadmap.md](Roadmap.md).

---

## How This Works

**Capture:** When you discover a bug, improvement opportunity, tech debt, or idea during a session that is outside your current task scope — add it here instead of fixing it inline. Use the item format below.

**Promote:** When capacity opens, move P0/P1 items into `Playbook/Status.md` as Pending or In Progress. Remove the item from this file when it appears in Status.

**Resolve:** Items completed via Status.md are cleaned up by the backlog-hygiene routine. Items abandoned or made irrelevant should be removed with a note in `Logs/RoutineLog.md`.

**Review:** The backlog-hygiene routine runs periodically to flag stale items, escalate misplaced P0s, remove duplicates, and cross-reference with Status.md and Roadmap.md.

### Item Format

```
- **[category] Short description** — Context or rationale. *(added YYYY-MM-DD, source: routine|session|user)*
```

**Categories:** `bug`, `feature`, `debt`, `security`, `research`, `improvement`

> **Brevity rule:** every entry follows [Standards/NoteStandards.md](Standards/NoteStandards.md) — 3 lines max, link out for detail. When closed, replace with a single HTML comment: `<!-- [tag] resolved YYYY-MM-DD via Plan NN / PR #N -->`.

### Priority Guide

| Priority | Meaning | Action |
|----------|---------|--------|
| **P0** | Blocking current work or broken functionality | Must be in Status.md. If a P0 is here, escalate it immediately |
| **P1** | Next up when current work completes | Promote to Status.md when capacity opens |
| **P2** | Planned but not urgent | Review at phase boundaries |
| **P3** | Ideas, nice-to-haves, research topics | Review during roadmap updates |

---

## P0 — Critical

<!-- Items here are blocking or broken. If a P0 exists but isn't in Status.md, escalate immediately. -->

## P1 — High

<!-- Next batch of work. Promote to Status.md when capacity opens. -->

## P2 — Medium

<!-- Planned but not scheduled. Review at phase boundaries. -->

## P3 — Ideas & Research

<!-- Nice-to-haves, research topics, improvement ideas. Low urgency, high optionality. -->
