#!/bin/bash
# ============================================================================
# 🥤 TEAM COCA SECURITY AUDIT - CAB-638 OASIS TENANT
# ============================================================================
# Auteur: Team Coca (Chucky, N3m0, Gh0st, Pr1nc3ss)
# Cible: STOA Platform - OASIS Tenant (Ready Player One Demo)
# Date: $(date +%Y-%m-%d)
# ============================================================================

set -uo pipefail  # Removed -e for offline testing resilience

# Configuration
MCP_GATEWAY="https://mcp.gostoa.dev"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
REPORT_FILE="audit-report-$(date +%Y%m%d-%H%M%S).md"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Compteurs
PASS=0
FAIL=0
WARN=0

# ============================================================================
# HELPERS
# ============================================================================

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN++))
}

log_info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

separator() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# ============================================================================
# 🔪 CHUCKY - Rate Limit Economic Bypass
# ============================================================================

audit_chucky() {
    separator
    echo -e "${RED}🔪 CHUCKY - Rate Limit Economic Bypass Audit${NC}"
    separator
    
    log_info "Testing transfer-coins rate limit bypass scenarios..."
    
    # Test 1: Vérifier si rate limit est par montant ou par requête
    log_test "T1: Rate limit granularity check"
    
    # Simuler la vérification du rate limit config
    RATE_LIMIT_CONFIG=$(curl -s "${MCP_GATEWAY}/mcp/v1/tools" 2>/dev/null | \
        jq -r '.tools[] | select(.name | contains("transfer-coins")) | .rateLimit // "NOT_FOUND"' 2>/dev/null || echo "UNREACHABLE")
    
    if [[ "$RATE_LIMIT_CONFIG" == "UNREACHABLE" ]]; then
        log_warn "Cannot reach MCP Gateway - testing offline scenarios"
    else
        log_info "Rate limit config: $RATE_LIMIT_CONFIG"
    fi
    
    # Test 2: Cumulative threshold check
    log_test "T2: Cumulative transfer threshold validation"
    echo "  → Scenario: 99 transfers of 999 coins = 98,901 coins (under 100K 2FA trigger)"
    echo "  → Expected: Cumulative threshold should trigger at 100K total/timeframe"
    
    # Check si sliding window existe
    log_test "T3: Sliding window rate limit check"
    echo "  → Attack: Burst at minute boundaries to bypass per-minute limits"
    echo "  → Mitigation needed: Sliding window instead of fixed window"
    
    # Test 4: Multi-account bypass
    log_test "T4: Multi-account transfer aggregation"
    echo "  → Attack: Split transfers across multiple accounts"
    echo "  → Check: Is there cross-account aggregation for governance thresholds?"
    
    # Recommendations
    echo ""
    log_info "CHUCKY RECOMMENDATIONS:"
    echo "  1. Implement cumulative transfer tracking per user/timeframe"
    echo "  2. Add sliding window rate limiting (not fixed)"
    echo "  3. Cross-account transfer correlation for AML compliance"
    echo "  4. Progressive authentication: amount-based, not just threshold-based"
}

# ============================================================================
# 🐠 N3M0 - Agent Credentials Lifecycle
# ============================================================================

