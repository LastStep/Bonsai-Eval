## Triggers

**Activate when:**
- Writing a new implementation plan
- Structuring a plan with tier rules and verification steps

---
# Skill: Planning Template

---

## Plan Tiers

### Tier 1 — Patch

Small, single-domain changes. Bug fixes, config tweaks, simple additions.

**Required sections:** Goal, Steps, Verification.

### Tier 2 — Feature

Multi-step or multi-domain work. New features, refactors, migrations.

**Required sections:** Goal, Context, Steps (with sub-steps), Dependencies, Security, Verification.

---

## Template

```markdown
# Plan NN — Title

**Tier:** 1 | 2
**Status:** Draft | Active | Complete
**Agent:** backend | frontend | both

## Goal

One sentence: what does "done" look like?

## Context

(Tier 2 only) Why are we doing this? What led here?

## Steps

1. Step one — specific file, function, shape
2. Step two — explicit enough that the agent makes zero design decisions

## Dependencies

(Tier 2 only) What must exist before this plan can execute?

## Security

> [!warning]
> Refer to SecurityStandards.md for all security requirements.

## Verification

- [ ] Concrete check 1
- [ ] Concrete check 2
```

---

## Rules

- Steps must be specific — no "implement the feature" hand-waving
- File paths, function names, and data shapes must be explicit
- Every plan MUST reference security standards
- Verification must be concrete and testable
