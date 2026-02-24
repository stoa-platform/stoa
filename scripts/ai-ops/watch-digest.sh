#!/bin/bash
# watch-digest.sh — Generate weekly digest from accumulated JSONL signals
# Usage: bash scripts/ai-ops/watch-digest.sh [YYYY-WNN]
# Schedule: Monday 08:00 CET via cron or launchd (see CRON-SETUP.md)
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/../.." && pwd)")"
WATCH_DIR="${REPO_ROOT}/.claude/watch"
export SCORE_FILE="${REPO_ROOT}/.claude/audit-score.txt"

# Accept week override or use current ISO week
export ISO_WEEK="${1:-$(date +%G-W%V)}"
export SIGNALS_FILE="${WATCH_DIR}/signals-${ISO_WEEK}.jsonl"

if [ ! -f "$SIGNALS_FILE" ]; then
  echo "No signals file for week ${ISO_WEEK}."
  echo "Expected: ${SIGNALS_FILE}"
  echo "Run watch-collect.sh first to collect signals."
  exit 1
fi

TOTAL=$(wc -l < "$SIGNALS_FILE" | tr -d ' ')
if [ "$TOTAL" -eq 0 ]; then
  echo "Signals file is empty for week ${ISO_WEEK}. Nothing to digest."
  exit 0
fi

# ── Generate digest via python3 ──────────────────────────────────────
python3 << 'PYEOF'
import json
import sys
import os
from collections import defaultdict

signals_file = os.environ["SIGNALS_FILE"]
score_file = os.environ.get("SCORE_FILE", "")
iso_week = os.environ["ISO_WEEK"]

# Read and deduplicate signals
seen = set()
signals = []
with open(signals_file, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            sig = json.loads(line)
            key = sig["source"] + "::" + sig["title"].strip().lower()
            if key not in seen:
                seen.add(key)
                signals.append(sig)
        except (json.JSONDecodeError, KeyError):
            continue

# Group by source
by_source = defaultdict(list)
for s in signals:
    by_source[s["source"]].append(s)

# Sort each group by score (descending)
for src in by_source:
    by_source[src].sort(key=lambda x: x.get("score", 0), reverse=True)

# Read audit score
audit_score = "N/A"
if score_file and os.path.exists(score_file):
    with open(score_file, "r") as f:
        audit_score = f.read().strip() + "/100"

# ── Format digest ────────────────────────────────────────────────────
print(f":telescope: VEILLE IA FACTORY — Semaine {iso_week}")
print(f"Signals: {len(signals)} uniques (apres dedup)")
print()

# BREAKING: high-score items from any source
breaking = [s for s in signals if s.get("score", 0) >= 200]
if breaking:
    print(":loudspeaker: BREAKING (action requise)")
    for s in breaking[:3]:
        print(f"  - [{s['source']}] {s['title']}")
        if s.get("url"):
            print(f"    {s['url']}")
    print()

# NOUVEAUTES: anthropic + npm
nouveautes = by_source.get("anthropic", []) + by_source.get("npm", [])
if nouveautes:
    print(":new: NOUVEAUTES")
    for s in nouveautes[:5]:
        label = s["source"].upper()
        print(f"  - [{label}] {s['title']}")
    print()

# CONCURRENCE: cursor + aider + codex
concurrence = by_source.get("cursor", []) + by_source.get("aider", []) + by_source.get("codex", [])
if concurrence:
    print(":crossed_swords: CONCURRENCE")
    for s in concurrence[:5]:
        label = s["source"].capitalize()
        print(f"  - [{label}] {s['title']}")
    print()

# COMMUNAUTE: reddit + hn (top by score)
communaute = sorted(
    by_source.get("reddit", []) + by_source.get("hn", []),
    key=lambda x: x.get("score", 0),
    reverse=True,
)
if communaute:
    print(":speech_balloon: COMMUNAUTE (top signaux)")
    for s in communaute[:7]:
        src = "Reddit" if s["source"] == "reddit" else "HN"
        score = s.get("score", 0)
        print(f"  - [{src} {score}pts] {s['title'][:90]}")
    print()

# SCORE
print(f":bar_chart: NOTRE SCORE")
print(f"  Setup actuel: {audit_score} (fichier: .claude/audit-score.txt)")
print()

# SOURCE STATS
print(":clipboard: SOURCES")
for src in sorted(by_source.keys()):
    count = len(by_source[src])
    print(f"  - {src}: {count} signal{'s' if count > 1 else ''}")
print()

# PATTERNS: signals mentioning specific keywords
pattern_keywords = ["mcp", "agent", "hook", "worktree", "skill", "subagent", "team"]
patterns = [
    s for s in signals
    if any(kw in s.get("title", "").lower() for kw in pattern_keywords)
]
if patterns:
    print(":bulb: PATTERNS A TESTER")
    for s in patterns[:5]:
        print(f"  - [{s['source']}] {s['title'][:90]}")
    print()

print(":dart: ACTION ITEMS")
if breaking:
    for s in breaking[:3]:
        print(f"  - [ ] Evaluer impact: {s['title'][:60]}")
else:
    print("  - Aucune action urgente cette semaine")
print()

print(f"--- Fin digest {iso_week} ({len(signals)} signaux) ---")
PYEOF

# ── Optional: post to Slack ──────────────────────────────────────────
if [ -n "${SLACK_WEBHOOK:-}" ]; then
  echo ""
  echo "Posting digest to Slack..."
  DIGEST=$(SIGNALS_FILE="$SIGNALS_FILE" SCORE_FILE="$SCORE_FILE" ISO_WEEK="$ISO_WEEK" python3 << 'PYSLACK'
import json, os
from collections import defaultdict

signals_file = os.environ["SIGNALS_FILE"]
iso_week = os.environ["ISO_WEEK"]

seen = set()
signals = []
with open(signals_file, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            sig = json.loads(line)
            key = sig["source"] + "::" + sig["title"].strip().lower()
            if key not in seen:
                seen.add(key)
                signals.append(sig)
        except (json.JSONDecodeError, KeyError):
            continue

by_source = defaultdict(list)
for s in signals:
    by_source[s["source"]].append(s)

lines = [f":telescope: *VEILLE IA FACTORY — {iso_week}* ({len(signals)} signaux)"]
lines.append("")

top = sorted(signals, key=lambda x: x.get("score", 0), reverse=True)[:5]
if top:
    lines.append(":fire: *Top signaux*")
    for s in top:
        src = s["source"].upper()
        score = s.get("score", 0)
        lines.append(f"  [{src} {score}pts] {s['title'][:80]}")
    lines.append("")

sources = ", ".join(f"{k}:{len(v)}" for k, v in sorted(by_source.items()))
lines.append(f":clipboard: Sources: {sources}")

print(json.dumps({"text": "\n".join(lines)}))
PYSLACK
  )
  curl -s -X POST -H "Content-Type: application/json" -d "$DIGEST" "${SLACK_WEBHOOK}" >/dev/null 2>&1 && echo "  Slack: sent" || echo "  Slack: failed (non-blocking)"
fi
