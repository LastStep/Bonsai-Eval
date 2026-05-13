---
tags: [protocol, scope]
description: What you own, what you never touch, dispatch rules.
---

# Protocol: Scope Boundaries

> [!warning]
> This is a Protocol — violations are hard stops. No exceptions.

---

## Your Workspace

You operate ONLY within your designated workspace directory. This is your boundary.

## Rules

- **NEVER** modify files outside your workspace directory
- **NEVER** make architectural decisions — if the plan is ambiguous, ask the user
- **NEVER** add dependencies or change configuration without explicit plan authorization
- **ALWAYS** flag in your report if your changes might affect another workspace
- **ALWAYS** stay within the plan's scope — no extra "improvements" or "cleanups"

## When You See Something Wrong

If you notice a bug, tech debt, or improvement opportunity outside your current task scope:
1. Do NOT fix it inline
2. Add it to `Playbook/Backlog.md` with the appropriate priority and category
3. Note it in your report
4. Let the Tech Lead or user decide when to address it
