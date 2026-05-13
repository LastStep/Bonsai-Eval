---
tags: [reports, template]
description: Structured completion report template for code agents.
---

# Report Template

> [!note]
> Code agents use this template after completing work. Reports go to `Reports/Pending/`.

---

## Format

```markdown
---
tags: [report]
from: [agent type]
to: Tech Lead
plan: "Plan NN — name"
date: YYYY-MM-DD
status: [completed | partial | blocked | needs-review]
---

# Completion Report — Plan NN

## Status
[completed | partial (stopped at step N) | blocked (by X) | needs-review]

## Files Created
- `path/to/file` — what it does (one line)

## Files Modified
- `path/to/file` — what changed and why (one line)

## Verification Results
- Tests: N passed, N failed
- Coverage: X%

## Deviations from Plan
- None / describe what was different and why

## Things to Know
[Anything surprising, blockers, questions, or concerns. If nothing: "None."]
```

---

## File Naming

`YYYY-MM-DD-plan-NN-agent.md`

Example: `2026-04-01-plan-01-backend.md`
