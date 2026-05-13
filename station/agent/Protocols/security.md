---
tags: [protocol, security]
description: Security enforcement — hard stops and hard enforcers.
---

# Protocol: Security Enforcement

> [!warning]
> This is a Protocol — violations are hard stops. No exceptions.

---

## Hard Stops (NEVER)

- NEVER include real secrets, API keys, or credentials in code, plans, docs, or examples
- NEVER commit `.env` files or files containing credentials
- NEVER bypass security checks or validation
- NEVER expose internal error details to external users
- NEVER approve a plan that doesn't reference SecurityStandards.md

## Hard Enforcers (ALWAYS)

- ALWAYS validate input at system boundaries (API endpoints, user input, external data)
- ALWAYS use parameterized queries — never string-concatenate SQL
- ALWAYS handle errors without leaking stack traces or internal paths
- ALWAYS check that secrets are loaded from environment variables, never hardcoded
- ALWAYS flag if any agent output includes files outside their designated workspace
- ALWAYS verify security domains during code review (secrets, scope, error handling)

---

## Full Reference

For the complete security standard, read:
[Playbook/Standards/SecurityStandards.md](../../Playbook/Standards/SecurityStandards.md)

> [!note]
> The path above is relative to the project docs location. Check your workspace CLAUDE.md → External References for the exact path.