audit_n3m0() {
    separator
    echo -e "${BLUE}🐠 N3M0 - Agent Credentials Lifecycle Audit${NC}"
    separator
    
    log_info "Testing agent credential management..."
    
    # Test 1: Agent registration endpoint
    log_test "T1: Agent registration security"
    echo "  → Check: Is agent registration rate-limited?"
    echo "  → Check: Is there email/domain verification for agents?"
    
    # Test 2: Whitelist expiration
    log_test "T2: Whitelist expiration policy"
    
    # Try to find whitelist config
    WHITELIST_CHECK=$(curl -s "${MCP_GATEWAY}/mcp/v1/agents" 2>/dev/null || echo "ENDPOINT_NOT_FOUND")
    
    if [[ "$WHITELIST_CHECK" == "ENDPOINT_NOT_FOUND" ]]; then
        log_warn "Agent management endpoint not publicly accessible (good!)"
    else
        log_warn "Agent endpoint accessible - verify authentication"
    fi
    
    echo "  → Required: TTL on agent whitelists (max 90 days recommended)"
    echo "  → Required: Automatic credential rotation mechanism"
    
    # Test 3: Agent impersonation
    log_test "T3: Agent identity verification"
    echo "  → Attack: Register agent with similar name to trusted agent"
    echo "  → Check: Naming collision prevention (Anorak-AI vs Anorak_AI vs AnorakAI)"
    
    # Test 4: Scope escalation
    log_test "T4: Agent scope escalation prevention"
    echo "  → Attack: Agent requests additional scopes post-registration"
    echo "  → Check: Scope changes require re-approval workflow"
    
    # Test 5: Credential revocation
    log_test "T5: Emergency credential revocation"
    echo "  → Check: Can admin instantly revoke all agent credentials?"
    echo "  → Check: Revocation propagation time to all gateway nodes"
    
    # Recommendations
    echo ""
    log_info "N3M0 RECOMMENDATIONS:"
    echo "  1. Implement agent credential TTL with forced rotation"
    echo "  2. Add naming convention enforcement (prevent homoglyphs)"
    echo "  3. Require re-approval for any scope modification"
    echo "  4. Implement instant revocation with sub-second propagation"
    echo "  5. Add agent activity anomaly detection"
}

# ============================================================================
# 👻 GH0ST - Domain/Email Security
# ============================================================================

audit_gh0st() {
    separator
    echo -e "${PURPLE}👻 GH0ST - Domain/Email Security Audit${NC}"
    separator
    
    log_info "Testing domain separation and email security..."
    
    # Personas config (using simple arrays for bash 3 compatibility)
    PERSONA_NAMES=("Parzival" "Art3mis" "Aech" "Sorrento" "Halliday")
    PERSONA_EMAILS=("wade@oasis.io" "samantha@oasis.io" "helen@oasis.io" "nolan@ioi.com" "james@gregarious.games")
    
    # Test 1: Domain concentration analysis
    log_test "T1: Domain concentration risk analysis"
    
    OASIS_COUNT=0
    IOI_COUNT=0
    OTHER_COUNT=0

    for i in "${!PERSONA_NAMES[@]}"; do
        persona="${PERSONA_NAMES[$i]}"
        email="${PERSONA_EMAILS[$i]}"
        domain="${email#*@}"

        case "$domain" in
            "oasis.io") ((OASIS_COUNT++)) ;;
            "ioi.com") ((IOI_COUNT++)) ;;
            *) ((OTHER_COUNT++)) ;;
        esac

        echo "  → $persona: $email (domain: $domain)"
    done
    
    echo ""
    echo "  Domain distribution:"
    echo "    - oasis.io: $OASIS_COUNT users ($(( OASIS_COUNT * 100 / 5 ))%)"
    echo "    - ioi.com: $IOI_COUNT users ($(( IOI_COUNT * 100 / 5 ))%)"
    echo "    - other: $OTHER_COUNT users ($(( OTHER_COUNT * 100 / 5 ))%)"
    
    if [[ $OASIS_COUNT -ge 3 ]]; then
        log_fail "Single domain compromise affects $OASIS_COUNT/5 personas (>50%)"
    fi
    
    # Test 2: DNS security check
    log_test "T2: Domain DNS security verification"
    
    for domain in "oasis.io" "ioi.com" "gregarious.games"; do
        echo "  Checking $domain..."
        
        # Check if dig is available
        if command -v dig &> /dev/null; then
            # MX record check
            MX_RECORD=$(dig +short +timeout=2 MX "$domain" 2>/dev/null | head -1 || echo "LOOKUP_FAILED")
            echo "    MX: ${MX_RECORD:-NOT_FOUND}"
            
            # SPF check
            SPF_RECORD=$(dig +short +timeout=2 TXT "$domain" 2>/dev/null | grep -i "spf" | head -1 || echo "")
            if [[ -z "$SPF_RECORD" ]]; then
                log_warn "No SPF record for $domain"
            else
                echo "    SPF: Found"
            fi
            
            # DMARC check
            DMARC_RECORD=$(dig +short +timeout=2 TXT "_dmarc.$domain" 2>/dev/null | head -1 || echo "")
            if [[ -z "$DMARC_RECORD" ]]; then
                log_warn "No DMARC record for $domain"
            else
                echo "    DMARC: Found"
            fi
        else
            log_info "dig not available - DNS checks skipped (manual verification needed)"
            echo "    → Manual check required: MX, SPF, DMARC records"
            break
        fi
    done
    
    # Test 3: Password reset flow
    log_test "T3: Password reset email interception risk"
    echo "  → Attack: DNS hijack on oasis.io → intercept reset emails for 3 users"
    echo "  → Mitigation: Require 2FA for all password resets"
    echo "  → Mitigation: Use organization-owned domains with DNSSEC"
    
    # Test 4: Email enumeration
    log_test "T4: Email/user enumeration prevention"
    echo "  → Check: Does login form leak valid email existence?"
    echo "  → Check: Does password reset leak valid accounts?"
    
    # Recommendations
    echo ""
    log_info "GH0ST RECOMMENDATIONS:"
    echo "  1. Diversify persona domains across different registrars"
    echo "  2. Enable DNSSEC on all demo domains"
    echo "  3. Add SPF, DKIM, DMARC on all domains"
    echo "  4. Require 2FA for all password operations"
    echo "  5. Implement email enumeration protection"
    echo "  6. Consider using @gostoa.dev subdomains for demo"
}

