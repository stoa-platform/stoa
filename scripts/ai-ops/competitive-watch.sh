#!/bin/bash
# Veille concurrentielle manuelle — lance depuis Claude Code
# Usage: bash scripts/ai-ops/competitive-watch.sh
set -euo pipefail

echo "🔭 Veille IA Factory — $(date '+%Y-%m-%d')"
echo "════════════════════════════════════════"

echo ""
echo "📦 Claude Code version locale:"
claude --version 2>/dev/null || echo "  Claude Code non trouve"

echo ""
echo "📦 Derniere version npm:"
npm view @anthropic-ai/claude-code version 2>/dev/null || echo "  npm check failed"

echo ""
echo "📢 Anthropic blog (derniers posts):"
curl -sL --max-time 10 "https://www.anthropic.com/news" 2>/dev/null \
  | grep -oP '<h[23][^>]*>[^<]+' \
  | head -5 \
  | sed 's/<[^>]*>//g; s/^/  /' \
  || echo "  Fetch failed"

echo ""
echo "💬 Reddit r/ClaudeAI (top semaine):"
curl -s --max-time 10 -H "User-Agent: stoa-ai-factory/1.0" \
  "https://www.reddit.com/r/ClaudeAI/top/.json?t=week&limit=5" 2>/dev/null \
  | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for post in data['data']['children'][:5]:
        d = post['data']
        print(f\"  [{d['score']}↑] {d['title'][:80]}\")
except Exception:
    print('  Fetch failed')
" 2>/dev/null || echo "  Fetch failed"

echo ""
echo "🔶 Hacker News (Claude Code mentions):"
curl -s --max-time 10 \
  "https://hn.algolia.com/api/v1/search_by_date?query=%22claude+code%22&tags=story&hitsPerPage=5" 2>/dev/null \
  | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for hit in data['hits'][:5]:
        print(f\"  [{hit.get('points',0)}↑] {hit['title'][:80]}\")
except Exception:
    print('  Fetch failed')
" 2>/dev/null || echo "  Fetch failed"

echo ""
echo "⚔️ Cursor changelog:"
curl -sL --max-time 10 "https://cursor.com/changelog" 2>/dev/null \
  | grep -oP '<h[23][^>]*>[^<]+' \
  | head -3 \
  | sed 's/<[^>]*>//g; s/^/  /' \
  || echo "  Fetch failed"

echo ""
echo "📊 Score IA Factory actuel:"
SCORE_FILE="$(git rev-parse --show-toplevel 2>/dev/null)/.claude/audit-score.txt"
if [ -f "$SCORE_FILE" ]; then
  echo "  $(cat "$SCORE_FILE")/100 (fichier: .claude/audit-score.txt)"
else
  echo "  Score non disponible (lancer l'audit mensuel)"
fi

echo ""
echo "Fin de veille. Pour un digest complet, utiliser le workflow n8n."
