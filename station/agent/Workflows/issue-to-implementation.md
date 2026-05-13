---
tags: [workflow, orchestration]
description: End-to-end autonomous workflow — issue intake to shipped code via research, planning, agent dispatch, review loops, and structured logging.
---
## Triggers

**Slash command:** `/issue-to-implementation`
**Activate when:**
- Taking an issue from intake through to shipped code
- Running the full autonomous implementation workflow

**Examples:**
> **User:** "Pick up issue #15 and ship it"
> **Action:** Load issue-to-implementation workflow, analyze issue, plan, dispatch, review, merge

---

# Workflow: Issue to Implementation

> The Tech Lead's primary orchestration workflow. Issue → shipped code.

> [!warning]
> **Hard rules:**
> 1. **You never write code.** All implementation goes to subagents. You plan, orchestrate, and review.
> 2. **All code changes happen in isolated worktrees.** Nothing touches the main working tree until the final merge after all audits pass.

---

## Prerequisites

Load before starting:

- [agent/Skills/issue-classification.md](../Skills/issue-classification.md) — issue types, importance levels
- [agent/Skills/dispatch.md](../Skills/dispatch.md) — triage rules, agent prompt structure
- [agent/Skills/planning-template.md](../Skills/planning-template.md) — plan format and tier rules

---

## Overview

```
Pre-Flight → Intake → Analysis → Research Loop → Clarify → Plan → Self-Review → Triage → Execute → Review Loop → Logging → Final Audit → Merge & Close
```

---

## Autonomy Modes

This workflow supports two modes:

- **Supervised** (default) — pause at Clarify and Triage for user input
- **Autonomous** — skip Clarify if research resolves all questions; self-dispatch if triage criteria are met

The user sets the mode at the start. When in doubt, default to supervised.

---

## Phase 0: Pre-Flight

1. Run `git status`. If the working tree has uncommitted changes, **stop and warn the user**. Suggest committing or stashing before proceeding.
2. Check [Playbook/Status.md](../../Playbook/Status.md) — if there's in-progress work that could conflict, flag it before starting.

---

## Phase 1: Intake

**Trigger:** User assigns a specific issue, asks to scan for work, or points to a Backlog.md item.

### From GitHub Issues

- Use `gh issue list` / `gh issue view` to read the issue
- Extract: title, body, labels, comments, linked issues

### From Backlog.md

- Read the item, extract context and priority
- Check if there's a linked GitHub issue

### Classify

Use [agent/Skills/issue-classification.md](../Skills/issue-classification.md):

- **Type:** bug, feature, change, debt, research
- **Domains:** which parts of the codebase are affected
- **Importance:** critical, high, medium, low

---

## Phase 2: Analysis

Understand what the issue touches before planning anything.

1. **Trace** — use Explore agents or Grep/Read to find affected files, functions, modules
2. **Blast radius** — what files change, what tests are affected, what depends on the changed code
3. **Architecture** — read relevant architecture docs, schemas, API specs
4. **Overlap** — check [Playbook/Status.md](../../Playbook/Status.md) for in-progress work that conflicts
5. **Related items** — check [Playbook/Backlog.md](../../Playbook/Backlog.md) for items that should be bundled with this work
6. **Prior decisions** — check [Logs/KeyDecisionLog.md](../../Logs/KeyDecisionLog.md) for constraints on the approach

---

## Phase 3: Research Loop

Deepen understanding until confident the plan will be correct.

### Each pass:

1. **Web research** — best practices, library documentation, known issues, similar implementations
2. **Codebase patterns** — how does the project handle similar cases? What conventions exist?
3. **Dependency check** — will this require new dependencies? Are there version constraints?
4. **Assumption verification** — test each assumption against actual code

### Confidence gate:

After each pass, rate confidence 1–5:

- **>= 4** — proceed to Clarify
- **< 4** — identify the specific gaps driving low confidence, research those gaps, re-rate
- **Max 3 passes** — if still < 4 after 3 passes, proceed but flag low-confidence areas explicitly in the plan

