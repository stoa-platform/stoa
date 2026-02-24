#!/bin/bash
# watch-collect.sh — Collect competitive signals into JSONL (append-only)
# Usage: bash scripts/ai-ops/watch-collect.sh
# Schedule: 2x/day via cron or launchd (see CRON-SETUP.md)
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/../.." && pwd)")"
WATCH_DIR="${REPO_ROOT}/.claude/watch"
mkdir -p "$WATCH_DIR"

# ISO week file: signals-YYYY-WNN.jsonl
ISO_WEEK="$(date +%G-W%V)"
SIGNALS_FILE="${WATCH_DIR}/signals-${ISO_WEEK}.jsonl"

# Ensure file exists
[ -f "$SIGNALS_FILE" ] || touch "$SIGNALS_FILE"

echo "Collecting signals into ${SIGNALS_FILE}..."

# Temp dir for raw fetches
TMPDIR_COLLECT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_COLLECT"' EXIT

# ── Fetch all sources in sequence (curl handles SSL on macOS) ────
echo ""
echo "1/6 Claude Code npm version..."
curl -sL --max-time 15 "https://registry.npmjs.org/@anthropic-ai/claude-code/latest" \
  > "$TMPDIR_COLLECT/npm.json" 2>/dev/null || echo "{}" > "$TMPDIR_COLLECT/npm.json"

echo "2/6 Anthropic blog..."
curl -sL --max-time 15 "https://www.anthropic.com/news" \
  > "$TMPDIR_COLLECT/anthropic.html" 2>/dev/null || echo "" > "$TMPDIR_COLLECT/anthropic.html"

echo "3/6 Reddit r/ClaudeAI..."
curl -s --max-time 15 -H "User-Agent: stoa-ai-factory/1.0" \
  "https://www.reddit.com/r/ClaudeAI/top/.json?t=week&limit=10" \
  > "$TMPDIR_COLLECT/reddit.json" 2>/dev/null || echo "{}" > "$TMPDIR_COLLECT/reddit.json"

echo "4/6 Hacker News..."
curl -s --max-time 15 \
  "https://hn.algolia.com/api/v1/search_by_date?query=%22claude+code%22&tags=story&hitsPerPage=10" \
  > "$TMPDIR_COLLECT/hn.json" 2>/dev/null || echo "{}" > "$TMPDIR_COLLECT/hn.json"

echo "5/6 Cursor changelog..."
curl -sL --max-time 15 "https://cursor.com/changelog" \
  > "$TMPDIR_COLLECT/cursor.html" 2>/dev/null || echo "" > "$TMPDIR_COLLECT/cursor.html"

echo "6/6 Aider changelog..."
curl -sL --max-time 15 "https://aider.chat/HISTORY.html" \
  > "$TMPDIR_COLLECT/aider.html" 2>/dev/null || echo "" > "$TMPDIR_COLLECT/aider.html"

# ── Parse all sources + dedup + append via single python3 run ────
echo ""
echo "Processing signals..."

python3 - "$SIGNALS_FILE" "$TMPDIR_COLLECT" << 'PYEOF'
import json
import os
import re
import sys
from datetime import datetime, timezone

signals_file = sys.argv[1]
tmpdir = sys.argv[2]

# Load existing dedup keys
existing_keys = set()
with open(signals_file, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            sig = json.loads(line)
            k = sig.get("source", "") + "::" + sig.get("title", "").strip().lower()
            existing_keys.add(k)
        except json.JSONDecodeError:
            continue

collected = 0
skipped = 0
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

def append_signal(source, title, url, score=0, meta=None):
    global collected, skipped
    title = title.strip()
    if not title or len(title) < 4:
        return
    key = source + "::" + title.lower()
    if key in existing_keys:
        skipped += 1
        return
    existing_keys.add(key)
    signal = {
        "ts": now,
        "source": source,
        "title": title[:120],
        "url": url.strip(),
        "score": score,
        "meta": meta or {},
    }
    with open(signals_file, "a") as f:
        f.write(json.dumps(signal, ensure_ascii=False) + "\n")
    collected += 1

def read_file(name):
    path = os.path.join(tmpdir, name)
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""

# 1. npm
try:
    data = json.loads(read_file("npm.json"))
    version = data.get("version", "")
    if version:
        append_signal("npm", f"Claude Code v{version}",
                       "https://www.npmjs.com/package/@anthropic-ai/claude-code",
                       0, {"version": version})
        print(f"  npm: v{version}")
except (json.JSONDecodeError, KeyError):
    print("  npm: parse failed")

# 2. Anthropic blog
html = read_file("anthropic.html")
titles = re.findall(r"<h[23][^>]*>([^<]+)", html)
count = 0
for t in titles[:5]:
    t = t.strip()
    if t and len(t) > 5:
        append_signal("anthropic", t, "https://www.anthropic.com/news")
        count += 1
print(f"  anthropic: {count} signals")

# 3. Reddit
try:
    data = json.loads(read_file("reddit.json"))
    count = 0
    for post in data.get("data", {}).get("children", [])[:10]:
        d = post.get("data", {})
        title = d.get("title", "")
        permalink = d.get("permalink", "")
        score = d.get("score", 0)
        if title:
            append_signal("reddit", title, "https://reddit.com" + permalink, score)
            count += 1
    print(f"  reddit: {count} signals")
except (json.JSONDecodeError, KeyError):
    print("  reddit: parse failed")

# 4. HN
try:
    data = json.loads(read_file("hn.json"))
    count = 0
    for hit in data.get("hits", [])[:10]:
        title = hit.get("title", "")
        url = hit.get("url") or ("https://news.ycombinator.com/item?id=" + str(hit.get("objectID", "")))
        score = hit.get("points") or 0
        if title:
            append_signal("hn", title, url, score)
            count += 1
    print(f"  hn: {count} signals")
except (json.JSONDecodeError, KeyError):
    print("  hn: parse failed")

# 5. Cursor
html = read_file("cursor.html")
titles = re.findall(r"<h[23][^>]*>([^<]+)", html)
count = 0
for t in titles[:5]:
    t = t.strip()
    if t and len(t) > 3:
        append_signal("cursor", t, "https://cursor.com/changelog")
        count += 1
print(f"  cursor: {count} signals")

# 6. Aider
html = read_file("aider.html")
titles = re.findall(r"<h[23][^>]*>([^<]+)", html)
count = 0
for t in titles[:3]:
    t = t.strip()
    if t and len(t) > 3:
        append_signal("aider", t, "https://aider.chat/HISTORY.html")
        count += 1
print(f"  aider: {count} signals")

# Summary
total = 0
with open(signals_file, "r") as f:
    total = sum(1 for line in f if line.strip())

print()
print(f"New: {collected} | Skipped (dedup): {skipped} | Total in file: {total}")
PYEOF

echo ""
echo "File: ${SIGNALS_FILE}"
echo "Run watch-digest.sh to generate the weekly digest."
