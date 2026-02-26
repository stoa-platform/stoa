#!/bin/bash
# Analyze captured tool usage to generate progressive allowlist proposals.
#
# Usage: ./analyze-instance-usage.sh <role>
# Example: ./analyze-instance-usage.sh backend
#
# Reads .claude/instances/<role>-captured.jsonl and outputs:
# 1. Tool usage frequency
# 2. Path prefix frequency (top-level directory grouping)
# 3. Proposed allowlist (JSON format for human review)
set -euo pipefail

ROLE="${1:?Usage: analyze-instance-usage.sh <role>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CAPTURE_FILE="$PROJECT_DIR/.claude/instances/${ROLE}-captured.jsonl"

if [[ ! -f "$CAPTURE_FILE" ]]; then
  echo "No captures found for instance '$ROLE'"
  echo "File: $CAPTURE_FILE"
  exit 0
fi

TOTAL=$(wc -l < "$CAPTURE_FILE" | tr -d ' ')
echo "=== Instance: $ROLE ==="
echo "Captures: $TOTAL entries"
echo ""

python3 -c "
import json, sys, collections

tools = collections.Counter()
paths = collections.Counter()
edit_paths = collections.Counter()

for line in open('$CAPTURE_FILE'):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    tool = d.get('tool', '')
    tools[tool] += 1
    p = d.get('path', '')
    if p and tool in ('Edit', 'Write', 'Read'):
        parts = p.strip('/').split('/')
        if len(parts) >= 2:
            prefix = '/' + '/'.join(parts[:2]) + '/'
        elif parts:
            prefix = '/' + parts[0] + '/'
        else:
            prefix = '/'
        paths[prefix] += 1
        if tool in ('Edit', 'Write'):
            edit_paths[prefix] += 1

print('--- Tool Usage ---')
for t, c in tools.most_common(20):
    print(f'  {t}: {c}')

print()
print('--- Read/Write Path Prefixes ---')
for p, c in paths.most_common(20):
    print(f'  {p}: {c}')

if edit_paths:
    print()
    print('--- Edit/Write Only (potential allow paths) ---')
    for p, c in edit_paths.most_common(20):
        print(f'  {p}: {c}')

    # Generate proposed allowlist
    print()
    print('--- Proposed Allowlist (review before activating) ---')
    allow = []
    for p, c in edit_paths.most_common(20):
        if c >= 3:  # Only include paths used 3+ times
            allow.append(f'Edit({p}**)')
            allow.append(f'Write({p}**)')
    bash_cmds = collections.Counter()
    for line in open('$CAPTURE_FILE'):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get('tool') == 'Bash':
            cmd = d.get('path', '')
            if cmd:
                prefix = cmd.split()[0] if ' ' in cmd else cmd[:20]
                bash_cmds[prefix] += 1
    for cmd, c in bash_cmds.most_common(15):
        if c >= 3:
            allow.append(f'Bash({cmd}:*)')
    print(json.dumps({'permissions': {'allow': allow}}, indent=2))
"

echo ""
echo "To activate allowlist mode:"
echo "  export INSTANCE_MODE=allow"
echo "  # Then copy the proposed allowlist to .claude/instances/${ROLE}-allowlist.json"