> The goal is not exhaustive research. The goal is enough confidence that the plan won't need revision mid-execution.

---

## Phase 4: Clarify

Ask the user about things that analysis and research couldn't resolve.

- Open design decisions
- Ambiguous requirements
- Priority conflicts
- Scope boundaries

> Don't ask questions you can answer from the codebase or research.
> One question at a time — each answer may resolve the next question.
> **Autonomous mode:** Skip entirely if confidence >= 4 and no unresolvable ambiguities exist.

---

## Phase 5: Plan

Write `Playbook/Plans/Active/NN-kebab-case-name.md` using the planning-template skill.

- **Tier 1 (Patch):** bug fix, config tweak, simple addition — single-domain, well-scoped
- **Tier 2 (Feature):** new capability, multi-step, multi-domain, architectural

**Multi-domain:** Write separate step sections per agent. Mark parallel vs sequential.

**Include:**

- Verification steps — concrete commands or checks that prove the work is correct
- Security references — every plan must reference SecurityStandards.md
- Research findings — anything that constrains the implementation

---

## Phase 6: Self-Review

- [ ] Steps are specific — no design decisions left to the agent
- [ ] File paths, function names, data shapes are explicit
- [ ] Security standards referenced
- [ ] Verification is concrete and testable
- [ ] No scope creep beyond the issue
- [ ] Edge cases addressed
- [ ] Multi-domain dependencies sequenced correctly
- [ ] Research findings incorporated — no assumptions contradicted by evidence

Fix every issue before proceeding. Do not carry known problems into dispatch.

---

## Phase 7: Triage

Use the decision tree from [agent/Skills/dispatch.md](../Skills/dispatch.md).

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
- Low-confidence areas flagged in Phase 3

**When escalating:** Present the plan and point to the specific decisions that need attention. Wait for approval before dispatching.

---

## Phase 8: Execute

> [!warning]
> **You do not write code.** Every implementation change — no matter how small — is dispatched to a subagent running in an isolated worktree. You orchestrate; they implement.

Dispatch implementation agents using the dispatch skill. See [agent/Skills/dispatch.md](../Skills/dispatch.md) for full prompt structure and syntax.

### Worktree isolation

Every implementation agent **must** use `isolation: "worktree"`. This creates a temporary git worktree on a fresh branch. The main working tree stays clean until the explicit merge in Phase 12.

- Worktrees are auto-cleaned if the agent makes no changes
- If the agent succeeds, you get back the worktree path and branch name — use these for review and merge
- Never ask an agent to write to the main working tree

### Dispatch patterns

**Single task:**

```
Agent(subagent_type: "general-purpose", isolation: "worktree", prompt: "...")
```

**Independent parallel tasks** (send in a single message so they run concurrently):

```
Agent(subagent_type: "general-purpose", isolation: "worktree", run_in_background: true, prompt: "task A...")
Agent(subagent_type: "general-purpose", isolation: "worktree", run_in_background: true, prompt: "task B...")
```

**Sequential dependent tasks** (wait for the first to finish, pass its branch to the next):

```
# First: dispatch agent A, wait for result
Agent(subagent_type: "general-purpose", isolation: "worktree", prompt: "task A...")
# Then: dispatch agent B on agent A's branch or with its output as context
Agent(subagent_type: "general-purpose", isolation: "worktree", prompt: "task B... Agent A's branch: {branch}...")
```

### Agent prompt structure

1. **Workspace bootstrap** — "Read `CLAUDE.md` at the project root first, then `{workspace}/CLAUDE.md`."
2. **Context** — the problem being solved (from the issue)
3. **Plan steps** — only this agent's steps, copied verbatim from the plan
4. **Plan location** — path to the plan file
5. **Verification** — what to run after completing (e.g., `make build && go test ./...`)
6. **PR creation** — "After verification passes, push your branch and create a **draft PR** targeting `main`. Use this format for the PR body:"
   ```
   ## Summary
   {what and why, 1-3 sentences}
   Closes #{issue_number}

   ## Changes
   - `path/file` — what changed

   ## Plan
   {link to plan file or "No plan — Tier 1 patch."}

   ## Verification
   - [x] `make build` — passes
   - [x] `go test ./...` — passes
   ```
   "Report the PR URL back to me."
