#!/bin/bash
# OpSec scanner — blocks commits/pushes containing sensitive content
# Called by pre-push-quality-gate.sh or standalone.
#
# Scans staged diff (or arbitrary diff) for:
#   1. STOA infrastructure IPs (OVH, Contabo, Hetzner ranges)
#   2. Financial data (EUR amounts, pricing, rates)
#   3. Client references (banque, specific client names)
#   4. Hardcoded passwords with defaults
#   5. SSH key filenames + user@IP patterns
#
# Usage:
#   ./scripts/opsec-scan.sh                    # Scan origin/main..HEAD
#   ./scripts/opsec-scan.sh --diff <range>     # Scan arbitrary diff range
#   ./scripts/opsec-scan.sh --staged           # Scan staged changes only
#
# Exit codes:
#   0 = clean
#   1 = findings (blocks push)
#
# Kill switch: DISABLE_OPSEC_SCAN=1

set -euo pipefail

[ "${DISABLE_OPSEC_SCAN:-}" = "1" ] && exit 0

# --- Parse args ---
DIFF_MODE="branch"
DIFF_RANGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --diff) DIFF_RANGE="$2"; DIFF_MODE="range"; shift 2 ;;
    --staged) DIFF_MODE="staged"; shift ;;
    *) shift ;;
  esac
done

# --- Get diff content ---
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT"

case "$DIFF_MODE" in
  staged)
    DIFF_CONTENT=$(git diff --cached --unified=0 2>/dev/null || echo "")
    ;;
  range)
    DIFF_CONTENT=$(git diff "$DIFF_RANGE" --unified=0 2>/dev/null || echo "")
    ;;
  branch)
    MERGE_BASE=$(git merge-base HEAD origin/main 2>/dev/null || echo "HEAD~1")
    DIFF_CONTENT=$(git diff "$MERGE_BASE"...HEAD --unified=0 2>/dev/null || echo "")
    ;;
esac

# Filter out self-referencing files (config files that contain the patterns as rules)
EXCLUDED_PATHS='.gitleaks.toml|scripts/opsec-scan.sh|\.claude/rules/|\.claude/hooks/'
DIFF_CONTENT=$(echo "$DIFF_CONTENT" | awk -v excl="$EXCLUDED_PATHS" '
  /^diff --git/ { skip=0; if (match($0, excl)) skip=1 }
  !skip { print }
')

# Only scan added lines (lines starting with +, not ++)
ADDED_LINES=$(echo "$DIFF_CONTENT" | grep '^+[^+]' | sed 's/^+//' || true)

[ -z "$ADDED_LINES" ] && exit 0

FINDINGS=0
FINDING_DETAILS=""

report() {
  FINDINGS=$((FINDINGS + 1))
  local severity="$1"
  local category="$2"
  local match="$3"
  FINDING_DETAILS="${FINDING_DETAILS}\n  ${severity} [${category}] ${match}"
}

# --- 1. Infrastructure IPs ---
# STOA VPS ranges — catches any IP in our known subnets
IP_PATTERNS=(
  '51\.83\.45\.[0-9]+'
  '51\.195\.43\.[0-9]+'
  '51\.255\.201\.[0-9]+'
  '51\.255\.193\.[0-9]+'
  '51\.254\.139\.[0-9]+'
  '54\.36\.209\.[0-9]+'
  '94\.23\.107\.[0-9]+'
  '135\.125\.204\.[0-9]+'
  '164\.68\.121\.[0-9]+'
  '144\.91\.73\.[0-9]+'
  '213\.199\.45\.[0-9]+'
  '91\.134\.108\.[0-9]+'
)

for pattern in "${IP_PATTERNS[@]}"; do
  matches=$(echo "$ADDED_LINES" | grep -oE "$pattern" 2>/dev/null | head -3 || true)
  if [ -n "$matches" ]; then
    while IFS= read -r m; do
      report "CRITICAL" "infra-ip" "$m"
    done <<< "$matches"
  fi
done

# --- 2. Financial data ---
# EUR amounts, hourly rates, billing
FINANCE_PATTERNS=(
  '[0-9]+\s*€/[hj]'                          # hourly/daily rates
  '[0-9]{1,3}[\. ][0-9]{3}\s*€'              # amounts > 999€
  '€\s*[0-9]{1,3}[\. ][0-9]{3}'              # €X,XXX
  'tarif.*[0-9]+€'                            # tarif + amount
  'facturation'                               # billing
  'chiffre\s*d.affaires'                      # revenue
)

for pattern in "${FINANCE_PATTERNS[@]}"; do
  matches=$(echo "$ADDED_LINES" | grep -iE "$pattern" 2>/dev/null | head -2 || true)
  if [ -n "$matches" ]; then
    while IFS= read -r m; do
      report "CRITICAL" "financial" "$(echo "$m" | head -c 80)"
    done <<< "$matches"
  fi
done

# --- 3. Client references ---
CLIENT_PATTERNS=(
  'banque\s+centrale'
  'mission\s+client.*banque'
  'prestation.*banque'
  'mission.*banque\s+centrale'
)

for pattern in "${CLIENT_PATTERNS[@]}"; do
  matches=$(echo "$ADDED_LINES" | grep -iE "$pattern" 2>/dev/null | head -2 || true)
  if [ -n "$matches" ]; then
    while IFS= read -r m; do
      report "CRITICAL" "client-ref" "$(echo "$m" | head -c 80)"
    done <<< "$matches"
  fi
done

# --- 4. Password defaults in shell ---
PASS_MATCHES=$(echo "$ADDED_LINES" | grep -iE '(PASSWORD|SECRET|TOKEN)[^=]*:-[A-Za-z0-9!@#$%^&*_-]{6,}' 2>/dev/null | head -3 || true)
if [ -n "$PASS_MATCHES" ]; then
  while IFS= read -r m; do
    report "HIGH" "password-default" "$(echo "$m" | head -c 80)"
  done <<< "$PASS_MATCHES"
fi

# --- 5. SSH patterns ---
SSH_MATCHES=$(echo "$ADDED_LINES" | grep -E 'ssh\s+-i.*@[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' 2>/dev/null | head -2 || true)
if [ -n "$SSH_MATCHES" ]; then
  while IFS= read -r m; do
    report "HIGH" "ssh-command" "$(echo "$m" | head -c 80)"
  done <<< "$SSH_MATCHES"
fi

# --- Result ---
if [ "$FINDINGS" -gt 0 ]; then
  echo ""
  echo "🔴 OpSec scan: $FINDINGS finding(s) — PUSH BLOCKED"
  echo ""
  echo -e "$FINDING_DETAILS"
  echo ""
  echo "Fix the findings above before pushing."
  echo "  - IPs: use env vars (\${VAR:?Set VAR})"
  echo "  - Passwords: remove defaults, use \${VAR:?Set VAR}"
  echo "  - Financial/client data: belongs in stoa-strategy (private)"
  echo ""
  echo "Kill switch: DISABLE_OPSEC_SCAN=1"
  exit 1
fi

exit 0
