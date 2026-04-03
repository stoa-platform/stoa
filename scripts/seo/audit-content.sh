#!/usr/bin/env bash
# audit-content.sh — SEO content quality audit for stoa-docs blog
# Runs all 10 quality gates from .claude/rules/seo-content.md
#
# Usage:
#   ./scripts/seo/audit-content.sh <stoa-docs-path>
#   ./scripts/seo/audit-content.sh ../stoa-docs
#
# Checks:
#   1. Build clean (npm run build)
#   2. Front-matter complete (delegates to validate-blog-metadata.sh)
#   3. Word count met
#   4. Min 3 internal links per article
#   5. Hub link present (spoke → pillar)
#   6. Content compliance (no P0/P1 violations)
#   7. Last-verified tag on comparisons
#   8. Valid tags (from tags.yml)
#   9. No broken links (build output)
#   10. FAQ section present (recommended)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

error() { echo -e "  ${RED}FAIL${NC}: $1"; ((ERRORS++)); }
warn() { echo -e "  ${YELLOW}WARN${NC}: $1"; ((WARNINGS++)); }
ok() { echo -e "  ${GREEN}PASS${NC}: $1"; }
section() { echo -e "\n${BLUE}[$1]${NC}"; }

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <stoa-docs-path>"
  echo "  Runs full SEO quality audit on stoa-docs blog content."
  echo ""
  echo "Options:"
  echo "  --skip-build    Skip npm run build check (faster, offline)"
  echo ""
  echo "Example:"
  echo "  $0 ../stoa-docs"
  echo "  $0 ../stoa-docs --skip-build"
  exit 1
fi

DOCS_PATH="$1"
SKIP_BUILD=false
[[ "${2:-}" == "--skip-build" ]] && SKIP_BUILD=true

if [[ ! -d "$DOCS_PATH/blog" ]]; then
  echo -e "${RED}Error${NC}: '$DOCS_PATH/blog' not found. Is this a stoa-docs checkout?"
  exit 1
fi

BLOG_DIR="$DOCS_PATH/blog"
BLOG_COUNT=$(find "$BLOG_DIR" -name "*.md" -o -name "*.mdx" | wc -l | tr -d ' ')

echo "=== SEO Content Audit ==="
echo "Docs path: $DOCS_PATH"
echo "Blog articles: $BLOG_COUNT"

# --- Gate 1: Build clean ---
section "Gate 1: Build Clean"
if $SKIP_BUILD; then
  warn "Build check skipped (--skip-build)"
else
  if [[ -f "$DOCS_PATH/package.json" ]]; then
    BUILD_OUTPUT=$(cd "$DOCS_PATH" && npm run build 2>&1) || true
    BUILD_ERRORS=$(echo "$BUILD_OUTPUT" | grep -ciE "error|broken" || true)
    if ((BUILD_ERRORS > 0)); then
      error "Build has ${BUILD_ERRORS} error/broken reference(s)"
      echo "$BUILD_OUTPUT" | grep -iE "error|broken" | head -5 | sed 's/^/    /'
    else
      ok "Build clean"
    fi
  else
    warn "No package.json found — cannot run build"
  fi
fi

# --- Gate 2-8: Front-matter validation (delegated) ---
section "Gate 2-8: Front-matter & Metadata"
if [[ -x "$SCRIPT_DIR/validate-blog-metadata.sh" ]]; then
  VALIDATE_OUTPUT=$("$SCRIPT_DIR/validate-blog-metadata.sh" "$BLOG_DIR" 2>&1) || true
  VALIDATE_ERRORS=$(echo "$VALIDATE_OUTPUT" | grep -c "ERROR" || true)
  VALIDATE_WARNINGS=$(echo "$VALIDATE_OUTPUT" | grep -c "WARN" || true)
  if ((VALIDATE_ERRORS > 0)); then
    error "Metadata validation: ${VALIDATE_ERRORS} error(s)"
    echo "$VALIDATE_OUTPUT" | grep "ERROR" | head -10 | sed 's/^/    /'
  else
    ok "Metadata validation passed"
  fi
  if ((VALIDATE_WARNINGS > 0)); then
    warn "Metadata validation: ${VALIDATE_WARNINGS} warning(s)"
  fi
  ERRORS=$((ERRORS + VALIDATE_ERRORS))
  WARNINGS=$((WARNINGS + VALIDATE_WARNINGS))
else
  warn "validate-blog-metadata.sh not found or not executable — skipping"
fi

# --- Gate 6: Content compliance scan ---
section "Gate 6: Content Compliance"