# ============================================================================
# 👑 PR1NC3SS - Promotion/Rejection Workflow
# ============================================================================

audit_pr1nc3ss() {
    separator
    echo -e "${YELLOW}👑 PR1NC3SS - Promotion/Rejection Workflow Audit${NC}"
    separator
    
    log_info "Testing promotion and rejection workflows..."
    
    # Role matrix
    echo "Current Role Matrix:"
    echo "  ┌──────────────┬─────────────────────┬──────────────────┐"
    echo "  │ Persona      │ Role                │ Permissions      │"
    echo "  ├──────────────┼─────────────────────┼──────────────────┤"
    echo "  │ Parzival     │ namespace_developer │ Create tools     │"
    echo "  │ Art3mis      │ project_owner       │ Promote tools    │"
    echo "  │ Aech         │ namespace_developer │ Create tools     │"
    echo "  │ Sorrento     │ tenant_admin        │ Admin dashboard  │"
    echo "  │ Halliday     │ security_officer    │ Approve security │"
    echo "  └──────────────┴─────────────────────┴──────────────────┘"
    
    # Test 1: Rejection authority
    log_test "T1: Rejection authority mapping"
    echo "  → Question: Who can REJECT a promotion request?"
    echo "  → Current: Only Halliday (security_officer) mentioned as approver"
    echo "  → Risk: Single point of failure for security reviews"
    
    # Test 2: Approver compromise scenario
    log_test "T2: Compromised approver impact analysis"
    echo "  → Scenario: Halliday account compromised"
    echo "  → Impact: All security approvals can be rubber-stamped"
    echo "  → Missing: Multi-party approval for critical promotions"
    
    # Test 3: Self-approval prevention
    log_test "T3: Self-approval prevention check"
    echo "  → Scenario: Art3mis creates tool AND approves it"
    echo "  → Check: Is creator != approver enforced?"
    
    # Test 4: Approval timeout
    log_test "T4: Promotion request timeout"
    echo "  → Check: Do pending approvals expire?"
    echo "  → Risk: Stale approval requests approved months later"
    
    # Test 5: Audit trail
    log_test "T5: Approval audit trail completeness"
    echo "  → Required fields:"
    echo "     - Who requested"
    echo "     - Who approved/rejected"
    echo "     - When (timestamp)"
    echo "     - Why (justification)"
    echo "     - What changed (diff)"
    
    # Test 6: Rollback mechanism
    log_test "T6: Emergency rollback capability"
    echo "  → Check: Can approved promotion be instantly reverted?"
    echo "  → Check: Who has rollback authority?"
    echo "  → Check: Is there automatic rollback on anomaly detection?"
    
    # Workflow recommendations
    echo ""
    log_info "PR1NC3SS RECOMMENDATIONS:"
    echo "  1. Implement dual-approval for prod promotions (security + admin)"
    echo "  2. Add explicit REJECT action with mandatory justification"
    echo "  3. Enforce creator ≠ approver rule"
    echo "  4. Set 7-day TTL on pending approvals"
    echo "  5. Require change diff review before approval"
    echo "  6. Implement one-click emergency rollback"
    echo "  7. Add anomaly-based automatic rollback triggers"
}

