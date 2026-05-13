---
tags: [skill, issues]
description: Issue types, importance levels, domain labels, and classification heuristics for intake triage.
---
## Triggers

**Activate when:**
- Classifying or triaging a new issue or bug report
- Determining issue type, importance, and domain labels

---

# Skill: Issue Classification

---

## Types

| Type | Description | Examples |
|------|-------------|----------|
| bug | Something is broken or behaves incorrectly | Crash, wrong output, regression, data corruption |
| feature | New capability that doesn't exist yet | New endpoint, new UI component, new CLI command |
| change | Modification to existing behavior | Rename field, change validation rules, update flow |
| debt | Technical cleanup with no user-facing change | Refactor, remove dead code, improve test coverage |
| research | Investigation that produces findings, not code | Evaluate library, benchmark approaches, document architecture |

---

## Importance

| Level | Meaning | Response |
|-------|---------|----------|
| critical | Blocks users, data loss risk, security vulnerability | Drop current work, fix immediately |
| high | Significant impact, degraded functionality | Next up, address promptly |
| medium | Important but not urgent, workaround exists | Schedule in current cycle |
| low | Nice to have, minor improvement | Backlog, address when convenient |

---

## Domain Labels

Domains represent which part of the codebase is affected. Common domains:

- `frontend` — UI, components, client-side logic
- `backend` — API, server-side logic, business rules
- `database` — schema, migrations, queries
- `infrastructure` — CI/CD, deployment, containers
- `cli` — command-line interface, flags, output
- `docs` — documentation, guides, references

An issue can span multiple domains. When it does, the plan should have separate step sections per domain with explicit sequencing.

---

## Classification Process

1. **Read the full issue** — title, body, comments, linked issues
2. **Identify the symptom** — what the user sees vs. what should happen
3. **Trace to root cause** — which code path is responsible
4. **Map domains** — which parts of the codebase need changes
5. **Assess importance** — based on user impact, not implementation effort
6. **Check for duplicates** — is this already tracked in Backlog.md or Status.md?
7. **Check for related items** — are there Backlog items that should be bundled?

---

## GitHub Label Mapping

When working with GitHub Issues, map classifications to labels:

- **Type** → `bug`, `feature`, `change`, `debt`, `research`
- **Importance** → `critical`, `high`, `medium`, `low`
- **Domain** → `frontend`, `backend`, `database`, `infra`, `cli`, `docs`
