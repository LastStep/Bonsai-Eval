#!/usr/bin/env bash
set -euo pipefail

# dispatch-guard — Tech Lead Agent
# Validates code agent dispatches before execution:
#   1. Uses worktree isolation
#   2. References a plan
#   3. Plan exists in Plans/Active/ and assigns the correct agent
# Exit 2 = block the tool call.
#
# # Repo-root resolution (precedence)
#
# Mirrors the scope-guard-files.sh wiring (PR #6 H-1 fix). Production
# (`station/.claude/settings.json`) invokes `bash dispatch-guard.sh "<repo-root>"`.
# Without the positional arg the python heredoc falls back to a CWD-relative
# `station/` path — which fails at rung-2/rung-3 where the Inspect sandbox CWD
# differs from the host repo root and surfaces as a false
# "Plan NNN not found in Playbook/Plans/Active/" block.
#
# Precedence:
#   1. Positional `$1` — production wiring; exported as
#      BONSAI_DISPATCH_GUARD_REPO_ROOT so the python heredoc sees it.
#   2. Pre-existing BONSAI_DISPATCH_GUARD_REPO_ROOT env var (test seam).
#   3. CWD-relative `station/` (legacy fallback).

if [ -n "${1:-}" ]; then
  export BONSAI_DISPATCH_GUARD_REPO_ROOT="$1"
fi

INPUT=$(cat)

echo "$INPUT" | python3 -c "
import sys, json, re, os
from pathlib import Path

data = json.load(sys.stdin)
tool_input = data.get('tool_input', {})
prompt = tool_input.get('prompt', '')
isolation = tool_input.get('isolation', '')

if not prompt:
    sys.exit(0)

# Detect target workspace from CLAUDE.md bootstrap reference.
# Keys are workspace-root prefixes (must include trailing slash) — the guard
# matches '<prefix>CLAUDE.md' in the dispatched prompt. Values are agent kinds
# matched (case-insensitive) against the plan's Dispatch table.
# Workspace conventions come from .bonsai.yaml + the agent catalog (one entry
# per agent kind). tech-lead is included for completeness; in normal flow the
# orchestrator does not dispatch to itself, so this key rarely fires.
workspaces = {
    'backend/': 'backend',
    'devops/': 'devops',
    'frontend/': 'frontend',
    'fullstack/': 'fullstack',
    'security/': 'security',
    'station/': 'tech-lead',
}

target_workspace = None
target_agent = None
for ws, agent in workspaces.items():
    if ws + 'CLAUDE.md' in prompt:
        target_workspace = ws
        target_agent = agent
        break

# Not a code agent dispatch (no workspace CLAUDE.md in prompt) — skip
if not target_workspace:
    sys.exit(0)

errors = []

# Check 1: worktree isolation required
if isolation != 'worktree':
    errors.append('Missing worktree isolation. Code agent dispatches MUST use isolation: \"worktree\".')

# Check 2: plan reference required
plan_match = re.search(r'Plan\s+(\d+)', prompt, re.IGNORECASE)
plan_path_match = re.search(r'Plans/Active/(\d+)-[^\s\]\"\x27)]+\.md', prompt)

plan_number = None
if plan_match:
    plan_number = plan_match.group(1)
elif plan_path_match:
    plan_number = plan_path_match.group(1)
else:
    errors.append('No plan referenced. Prompt must mention a plan number (e.g. \"Plan 42\") or path to Plans/Active/.')

# Check 3: plan file exists and assigns correct agent.
# Repo-root resolution: bash side exports BONSAI_DISPATCH_GUARD_REPO_ROOT when
# given a positional \$1. When unset, fall back to the legacy CWD-relative
# 'station/' (preserves test behaviour for callers that cd to repo root).
repo_root = os.environ.get('BONSAI_DISPATCH_GUARD_REPO_ROOT')
docs_path = (Path(repo_root) / 'station') if repo_root else Path('station')
if plan_number:
    plans_dir = docs_path / 'Playbook' / 'Plans' / 'Active'
    plan_file = None
    if os.path.isdir(str(plans_dir)):
        for f in os.listdir(str(plans_dir)):
            if f.startswith(plan_number + '-') and f.endswith('.md'):
                plan_file = str(plans_dir / f)
                break

    if plan_file is None:
        errors.append(f'Plan {plan_number} not found in Playbook/Plans/Active/.')
    else:
        with open(plan_file, 'r') as pf:
            plan_content = pf.read()

        # Parse Dispatch table rows
        dispatch_match = re.search(
            r'## Dispatch\s*\n\s*\n?\|.*?\n\|[-|\s]+\n((?:\|.*\n)*)',
            plan_content
        )
        if dispatch_match:
            dispatch_rows = dispatch_match.group(1).lower()
            if target_agent.lower() not in dispatch_rows:
                errors.append(
                    f'Plan {plan_number} Dispatch table does not assign \"{target_agent}\". '
                    f'Check the plan — wrong agent for this workspace.'
                )

if errors:
    # F1 — emit BLOCKED to stdout (not stderr) so inspect-ai's claude-code
    # bridge captures the marker into the transcript. Other PreToolUse sensors
    # in this directory already use stdout; this aligns dispatch-guard.
    # The corresponding marker pin is in
    # bonsai_eval/scorers/deterministic.py:_HOOK_MARKERS['dispatch-guard'].
    print(f'BLOCKED: Dispatch guard failed for {target_agent}:')
    for i, e in enumerate(errors, 1):
        print(f'  {i}. {e}')
    sys.exit(2)

sys.exit(0)
"