# P0 checks: competitor pricing, client names, certification claims
P0_PATTERNS='(\$[0-9]+[kK]|\$[0-9]+,?[0-9]+/year|€[0-9]|EUR [0-9])'
P0_CERT='(STOA is (DORA|ISO|SOC|PCI|HIPAA|GDPR)[ -]compliant|certified (ISO|SOC|PCI))'

P0_PRICE_HITS=0
P0_CERT_HITS=0

for f in "$BLOG_DIR"/*.md "$BLOG_DIR"/*.mdx; do
  [[ -f "$f" ]] || continue
  if grep -qP "$P0_PATTERNS" "$f" 2>/dev/null; then
    error "P0 — Competitor pricing found in $(basename "$f")"
    grep -nP "$P0_PATTERNS" "$f" | head -3 | sed 's/^/    /'
    ((P0_PRICE_HITS++))
  fi
  if grep -qiP "$P0_CERT" "$f" 2>/dev/null; then
    error "P0 — Certification claim found in $(basename "$f")"
    grep -niP "$P0_CERT" "$f" | head -3 | sed 's/^/    /'
    ((P0_CERT_HITS++))
  fi
done

if ((P0_PRICE_HITS == 0 && P0_CERT_HITS == 0)); then
  ok "No P0 compliance violations"
fi

# P1 checks: comparisons without disclaimer
COMPARISON_FILES=0
DISCLAIMER_MISSING=0
for f in "$BLOG_DIR"/*.md "$BLOG_DIR"/*.mdx; do
  [[ -f "$f" ]] || continue
  if grep -q 'comparison' <(sed -n '/^---$/,/^---$/p' "$f" | grep 'tags:'); then
    ((COMPARISON_FILES++))
    if ! grep -qi 'Feature comparisons are based on\|trademarks belong to their respective' "$f"; then
      warn "P1 — Comparison '$(basename "$f")' missing disclaimer"
      ((DISCLAIMER_MISSING++))
    fi
  fi
done

if ((COMPARISON_FILES > 0 && DISCLAIMER_MISSING == 0)); then
  ok "All ${COMPARISON_FILES} comparison articles have disclaimers"
fi

# --- Gate 9: Broken links (from build output) ---
section "Gate 9: Broken Links"
if $SKIP_BUILD; then
  warn "Broken link check skipped (requires build)"
else
  BROKEN_LINKS=$(echo "${BUILD_OUTPUT:-}" | grep -ci "broken" || true)
  if ((BROKEN_LINKS > 0)); then
    error "${BROKEN_LINKS} broken link(s) detected in build"
  else
    ok "No broken links"
  fi
fi

# --- Gate 10: FAQ sections ---
section "Gate 10: FAQ Sections"
FAQ_COUNT=0
NO_FAQ_COUNT=0
for f in "$BLOG_DIR"/*.md "$BLOG_DIR"/*.mdx; do
  [[ -f "$f" ]] || continue
  if grep -qi '## FAQ\|## Frequently Asked\|## Common Questions' "$f"; then
    ((FAQ_COUNT++))
  else
    ((NO_FAQ_COUNT++))
  fi
done
if ((NO_FAQ_COUNT > 0)); then
  warn "${NO_FAQ_COUNT}/${BLOG_COUNT} articles lack an FAQ section"
else
  ok "All articles have FAQ sections"
fi

# --- Hub & Spoke integrity ---
section "Hub & Spoke Integrity"
HUBS=("api-gateway-migration-guide-2026" "what-is-mcp-gateway" "open-source-api-gateway-2026")
HUB_NAMES=("Migration" "MCP & AI" "Open Source")

for i in "${!HUBS[@]}"; do
  hub="${HUBS[$i]}"
  name="${HUB_NAMES[$i]}"
  spoke_count=0
  for f in "$BLOG_DIR"/*.md "$BLOG_DIR"/*.mdx; do
    [[ -f "$f" ]] || continue
    # Don't count the hub article itself
    if [[ "$(basename "$f")" != *"$hub"* ]] && grep -q "$hub" "$f" 2>/dev/null; then
      ((spoke_count++))
    fi
  done
  if ((spoke_count == 0)); then
    warn "Pillar '${name}': no spokes link to hub '${hub}'"
  else
    ok "Pillar '${name}': ${spoke_count} spoke(s) link to hub"
  fi
done

# --- Summary ---
echo ""
echo "=== Audit Summary ==="
echo "Articles scanned: ${BLOG_COUNT}"
echo -e "Errors: ${RED}${ERRORS}${NC}"
echo -e "Warnings: ${YELLOW}${WARNINGS}${NC}"

if ((ERRORS > 0)); then
  echo -e "\n${RED}AUDIT FAILED${NC} — ${ERRORS} error(s) must be resolved."
  exit 1
else
  echo -e "\n${GREEN}AUDIT PASSED${NC}"
  exit 0
fi