7. **Constraints:**
   ```
   - Don't modify files outside the scope of the plan
   - Don't make design decisions — if the plan is ambiguous, stop and report
   - Don't add features, refactor code, or make improvements beyond what the plan specifies
   - If something is unclear, stop and report — don't guess
   - Run verification steps before reporting completion
   - Create a draft PR after verification — never merge directly
   ```

Do NOT include: conversation history, other agents' steps, or unnecessary context.

### After dispatch

Wait for the agent notification — don't poll. When it returns:
1. Note the **draft PR URL** and branch name from the result
2. If the agent failed to create a PR, push the branch and create it yourself
3. Proceed to Phase 9 (Review Loop)

---

## Phase 9: Review Loop

When the execution agent finishes, enter the review cycle. All review happens against the worktree branch — the main tree is still untouched.

### Step 1 — Self-review the output

- Read the agent's summary
- Diff the worktree branch against main — `git diff main...{branch}`
- Check every plan step was followed, nothing improvised
- Check for scope creep (changes not in the plan)

### Step 2 — Dispatch review agent(s)

For substantial changes, dispatch an independent review agent (no worktree needed — reviewers only read):

```
Agent(subagent_type: "general-purpose", prompt:
  "Review the changes on branch {branch}.
   Read the plan at {plan-path}.
   Use the review checklist at {workspace}/agent/Skills/review-checklist.md.
   Check: correctness, security, test coverage, standards compliance.
   Report pass/fail with specific issues found.")
```

For security-sensitive changes, also dispatch a security review in parallel:

```
Agent(subagent_type: "general-purpose", prompt:
  "Security review of changes on branch {branch}.
   Check against {workspace}/Playbook/Standards/SecurityStandards.md.
   Focus on: input validation, auth, secrets, error handling, dependency safety.
   Report pass/fail with specific findings.")
```

### Step 3 — Evaluate review results

| Result | Action |
|--------|--------|
| All checks pass | Proceed to Logging |
| Minor issues found | Dispatch a **fix agent in a new worktree based on the same branch**, then re-review from Step 2 |
| Major issues found | Escalate to user with specific problems listed |

When dispatching a fix agent for minor issues:

```
Agent(subagent_type: "general-purpose", isolation: "worktree", prompt:
  "You are fixing review findings on branch {branch}.
   Git checkout {branch} first, then apply these fixes:
   {specific issues from review}
   Run verification: make build && go test ./...
   Constraints: only fix what's listed, nothing else.")
```

### Iteration limits

- **Max 3 execute-review cycles** before mandatory escalation to user
- Track the iteration count explicitly
- If hitting the limit, the plan likely needs revision — not just the code

---

## Phase 10: Logging

Update all tracking systems. Do all of the following that apply:

### 1. Execution log

Append to `Logs/RoutineLog.md`:

```markdown
### YYYY-MM-DD — Issue #N: Title
- **Plan:** Plans/Active/NN-name.md
- **Iterations:** N execute-review cycles
- **Issues found:** (list any issues caught during review)
- **Result:** completed | partial | escalated
```

### 2. GitHub Issue

If the issue came from GitHub, comment with:

- What was implemented
- Key decisions made during execution
- Test results
- Any caveats or follow-up items

### 3. Status

Update `Playbook/Status.md`:

- Move to Recently Done with today's date, or
- Update In Progress if partially complete

### 4. Backlog

Update `Playbook/Backlog.md`:

- Remove the item if it was sourced from there
- Add any new items discovered during implementation

### 5. Completion report

