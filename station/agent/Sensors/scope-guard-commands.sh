#!/usr/bin/env bash
# Scope Guard — Commands
# Blocks Tech Lead Agent from running execution commands.
# Exit 2 = block the tool call.

input=$(cat)

echo "$input" | python3 -c "
import sys, json, re

data = json.load(sys.stdin)
command = data.get('tool_input', {}).get('command', '')

if not command:
    sys.exit(0)

# Each pattern matches at command position: start of string, or after ; && || |
prefix = r'(?:^|(?<=&&)|(?<=\|\|)|(?<=;)|(?<=\|))\s*'

forbidden = [
    (prefix + r'pytest\b',                'pytest'),
    (prefix + r'python3?\s+-m\s+pytest',   'python -m pytest'),
    (prefix + r'npm\s+(run|test|start|install|ci)\b', 'npm'),
    (prefix + r'npx\b',                   'npx'),
    (prefix + r'uvicorn\b',               'uvicorn'),
    (prefix + r'tsc\b',                   'tsc'),
    (prefix + r'pip3?\s+(install|uninstall)\b', 'pip install/uninstall'),
    (prefix + r'ruff\b',                  'ruff'),
    (prefix + r'black\b',                 'black'),
    (prefix + r'mypy\b',                  'mypy'),
    (prefix + r'node\s',                  'node'),
]

for pattern, label in forbidden:
    if re.search(pattern, command):
        print(f'BLOCKED: Tech Lead Agent cannot run \"{label}\". Dispatch to a code agent instead.')
        sys.exit(2)

sys.exit(0)
"
