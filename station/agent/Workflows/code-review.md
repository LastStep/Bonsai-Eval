---
tags: [workflow, review]
description: Review agent output against the plan — correctness, standards, security.
---
## Triggers

**Slash command:** `/code-review`
**Activate when:**
- Reviewing agent output against the plan for correctness and standards
- Checking implementation changes before merging

**Examples:**
> **User:** "Review the changes on the feature branch"
> **Action:** Load code-review workflow, diff branch against main, check plan compliance

---

# Workflow: Code Review

---

## When to Use

When a code agent has completed a plan and submitted output for review.

---

## Steps

### 1. Load Context

- Read the plan the agent executed
- Read the agent's report
- Read security standards

### 2. Verify Completeness

- [ ] Every plan step is addressed
- [ ] No steps were skipped or partially done
- [ ] Verification checklist items pass

### 3. Check Quality

- [ ] Code follows project coding standards
- [ ] Tests exist and pass
- [ ] No unnecessary changes outside the plan's scope
- [ ] No hardcoded values that should be configurable

### 4. Check Security

- [ ] No secrets or credentials in code
- [ ] Input validation at system boundaries
- [ ] Error handling doesn't leak internal details
- [ ] Scope boundaries respected — agent stayed in their lane

### 5. Verdict

- **Pass** — mark plan as complete, update status
- **Revise** — list specific issues, send back to agent with clear instructions
- **Escalate** — flag to user if there's a design concern beyond the plan
