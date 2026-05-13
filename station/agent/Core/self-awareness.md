---
tags: [core, self-awareness]
description: Behavioral guardrails and dynamic context monitoring reference.
---

# Self-Awareness

## Dynamic Context Monitoring

Your context usage is tracked automatically by two sensors:

- **Status bar** (after every response) — shows context %, turns, and session health to the user
- **Context guard** (before every prompt) — injects behavioral constraints when context grows high

Follow any context advisories injected into your prompt — they are calibrated to your actual usage.

## Behavioral Guardrails

These are not automated. Follow them yourself:

- If you're losing track of the task, re-read [agent/Core/memory.md](memory.md).
- If a task has more than 10 steps, break it into sub-tasks before starting.
- Never continue if you're unsure what the plan says — re-read it.
- If you've already read a file this session, don't re-read it unless it changed.
