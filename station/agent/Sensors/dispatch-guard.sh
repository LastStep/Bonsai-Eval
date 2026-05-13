#!/usr/bin/env bash
set -euo pipefail

# dispatch-guard — Tech Lead Agent
# Validates code agent dispatches before execution:
#   1. Uses worktree isolation
#   2. References a plan
#   3. Plan exists in Plans/Active/ and assigns the correct agent
# Exit 2 = block the tool call.

INPUT=$(cat)

echo "$INPUT" | python3 -c "
import sys, json, re, os

data = json.load(sys.stdin)
tool_input = data.get('tool_input', {})
prompt = tool_input.get('prompt', '')
isolation = tool_input.get('isolation', '')

if not prompt:
    sys.exit(0)

# Detect target workspace from CLAUDE.md bootstrap reference
workspaces = {
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

# Check 3: plan file exists and assigns correct agent
docs_path = 'station/'
if plan_number:
    plans_dir = docs_path + 'Playbook/Plans/Active'
    plan_file = None
    if os.path.isdir(plans_dir):
        for f in os.listdir(plans_dir):
            if f.startswith(plan_number + '-') and f.endswith('.md'):
                plan_file = os.path.join(plans_dir, f)
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
    print(f'BLOCKED: Dispatch guard failed for {target_agent}:', file=sys.stderr)
    for i, e in enumerate(errors, 1):
        print(f'  {i}. {e}', file=sys.stderr)
    sys.exit(2)

sys.exit(0)
"
