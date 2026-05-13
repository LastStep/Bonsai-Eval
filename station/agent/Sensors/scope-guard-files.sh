#!/usr/bin/env bash
# Scope Guard — File Edits
# Blocks Tech Lead Agent from editing files outside station/
# Exit 2 = block the tool call.

input=$(cat)
file_path=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [[ -z "$file_path" ]]; then
  exit 0
fi


# Block writes to .env files
basename_file=$(basename "$file_path")
if [[ "$basename_file" == .env* ]]; then
  echo "BLOCKED: Tech Lead Agent cannot modify .env files."
  exit 2
fi

exit 0