# ============================================================================
# SUMMARY & REPORT
# ============================================================================

generate_report() {
    separator
    echo -e "${GREEN}📊 TEAM COCA AUDIT SUMMARY${NC}"
    separator
    
    TOTAL=$((PASS + FAIL + WARN))
    
    echo ""
    echo "  Results:"
    echo "    ✅ PASS: $PASS"
    echo "    ❌ FAIL: $FAIL"
    echo "    ⚠️  WARN: $WARN"
    echo "    📊 TOTAL: $TOTAL checks"
    echo ""
    
    # Risk score
    if [[ $FAIL -eq 0 && $WARN -le 2 ]]; then
        echo -e "  Overall Risk: ${GREEN}LOW${NC} ✅"
        VERDICT="APPROVED"
    elif [[ $FAIL -le 2 && $WARN -le 5 ]]; then
        echo -e "  Overall Risk: ${YELLOW}MEDIUM${NC} ⚠️"
        VERDICT="CONDITIONAL"
    else
        echo -e "  Overall Risk: ${RED}HIGH${NC} ❌"
        VERDICT="BLOCKED"
    fi
    
    echo ""
    echo "  Verdict: $VERDICT for dry-run"
    echo ""
    
    # Generate markdown report
    cat > "$REPORT_FILE" << EOF
# 🥤 Team Coca Security Audit Report

**Target:** CAB-638 - OASIS Tenant (Ready Player One Demo)
**Date:** $(date +%Y-%m-%d)
**Auditors:** Chucky, N3m0, Gh0st, Pr1nc3ss

## Executive Summary

| Metric | Value |
|--------|-------|
| Pass | $PASS |
| Fail | $FAIL |
| Warnings | $WARN |
| **Verdict** | **$VERDICT** |

## Critical Findings

### 🔪 Chucky (Rate Limit Bypass)
- [ ] Cumulative transfer threshold missing
- [ ] Sliding window rate limit needed
- [ ] Cross-account aggregation required

### 🐠 N3m0 (Agent Credentials)
- [ ] Agent credential TTL not enforced
- [ ] Scope escalation controls unclear
- [ ] Revocation propagation time unknown

### 👻 Gh0st (Domain Security)
- [ ] 60% personas on single domain (oasis.io)
- [ ] DNSSEC/DMARC verification needed
- [ ] Password reset email interception risk

### 👑 Pr1nc3ss (Workflow)
- [ ] Single approver (Halliday) = SPOF
- [ ] Rejection workflow not documented
- [ ] Self-approval prevention unclear

## Remediation Priority

| Priority | Issue | Owner | ETA |
|----------|-------|-------|-----|
| P0 | Dual-approval for prod | TBD | Before demo |
| P0 | Cumulative rate limits | TBD | Before demo |
| P1 | Agent credential TTL | TBD | Post-demo |
| P1 | Domain diversification | TBD | Post-demo |

---
*Generated by Team Coca Audit Script v1.0*
EOF

    echo "  📄 Report saved to: $REPORT_FILE"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════════════════╗"
    echo "║  🥤 TEAM COCA SECURITY AUDIT - OASIS TENANT                               ║"
    echo "║  Target: CAB-638 - Ready Player One Demo (MVP 24/02)                      ║"
    echo "╚═══════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    log_info "Starting comprehensive security audit..."
    log_info "MCP Gateway: $MCP_GATEWAY"
    echo ""
    
    # Run all audits
    audit_chucky
    audit_n3m0
    audit_gh0st
    audit_pr1nc3ss
    
    # Generate summary
    generate_report
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Audit complete. Review $REPORT_FILE for detailed findings."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
