#!/bin/bash
# Enforce CLAUDE.md size budget: ≤ 250 lignes par fichier.
# Hard fail en CI. Kill-switch: DISABLE_CLAUDE_MD_BUDGET=1.
set -euo pipefail

[ "${DISABLE_CLAUDE_MD_BUDGET:-0}" = "1" ] && { echo "budget lint bypassed"; exit 0; }

MAX=250
fail=0

while IFS= read -r f; do
  lines=$(wc -l < "$f")
  if [ "$lines" -gt "$MAX" ]; then
    echo "❌ $f: $lines lignes (max $MAX)"
    fail=1
  else
    echo "✅ $f: $lines"
  fi
done < <(find . -name "CLAUDE.md" -not -path "./.git/*" -not -path "./node_modules/*" -not -path "./.claude/rules-backup*")

if [ "$fail" -eq 1 ]; then
  echo ""
  echo "Un ou plusieurs CLAUDE.md dépassent $MAX lignes."
  echo "Règle: décisions GO/NOGO → CLAUDE.md. Protocoles/détails → .claude/docs/."
  exit 1
fi
