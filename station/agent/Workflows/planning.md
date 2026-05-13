---
tags: [workflow, planning]
description: End-to-end planning process — from request to dispatch-ready plan.
---
## Triggers

**Slash command:** `/planning`
**Activate when:**
- Starting end-to-end planning for a new feature or task
- Translating requirements into a structured implementation plan

**Examples:**
> **User:** "Plan the new caching layer"
> **Action:** Load planning workflow, analyze requirements, write plan to Plans/Active/

---

# Workflow: Planning

---

## When to Use

When a new task, feature, or fix needs a plan before agents can execute.

---

## Steps

### 1. Understand the Request

- What does the user want?
- What's the scope? (single-domain or multi-domain)
- What tier? (Tier 1 Patch or Tier 2 Feature — see [agent/Skills/planning-template.md](../Skills/planning-template.md))
- Check [Playbook/Backlog.md](../../Playbook/Backlog.md) — is this request already captured? Are there related P0/P1 items that should be bundled?

### 2. Research

- Read relevant architecture docs
- Check prior decisions that constrain the approach
- Trace the codebase — understand what exists before planning what to add

### 3. Surface Architectural Questions

If you see a design fork — raise it. Don't wait for the user to ask.

### 4. Write the Plan

- Use the appropriate tier template from [agent/Skills/planning-template.md](../Skills/planning-template.md)
- Steps must be specific enough that agents don't make design decisions

### 5. Self-Review

- [ ] Steps are specific — no design decisions left to the agent
- [ ] File paths, function names, shapes are explicit
- [ ] Security standards referenced
- [ ] Verification is concrete
- [ ] No scope creep

### 6. Hand Off

> [!warning]
> Your job is done. The next action is ALWAYS handoff — never execution.

- Present the plan to the user
- Dispatch to the appropriate code agent, or tell the user it's ready for dispatch
