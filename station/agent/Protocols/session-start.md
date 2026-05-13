---
tags: [protocol, session]
description: Session startup — act on the context the session-context sensor already injected.
---

# Protocol: Session Start

> [!warning]
> This is a Protocol — follow it every session, no exceptions.

---

## Always

The session-context sensor injects the following at SessionStart: identity.md, memory.md, self-awareness.md, INDEX.md, Status.md, FieldNotes.md (when non-empty), Reports/Pending summary, and always-on Protocols (security, scope-boundaries). Health warnings (stale memory, Backlog P0, pending reports, log freshness) are also surfaced.

Your job:

1. **Address any flags** in the injected `memory.md` Flags section.
2. **Confirm work state** from `memory.md` — resume in-flight tasks or start fresh as appropriate.
3. **Act on health warnings** the sensor raised (stale memory, P0 items, pending reports).
4. **Process pending reports** by reading each file in `Reports/Pending/` (sensor gave summaries only).

> [!note]
> If the session-context sensor is NOT installed (headless agent), fall back to reading core files manually: identity, memory, self-awareness, INDEX, Status, then scan Backlog P0 and check Reports/Pending.

---

## Conditional (by task type)

### If executing a plan

- Read the assigned plan in full before any dispatch
- Read [Playbook/Standards/SecurityStandards.md](../../Playbook/Standards/SecurityStandards.md)
- Read relevant skills from [agent/Skills/](../Skills/)

### If starting new work

- Check for an existing plan in [Playbook/Plans/Active/](../../Playbook/Plans/Active/); ask the user if none
- Re-read scope-boundaries if touching new files

### If reviewing or reporting

- Read the relevant plan or prior report
- Read [Playbook/Standards/SecurityStandards.md](../../Playbook/Standards/SecurityStandards.md)
- Submit reports to `Reports/Pending/` using the report template
