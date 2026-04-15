#!/bin/bash
# Empêche la recréation de .claude/rules/
if [ -d ".claude/rules" ]; then
  count=$(find .claude/rules -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$count" -gt 0 ]; then
    echo "❌ .claude/rules/ contient $count fichiers .md"
    echo "   Interdit. Utiliser CLAUDE.md par service ou .claude/docs/"
    echo "   Voir ADR: suppression rules/ du $(date +%Y-%m-%d)"
    exit 1
  fi
fi
