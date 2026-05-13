---
tags: [standards, security]
description: Hard security rules for all agents and application code.
---

# Bonsai-Eval — Security Standards

> [!warning]
> **Rule Zero — Directory Isolation**
> Every agent operates ONLY in its designated directory. No exceptions.
> Reading files outside your directory for context is permitted. Creating, editing, or deleting files outside your directory is NEVER permitted.
> If a task seems to require crossing a directory boundary, STOP and ask the user.

---

## Domain 1 — Secrets Management

- NEVER commit `.env`, credentials, API keys, or tokens to git
- NEVER log, print, or echo secrets — not even in debug mode
- NEVER hardcode secrets in source files — always use environment variables
- NEVER include real credentials in code examples, comments, or documentation
- When creating new services that need secrets, add the key name to `.env.example` with a placeholder value
- If you encounter a secret in code, flag it immediately and STOP

---

## Domain 2 — Destructive Operations

- NEVER run `rm -rf`, `git clean -f`, `git reset --hard`, or `git checkout .` without explicit user approval
- NEVER force-push without explicit user approval
- NEVER drop database tables, truncate data, or run destructive migrations without explicit user approval
- NEVER delete git branches without explicit user approval
- If a destructive action seems like the only path forward, STOP and ask the user

---

## Domain 3 — Scope Boundaries

- Each agent operates ONLY in its designated directory
- No agent modifies `CLAUDE.md`, `.env`, or infrastructure config without explicit user approval
- No agent installs new dependencies without explicit user approval — propose it, don't do it
- No agent makes architectural decisions — encounter a design fork, STOP and flag it

---

## Domain 4 — Input Validation

- Validate all external input at system boundaries (API endpoints, user input, file uploads)
- Use parameterized queries — never string-concatenate SQL
- Sanitize output to prevent XSS
- Validate file types and sizes before processing

---

## Domain 5 — Error Handling

- Never expose stack traces, internal paths, or system details in error responses
- Log errors with context but without sensitive data
- Use structured error responses with appropriate HTTP status codes
- Fail closed — deny access on error, don't default to permissive

---

## Domain 6 — Dependencies

- Pin dependency versions — no floating ranges in production
- Review changelogs before upgrading major versions
- Never install packages from untrusted sources
- Keep dependencies up to date — check for known vulnerabilities
