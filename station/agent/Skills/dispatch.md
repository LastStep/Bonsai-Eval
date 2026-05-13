---
tags: [skill, dispatch]
description: How to dispatch work to code agents — triage rules, prompt structure, iteration tracking.
---
## Triggers

**Activate when:**
- Dispatching work to a code agent via worktree
- Writing an agent dispatch prompt with plan steps

---

# Skill: Dispatch Reference

---

## Triage — Self-Dispatch vs Escalate

### Self-dispatch when ALL true:

- Limited scope, well-defined changes
- No project structure or architecture changes
- Self-review passed clean
- Not critical importance
- Single domain, or multi-domain with clear sequencing
- Research confidence >= 4

### Escalate to user when ANY true:

- Touches project structure or architecture
- Cross-domain with design interdependencies
- Critical importance
- Unconfirmed assumptions in the plan
- Open questions from self-review
- Low-confidence areas from research

**When escalating:** Present the plan, point to the specific decisions that need attention, and wait for approval.

---

## Agent Tool Syntax

### Execution agents (always use worktree isolation)

**Single-domain:**

```
Agent(
  subagent_type: "general-purpose",
  isolation: "worktree",
  prompt: "..."
)
```

**Multi-domain (parallel):**

```
Agent(subagent_type: "general-purpose", isolation: "worktree", run_in_background: true, prompt: "backend steps...")
Agent(subagent_type: "general-purpose", isolation: "worktree", run_in_background: true, prompt: "frontend steps...")
```

Sequential if there's a dependency — e.g., backend API must exist before frontend calls it.

### Review agents (no worktree needed — they read, not write)

```
Agent(subagent_type: "general-purpose", prompt: "Review changes on branch {branch}...")
```

### Fix agents (reuse existing worktree)

When review finds minor issues, dispatch a fix agent on the same worktree branch — don't create a new one.

---

## Agent Prompt Structure

Include in this order:

1. **Workspace bootstrap** — "Read `{workspace}/CLAUDE.md` first."
2. **Context** — the problem being solved (from the issue)
3. **Plan steps** — only this agent's steps, copied verbatim from the plan
4. **Plan location** — path to the plan file in `Playbook/Plans/Active/`
5. **Verification** — what to run after completing (tests, build, lint)
6. **Constraints** — scope limits and behavioral rules

7. **PR creation** — "After verification passes, create a draft PR using the pr-creation skill format. Report the PR URL."

### Constraint block (always include):

```
Constraints:
- Don't modify files outside your workspace directory
- Don't make design decisions — if the plan is ambiguous, stop and report
- Don't add features, refactor code, or make improvements beyond what the plan specifies
- If something is unclear, stop and report — don't guess
- Run verification steps before reporting completion
- Create a draft PR after verification passes — never merge directly
```

### Do NOT include:

- Conversation history
- Other agents' steps
- Explanations of why the work matters
- Unnecessary context that doesn't inform the implementation

---

## Iteration Tracking

Track execute-review cycles explicitly:

```
Iteration 1: dispatch → review → [pass/fail + issues]
Iteration 2: fix dispatch → re-review → [pass/fail + issues]
Iteration 3: fix dispatch → re-review → [pass/fail + issues]
```

### Limits

- **Max 3 iterations** before mandatory escalation to the user
- If iteration 3 still fails, the problem is likely in the plan, not the code
- Document each iteration's findings in the execution log

---

## Rules

- **Always** use `isolation: "worktree"` for execution agents — never let agents write to the main tree
- **Never** dispatch without a written plan — the plan is the contract between you and the agent
- **Never** include conversation history or other agents' steps in the prompt
- After dispatch, wait for the agent notification — don't poll or sleep
- When the agent finishes, follow the Review Loop (Phase 9 of issue-to-implementation)
- If an agent fails or times out, check the summary for partial work before deciding to resume or restart

---

## Post-Dispatch Checklist

After each agent completes:

- [ ] Read agent summary
- [ ] Confirm draft PR was created — note the PR URL and branch
- [ ] Diff worktree against plan — every step followed, nothing improvised
- [ ] Check for scope creep — changes not in the plan
- [ ] Run verification commands from the plan
- [ ] Dispatch independent review agent if changes are substantial
- [ ] After review passes, promote draft PR to ready-for-review and merge
