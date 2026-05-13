---
tags: [logs, routines]
description: Append-only audit trail for routine executions. Each entry records outcome, changes, and notes.
---

# Routine Log

> [!note]
> Agents append to this log after completing a routine. Do not edit existing entries — this is an audit trail.

**Format:**

```
### YYYY-MM-DD — Routine Name
- **Outcome:** success | partial | skipped | deferred
- **Changes:** what was modified
- **Flags:** issues found
- **Notes:** context for future runs
```

---
