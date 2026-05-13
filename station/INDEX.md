---
tags: [meta, index]
description: Master lookup table — read this first every session.
---

# Bonsai-Eval — Project Index

## Project Snapshot

Empirical eval harness for Bonsai's scaffolding value-add — Plan 38 P0+P1+P2.

**Current phase:** See Playbook/Status.md

### Tech Stack

<!-- Update this table with your actual stack -->

| Layer | Technology |
|-------|-----------|
| Backend | (your backend stack) |
| Frontend | (your frontend stack) |
| Database | (your database) |

---

## Document Registry

| Path | What it contains | When to use it |
|------|-----------------|----------------|
| `INDEX.md` | This file — project snapshot and document map | Read first, every session |
| [CLAUDE.md](CLAUDE.md) | Navigation table — routes to agent instructions | First file loaded every session |
| [Playbook/Status.md](Playbook/Status.md) | Live task tracker (in-progress / pending / done) | Start of every session; after completing work |
| [Playbook/Roadmap.md](Playbook/Roadmap.md) | Phases and milestones | When planning next steps |
| [Playbook/Backlog.md](Playbook/Backlog.md) | Prioritized intake queue — bugs, features, debt, ideas | When discovering out-of-scope issues; before promoting to Status.md |
| [Playbook/Plans/Active/](Playbook/Plans/Active/) | Numbered implementation plans for agents | When handing off work to an agent |
| [Playbook/Standards/SecurityStandards.md](Playbook/Standards/SecurityStandards.md) | Hard security rules — all agents | Every session, every plan, every code review |
| [Logs/FieldNotes.md](Logs/FieldNotes.md) | User-maintained notes on work done outside sessions | Read every session |
| [Logs/KeyDecisionLog.md](Logs/KeyDecisionLog.md) | Settled architectural decisions | When planning or when a topic comes up |
| [Reports/Pending/](Reports/Pending/) | Unprocessed agent completion reports | Check every session start |
| [Reports/report-template.md](Reports/report-template.md) | Structured report format for agents | When submitting a completion report |

---

## Agent Handoff Notes

> [!note]
> Agent instructions use a 4-layer structure: [agent/Core/](agent/Core/) → [agent/Protocols/](agent/Protocols/) → [agent/Workflows/](agent/Workflows/) → [agent/Skills/](agent/Skills/). Each workspace's [CLAUDE.md](CLAUDE.md) is a pure routing table.

<!-- Add agent-specific handoff notes as you add agents to the project -->
