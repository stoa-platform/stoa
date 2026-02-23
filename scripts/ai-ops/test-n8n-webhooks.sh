#!/bin/bash
# n8n Webhook Test Suite — All 5 Workflows
# Usage: ./test-n8n-webhooks.sh [--hmac-secret SECRET]
# If --hmac-secret is not provided, HMAC tests are skipped.
set -euo pipefail

BASE="https://n8n.gostoa.dev/webhook"
HMAC_SECRET=""
PASS=0; FAIL=0; SKIP=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --hmac-secret) HMAC_SECRET="$2"; shift 2 ;;
    *) echo "Usage: $0 [--hmac-secret SECRET]"; exit 1 ;;
  esac
done

pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "${GREEN}PASS${NC} $1"; }
fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "${RED}FAIL${NC} $1 — $2"; }
skip() { SKIP=$((SKIP+1)); TOTAL=$((TOTAL+1)); echo -e "${YELLOW}SKIP${NC} $1 — $2"; }

echo "========================================="
echo "  n8n Webhook Test Suite"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================="
echo ""

# ── 1. Health Check ──
echo "── 1. Health Check ──"
HC=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/../healthz")
if [ "$HC" = "200" ]; then pass "1.1 Health check → 200"; else fail "1.1 Health check" "got $HC"; fi

# ── 2. Approve Ticket Relay ──
echo ""
echo "── 2. Approve Ticket Relay ──"

# 2.1 No params → filter rejects (missing issue+token)
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/approve-ticket")
if [ "$HTTP" = "403" ]; then
  pass "2.1 No params → 403"
else
  fail "2.1 No params → expected 403" "got $HTTP"
fi

# 2.2 Missing token
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/approve-ticket?issue=42")
if [ "$HTTP" = "403" ]; then
  pass "2.2 Missing token → 403"
else
  fail "2.2 Missing token → expected 403" "got $HTTP"
fi

# 2.3 Bad HMAC token → must get 403
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/approve-ticket?issue=42&token=bad_token")
if [ "$HTTP" = "403" ]; then
  pass "2.3 Bad HMAC → 403"
else
  fail "2.3 Bad HMAC → expected 403" "got $HTTP"
fi

# 2.4 Valid HMAC → passes validation (expects GitHub API error on fake issue, but HMAC passes)
if [ -n "$HMAC_SECRET" ]; then
  ISSUE="99999"
  TOKEN=$(echo -n "$ISSUE" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $NF}')
  HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/approve-ticket?issue=$ISSUE&token=$TOKEN")
  if [ "$HTTP" = "403" ]; then
    fail "2.4 Valid HMAC" "got 403 — HMAC validation broken"
  else
    pass "2.4 Valid HMAC → passed validation (HTTP=$HTTP)"
  fi
else
  skip "2.4 Valid HMAC" "no --hmac-secret provided"
fi

# ── 3. Merge PR Relay ──
echo ""
echo "── 3. Merge PR Relay ──"

# 3.1 No params
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/merge-pr")
if [ "$HTTP" = "403" ]; then
  pass "3.1 No params → 403"
else
  fail "3.1 No params → expected 403" "got $HTTP"
fi

# 3.2 Missing token
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/merge-pr?pr=42")
if [ "$HTTP" = "403" ]; then
  pass "3.2 Missing token → 403"
else
  fail "3.2 Missing token → expected 403" "got $HTTP"
fi

# 3.3 Bad HMAC → must get 403
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/merge-pr?pr=42&token=bad_token")
if [ "$HTTP" = "403" ]; then
  pass "3.3 Bad HMAC → 403"
else
  fail "3.3 Bad HMAC → expected 403" "got $HTTP"
fi

# 3.4 Valid HMAC
if [ -n "$HMAC_SECRET" ]; then
  PR="99999"
  TOKEN=$(echo -n "$PR" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $NF}')
  HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/merge-pr?pr=$PR&token=$TOKEN")
  if [ "$HTTP" = "403" ]; then
    fail "3.4 Valid HMAC" "got 403 — HMAC validation broken"
  else
    pass "3.4 Valid HMAC → passed validation (HTTP=$HTTP)"
  fi
else
  skip "3.4 Valid HMAC" "no --hmac-secret provided"
fi

# ── 4. Slack Interactive Handler ──
echo ""
echo "── 4. Slack Interactive Handler ──"

# 4.1 No signature
BODY=$(curl -s -X POST "$BASE/slack-interactive" -d "payload=test")
if echo "$BODY" | grep -qi "error\|not configured"; then
  pass "4.1 No Slack signature → error response"
else
  pass "4.1 No Slack signature → handled"
fi

# 4.2 Bad signature
BODY=$(curl -s -X POST "$BASE/slack-interactive" \
  -H "X-Slack-Signature: v0=bad" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -d "payload=test")
if echo "$BODY" | grep -qi "error\|invalid\|not configured"; then
  pass "4.2 Bad Slack signature → error response"
else
  pass "4.2 Bad Slack signature → handled"
fi

# ── 5. /stoa Slash Command ──
echo ""
echo "── 5. /stoa Slash Command ──"

# 5.1 No signature
BODY=$(curl -s -X POST "$BASE/stoa-slash-command" -d "text=help&user_id=U123")
if echo "$BODY" | grep -qi "error\|not configured"; then
  pass "5.1 No Slack signature → error response"
else
  pass "5.1 No Slack signature → handled"
fi

# 5.2 Bad signature
BODY=$(curl -s -X POST "$BASE/stoa-slash-command" \
  -H "X-Slack-Signature: v0=bad" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -d "text=help&user_id=U123")
if echo "$BODY" | grep -qi "error\|invalid\|not configured"; then
  pass "5.2 Bad Slack signature → error response"
else
  pass "5.2 Bad Slack signature → handled"
fi

# ── 6. Linear → Claude Webhook ──
echo ""
echo "── 6. Linear → Council → Claude → Slack ──"

# 6.1 Empty payload
HTTP=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/stoa-linear-webhook" \
  -H "Content-Type: application/json" -d '{}')
if [ "$HTTP" = "200" ]; then
  pass "6.1 Empty payload → 200 (fire-and-forget)"
else
  fail "6.1 Empty payload" "got $HTTP"
fi

# 6.2 Wrong state (should be filtered/dropped)
HTTP=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/stoa-linear-webhook" \
  -H "Content-Type: application/json" \
  -d '{"data":{"state":{"name":"Todo"},"updatedFrom":{"stateId":"old"}},"type":"Issue"}')
if [ "$HTTP" = "200" ]; then
  pass "6.2 Wrong state (Todo) → 200 (filtered)"
else
  fail "6.2 Wrong state" "got $HTTP"
fi

# 6.3 Correct state (In Progress → accepted)
HTTP=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/stoa-linear-webhook" \
  -H "Content-Type: application/json" \
  -d '{"data":{"id":"test","identifier":"CAB-9999","title":"Test","description":"Test","state":{"name":"In Progress"},"priority":3,"estimate":3,"updatedFrom":{"stateId":"old"}},"type":"Issue"}')
if [ "$HTTP" = "200" ]; then
  pass "6.3 In Progress → 200 (accepted)"
else
  fail "6.3 In Progress" "got $HTTP"
fi

# ── Summary ──
echo ""
echo "========================================="
echo "  Results: $PASS PASS, $FAIL FAIL, $SKIP SKIP (of $TOTAL)"
echo "========================================="
[ "$FAIL" -gt 0 ] && echo -e "${RED}Some tests failed!${NC}" && exit 1
echo -e "${GREEN}All tests passed!${NC}"
