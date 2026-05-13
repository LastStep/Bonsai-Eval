#!/usr/bin/env bash
# Session Start — Tech Lead Agent
# Injects required context at the start of every session.

ROOT="${1:-.}"
WORKSPACE="${ROOT}/station/"
DOCS="${ROOT}/station/"

# ── Core identity ───────────────────────────────────────────────────────────

if [[ -f "${WORKSPACE}agent/Core/identity.md" ]]; then
  echo "=== CORE: identity.md ==="
  cat "${WORKSPACE}agent/Core/identity.md"
fi

if [[ -f "${WORKSPACE}agent/Core/memory.md" ]]; then
  echo ""
  echo "=== CORE: memory.md ==="
  cat "${WORKSPACE}agent/Core/memory.md"
fi

if [[ -f "${WORKSPACE}agent/Core/self-awareness.md" ]]; then
  echo ""
  echo "=== CORE: self-awareness.md ==="
  cat "${WORKSPACE}agent/Core/self-awareness.md"
fi

# ── Project status ──────────────────────────────────────────────────────────

if [[ -n "$DOCS" ]]; then
  if [[ -f "${DOCS}INDEX.md" ]]; then
    echo ""
    echo "=== INDEX.md ==="
    cat "${DOCS}INDEX.md"
  fi

  if [[ -f "${DOCS}Playbook/Status.md" ]]; then
    echo ""
    echo "=== Playbook/Status.md ==="
    cat "${DOCS}Playbook/Status.md"
  fi

  # FieldNotes: skip dump when file is effectively empty (only header/separators).
  # Effectively empty = 1 or fewer non-blank, non-header-marker, non-frontmatter lines
  # after removing the top YAML frontmatter block and markdown headings.
  if [[ -f "${DOCS}Logs/FieldNotes.md" ]]; then
    content_lines=$(awk '
      BEGIN { in_fm = 0; fm_done = 0 }
      NR == 1 && /^---[[:space:]]*$/ { in_fm = 1; next }
      in_fm && /^---[[:space:]]*$/ { in_fm = 0; fm_done = 1; next }
      in_fm { next }
      /^[[:space:]]*$/ { next }
      /^#/ { next }
      /^---[[:space:]]*$/ { next }
      /^>/ { next }
      { count++ }
      END { print count + 0 }
    ' "${DOCS}Logs/FieldNotes.md")
    if [[ "$content_lines" -gt 1 ]]; then
      echo ""
      echo "=== Logs/FieldNotes.md ==="
      cat "${DOCS}Logs/FieldNotes.md"
    fi
  fi

  # Pending reports: summarize (name + description) instead of full cat.
  if [[ -d "${DOCS}Reports/Pending/" ]] && [ -n "$(ls -A "${DOCS}Reports/Pending/" 2>/dev/null)" ]; then
    echo ""
    echo "=== Reports/Pending/ ==="
    for f in "${DOCS}Reports/Pending/"*; do
      [[ -f "$f" ]] || continue
      echo ""
      echo "--- $(basename "$f") ---"
      # Try to extract description from YAML frontmatter first
      desc=$(awk '
        BEGIN { in_fm = 0 }
        NR == 1 && /^---[[:space:]]*$/ { in_fm = 1; next }
        in_fm && /^---[[:space:]]*$/ { exit }
        in_fm && /^description:/ {
          sub(/^description:[[:space:]]*/, "")
          print
          exit
        }
      ' "$f")
      if [[ -n "$desc" ]]; then
        echo "$desc"
      else
        # Fallback: first non-empty, non-separator line
        awk '
          /^---[[:space:]]*$/ { next }
          /^[[:space:]]*$/ { next }
          { print; exit }
        ' "$f"
      fi
    done
  fi
fi

# ── Protocols ───────────────────────────────────────────────────────────────

if [[ -f "${WORKSPACE}agent/Protocols/security.md" ]]; then
  echo ""
  echo "=== PROTOCOL: security.md ==="
  cat "${WORKSPACE}agent/Protocols/security.md"
fi

if [[ -f "${WORKSPACE}agent/Protocols/scope-boundaries.md" ]]; then
  echo ""
  echo "=== PROTOCOL: scope-boundaries.md ==="
  cat "${WORKSPACE}agent/Protocols/scope-boundaries.md"
fi


# ── Health checks ───────────────────────────────────────────────────────────

echo ""
echo "=== SESSION HEALTH CHECK ==="

today=$(date +%Y-%m-%d)

# Check memory staleness
if [[ -f "${WORKSPACE}agent/Core/memory.md" ]]; then
  last_mod=$(stat -c %Y "${WORKSPACE}agent/Core/memory.md" 2>/dev/null || stat -f %m "${WORKSPACE}agent/Core/memory.md" 2>/dev/null)
  now=$(date +%s)
  days_stale=$(( (now - last_mod) / 86400 ))
  if [[ $days_stale -ge 2 ]]; then
    echo "WARNING: memory.md last updated $days_stale days ago — review and update work state"
  fi
fi

# Backlog P0 check
if [[ -n "$DOCS" ]] && [[ -f "${DOCS}Playbook/Backlog.md" ]]; then
  p0_items=$(sed -n '/^## P0/,/^## P[1-3]/p' "${DOCS}Playbook/Backlog.md" | grep -c '^- ' || true)
  if [[ $p0_items -gt 0 ]]; then
    echo "WARNING: $p0_items P0 (critical) item(s) in Playbook/Backlog.md — escalate to Status.md if not already there"
    sed -n '/^## P0/,/^## P[1-3]/p' "${DOCS}Playbook/Backlog.md" | grep '^- '
  fi
fi

# Pending reports count
if [[ -n "$DOCS" ]] && [[ -d "${DOCS}Reports/Pending/" ]]; then
  pending_count=$(ls -1 "${DOCS}Reports/Pending/" 2>/dev/null | wc -l)
  if [[ $pending_count -gt 0 ]]; then
    echo "WARNING: $pending_count pending report(s) in Reports/Pending/ — process before starting new work"
  fi
fi

# Log freshness check
if [[ -n "$DOCS" ]] && [[ -d "${DOCS}Logs/" ]]; then
  yesterday=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null)
  has_recent_log=false
  [[ -f "${DOCS}Logs/${today}.md" ]] && has_recent_log=true
  [[ -f "${DOCS}Logs/${yesterday}.md" ]] && has_recent_log=true
  if [[ "$has_recent_log" == "false" ]]; then
    latest_log=$(ls -1 "${DOCS}Logs/"20*.md 2>/dev/null | sort -r | head -1)
    if [[ -n "$latest_log" ]]; then
      echo "WARNING: Last session log is $(basename "$latest_log") — no log for yesterday or today"
    fi
  fi
fi
