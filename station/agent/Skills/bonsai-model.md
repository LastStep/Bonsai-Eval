## Triggers

**Activate when:**
- User asks what Bonsai is or what it does
- User asks to customize the workspace for project-specific needs
- Deciding whether to reuse a catalog ability or create a custom one
- Explaining the mental model behind agents, abilities, or scaffolding
- Auditing which installed abilities are a fit vs unused for the project

---

# Skill: Bonsai Mental Model

> This skill is for you, the AI agent working inside a Bonsai-managed workspace. It explains what Bonsai is so you can reason about customizing the workspace rather than improvising.

---

## What Bonsai is

Bonsai is a CLI tool (`bonsai`) that scaffolds structured agent workspaces. One binary. Written in Go. Managed via `.bonsai.yaml` in the project root.

Bonsai is **not**:
- A runtime, framework, or server
- An agent itself (it's infrastructure for agents)
- A content generator (it doesn't write your code, plans, or docs — you do)

Bonsai's job is to lay out a workspace with the files and hooks an agent (you) needs to work coherently. After `bonsai init`, Bonsai gets out of the way until the user runs it again.

---

## Core concept — the workspace

A Bonsai workspace is a directory (e.g. `station/`, `backend/`) that contains:

```
<workspace>/
├── CLAUDE.md           ← nav table + quick triggers, always loaded
├── agent/
│   ├── Core/           ← identity, memory, self-awareness (always loaded)
│   ├── Protocols/      ← rules loaded every session (memory, security, scope, session-start)
│   ├── Skills/         ← reference material loaded when a specific activity starts
│   ├── Workflows/      ← end-to-end activity procedures loaded when activated
│   ├── Routines/       ← periodic self-maintenance tasks
│   └── Sensors/        ← auto-enforced shell hooks (not loaded — executed by Claude Code)
├── .claude/
│   ├── settings.json   ← hook wiring for sensors
│   └── ...             ← path-scoped rules, skill bundles
└── (user content — Playbook, Logs, etc. if installed via scaffolding)
```

Each agent has its own workspace. A multi-agent project typically has `station/` (tech-lead) + one workspace per other agent.

---

## Catalog — what's available

The Bonsai binary ships with a catalog of reusable pieces. Six categories:

| Category | What it is | Example | When to use |
|----------|------------|---------|-------------|
| **agents** | Agent-type definitions with defaults | `tech-lead`, `backend`, `frontend`, `fullstack`, `devops`, `security` | First step — pick agent type at `bonsai add` |
| **skills** | Reference material — standards, templates, checklists | `coding-standards`, `review-checklist`, `bubbletea`, `bonsai-model` | Agent loads when doing domain-specific work |
| **workflows** | End-to-end procedures for a task | `code-review`, `planning`, `session-wrapup` | Agent follows step-by-step when activity begins |
| **protocols** | Rules always active (loaded every session) | `memory`, `security`, `scope-boundaries`, `session-start` | Define non-negotiables |
| **sensors** | Shell scripts run as Claude Code hooks | `status-bar`, `scope-guard-files`, `context-guard`, `session-context` | Automate enforcement — agent doesn't choose to run these |
| **routines** | Periodic self-maintenance tasks | `backlog-hygiene` (7d), `memory-consolidation` (5d) | Scheduled drift-checks |

Inspect the live catalog:
- `bonsai catalog` — interactive browser
- `bonsai catalog --json` — machine-readable stdout (for you)
- `.bonsai/catalog.json` at project root — filesystem snapshot (for you, no CLI call needed)

---

## Installed state — `.bonsai.yaml` + `.bonsai-lock.yaml`

Two files track project state:

- **`.bonsai.yaml`** — config Bonsai writes for you. Lists which agents exist + which abilities each has installed. **Read-only for agents** — never hand-edit the `skills/workflows/protocols/sensors/routines` lists or `custom_items` map; let `bonsai update` register custom files.
- **`.bonsai-lock.yaml`** — content-hash tracking. Detects user-modified generated files. Not edited by hand.

Read `.bonsai.yaml` to know what the user already chose. Don't overwrite it.

> **Workspace looks off?** Run `bonsai validate` first — read-only audit that surfaces orphaned registrations, stale lock entries, untracked custom files, and frontmatter problems. Use `bonsai validate --json` for machine-readable output. Then run `bonsai update` to fix what it finds.

---

## Key commands

| Command | What it does |
|---------|-------------|
| `bonsai init` | First-run setup. Picks tech-lead, scaffolding, and starter abilities. Writes `.bonsai.yaml`. |
| `bonsai add` | Adds a new agent OR adds abilities to an existing agent. Interactive. |
| `bonsai remove <agent\|skill\|...>` | Removes an agent or a specific ability. Interactive. |
| `bonsai update` | Detects user-dropped custom files, re-renders abilities against latest catalog, resolves conflicts. |
| `bonsai validate` | Read-only audit — detect orphaned registrations, stale lock entries, untracked custom files, frontmatter problems. JSON via `--json`. |
| `bonsai list` | Shows installed agents + their abilities. |
| `bonsai catalog` | Browses what's available (add `--json` for stdout). |
| `bonsai guide` | Reads bundled onboarding docs. |

All interactive commands have non-TTY fallbacks for scripting.

---

## Customization model

Three layers, in order of preference:

### 1. Install from catalog

Default path. Catalog-shipped abilities are maintained, tested, and re-rendered consistently on `bonsai update`.

```
bonsai add                # adds an ability from catalog
bonsai remove skill X     # removes it
```

### 2. Custom file drop-in

User (or you, on behalf of user) creates a new file directly in `agent/Skills/my-thing.md` with frontmatter like:
```yaml
---
name: my-thing
display_name: My Thing
description: What this does
type: skill
---
```
Then runs `bonsai update`. Bonsai detects the file, prompts the user to confirm tracking, and adds it to `.bonsai.yaml` under that agent's Skills list. Lock-tracked from then on.

> [!warning]
> **Do not manually register custom abilities in `.bonsai.yaml`.** If you add a name to `skills:` (or any other list) without `bonsai update` discovering it, the file is never lock-tracked and `custom_items[name]` is never populated — CLAUDE.md will render the row with an empty description and the file will silently desync from the lockfile. Always: drop file with frontmatter, then `bonsai update`.

Use for: project-specific standards, team-specific workflows, anything that wouldn't generalize.

### 3. Contribute to upstream catalog (rare)

If the custom ability is general enough, propose it upstream. Not your call to make — this is a user decision.

---

## Scope & ownership

- **Bonsai owns:** anything it generated (tracked in `.bonsai-lock.yaml`). On `bonsai update`, these get re-rendered against latest catalog.
- **User owns:** custom files (tracked via frontmatter). On `bonsai update`, these get detected and surfaced, not overwritten.
- **Never owned:** files outside the workspace (source code, business logic, everything else).

If a generated file is modified by the user, lockfile detects the hash drift and prompts on next update: keep / overwrite / backup.

---

## Decision heuristics

When the user asks you to customize their Bonsai workspace, walk this decision tree:

### Is the need generic or project-specific?
- **Generic** (e.g. "add linting standards") → `bonsai catalog --json`, find existing catalog item, `bonsai add`.
- **Project-specific** (e.g. "our team reviews PRs with two approvals") → create custom file in `agent/Skills/`, run `bonsai update`.

### Is this a rule or a reference?
- **Rule, always active** → protocol.
- **Reference, loaded on activity** → skill.
- **End-to-end procedure** → workflow.
- **Recurring self-check** → routine.
- **Automated enforcement** → sensor.

### Should this be a new agent or an ability on an existing one?
- **New agent** when there's a clear role boundary (security reviews, devops ownership). Agents have their own workspace + identity.
- **Ability on existing agent** otherwise. Cheaper, avoids workspace sprawl.

### Is the user asking for something Bonsai doesn't directly support?
- Suggest the next-best catalog item and note the gap.
- If it's a recurring request across projects, suggest filing in the project's Backlog or proposing to upstream catalog.
- Don't invent CLI flags or behaviors that don't exist. Read `bonsai --help` first if unsure.

---

## Common patterns

### First-run customization (you are here most often)

1. User just ran `bonsai init`, gives you project context ("this is an animation studio pipeline in Blender + Python").
2. You read `.bonsai/catalog.json` for available abilities and `.bonsai.yaml` for current state.
3. You inspect project files (e.g. `package.json`, `requirements.txt`, source tree) to understand stack.
4. You propose: agents to add, skills to add/remove, scaffolding gaps.
5. User approves items individually or batch.
6. You run `bonsai add`, `bonsai remove`, or create custom files + `bonsai update`.
7. You log major decisions to `Logs/KeyDecisionLog.md` (if installed).

### Adding a new agent for a domain
1. `bonsai catalog --json` — check existing agent types.
2. If a fit exists: `bonsai add <type>`. Walk user through ability selection.
3. If no fit: suggest closest match + custom skill overrides, OR flag the gap as a potential upstream contribution.

### Fixing drift
1. `bonsai update` — detects custom-file drop-ins + re-renders generated files.
2. If conflicts: explain what was upstream-changed vs user-modified. Recommend keep/overwrite per item.
3. If stale peer-awareness suspected (multi-agent workspace, generated files look stale): re-run `bonsai update`.

---

## What NOT to do

- Don't edit `.bonsai-lock.yaml` by hand — Bonsai owns it.
- Don't edit generated files without understanding `bonsai update`'s conflict flow.
- Don't run `bonsai remove` or `bonsai add` without confirming scope with the user.
- Don't create shadow configuration outside `.bonsai.yaml` — but don't hand-edit `.bonsai.yaml` either. Bonsai state belongs in `.bonsai.yaml`, and **only `bonsai` commands write it**.
- Don't add custom files without frontmatter — they won't be detected by `bonsai update`.
- Don't reason about Bonsai from this doc alone when the live catalog is authoritative. This doc is a model; `bonsai catalog --json` is truth.

---

## Quick references

| I need to know... | Read / run |
|-------------------|-----------|
| What catalog items exist | `bonsai catalog --json` or `.bonsai/catalog.json` |
| What's installed in this project | `.bonsai.yaml` or `bonsai list` |
| Whether the workspace is in a consistent state | `bonsai validate` (or `bonsai validate --json`) |
| What a specific skill does | `cat <workspace>/agent/Skills/<name>.md` |
| What a sensor enforces | `cat <workspace>/agent/Sensors/<name>.sh` |
| What routines are active and their last-run dates | `<workspace>/agent/Core/routines.md` |
| Bonsai's own docs | `bonsai guide` |