If reports scaffolding is installed, submit a report to `Reports/Pending/` using the report template.

---

## Phase 11: Final Audit

Before merging, verify holistically:

1. **Tests** — run the full test suite, not just new tests
2. **Lint & format** — run project linters and formatters
3. **Build** — verify a clean build with no warnings
4. **Scope check** — the diff should match the plan; flag anything extra
5. **Security scan** — no secrets committed, no new vulnerable dependencies
6. **Stale references** — no broken imports, no references to removed or renamed code
7. **Documentation** — if behavior changed, are docs updated?

If any check fails: fix it, re-verify the fix, and document what was caught in the execution log.

---

## Phase 12: Review PR & Merge

Only merge after all audits in Phase 11 pass. The draft PR has existed since Phase 8 — now it's time to review, promote, and merge it.

### 1. Review the PR

Use the PR review workflow ([agent/Workflows/pr-review.md](pr-review.md)):

```bash
gh pr view {pr_number} --json title,body,files,additions,deletions
gh pr diff {pr_number}
```

Review passes: scope check, correctness, security, performance, maintainability, standards.

If issues are found, dispatch a fix agent on the same branch, push the fix, and re-review.

### 2. Promote and merge

```bash
# Mark ready for review
gh pr ready {pr_number}

# Merge (squash for clean history on small PRs, merge commit for multi-commit branches)
gh pr merge {pr_number} --squash --delete-branch
# or for larger feature branches:
gh pr merge {pr_number} --merge --delete-branch
```

If merge conflicts exist: checkout the branch locally, rebase onto main, force-push, then merge.

### 3. Post-merge verification

Run the full test suite and build on main after merge:

```bash
git pull && make build && go test ./...
```

If post-merge tests fail: revert the merge commit, fix on the branch, create a new PR, re-audit.

### 4. Close out

1. **GitHub Issue** — should auto-close from `Closes #N` in the PR. If not, close manually with a comment.
2. **Update Status.md** — ensure Recently Done entry exists
3. **Update memory** — if significant architectural decisions were made, update `agent/Core/memory.md`
4. **Notify user** — concise summary: what was done, how many iterations, PR link, any follow-ups

---

## Quick Reference

| Phase | Key Tools | Exit Criteria |
|-------|-----------|---------------|
| Pre-Flight | `git status` | Clean working tree |
| Intake | `gh`, Backlog.md | Issue classified |
| Analysis | Explore agents, Grep, Read | Blast radius mapped |
| Research | WebSearch, WebFetch, Read | Confidence >= 4 (or 3 passes exhausted) |
| Clarify | Direct conversation | No unresolved ambiguities |
| Plan | Write tool | Plan file written |
| Self-Review | Internal checklist | All checks pass |
| Triage | Decision tree | Dispatch or escalate decided |
| Execute | Agent tool (worktree) | Agent(s) complete, draft PR(s) created |
| Review | Review agents, diff | All reviews pass (max 3 cycles) |
| Logging | Status.md, GitHub, logs | All systems updated |
| Final Audit | Tests, lint, build | All green |
| Review PR & Merge | `gh pr`, pr-review workflow | PR merged, issue closed |

---

## Failure Modes

| Situation | Action |
|-----------|--------|
| Research confidence stays < 4 after 3 passes | Proceed with explicit caveats in plan; flag gaps to user at Triage |
| Execute-review loop hits 3 iterations | Stop and escalate — the plan likely needs revision, not just the code |
| Subagent fails to create draft PR | Push the branch yourself and create the draft PR manually |
| PR has merge conflicts | Rebase branch onto main, force-push, re-run verification |
| Post-merge tests fail | Revert the merge commit, fix on branch, new PR, re-audit |
| Agent produces output outside plan scope | Reject the output. Re-dispatch with tighter constraints |
| Conflicting in-progress work discovered | Stop. Coordinate with user before proceeding |
| Agent fails or times out | Check agent summary for partial work. Decide: resume on same worktree or start fresh |
