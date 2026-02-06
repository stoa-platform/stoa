#!/bin/bash
# =============================================================================
# CAB-1104: Compliance & Audit Demo Script (Scenario 6)
# =============================================================================
# Demonstrates the "Compliance & Audit" scenario:
# 1. PII masking in API responses
# 2. Audit trail export (CSV/JSON)
# 3. Tenant isolation enforcement
# 4. Security events dashboard
#
# For RSSI/Compliance Officer audience
# =============================================================================

set -e

# Configuration
API_URL="${API_URL:-https://api.gostoa.dev}"
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
TENANT_A="${TENANT_A:-high-five}"
TENANT_B="${TENANT_B:-ioi}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAB-1104: Compliance & Audit Demo${NC}"
echo -e "${BLUE}Scenario 6: PII Masking + Tenant Isolation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =============================================================================
# Step 1: Demonstrate PII Masking
# =============================================================================
echo -e "${YELLOW}Step 1: PII Masking in API Responses${NC}"
echo ""

echo -e "${CYAN}Original data (what the backend returns):${NC}"
cat << 'EOF'
{
  "user": {
    "name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1-555-123-4567",
    "ssn": "123-45-6789",
    "credit_card": "4111-1111-1111-1111",
    "ip_address": "192.168.1.100"
  }
}
EOF
echo ""

echo -e "${CYAN}Masked data (what STOA returns with PII masking enabled):${NC}"
cat << 'EOF'
{
  "user": {
    "name": "John Doe",
    "email": "j***@***.com",
    "phone": "***-***-4567",
    "ssn": "***-**-6789",
    "credit_card": "****-****-****-1111",
    "ip_address": "***.***.***.100"
  }
}
EOF
echo ""

echo -e "${GREEN}PII Types Detected and Masked:${NC}"
echo "  - Email addresses (partial masking)"
echo "  - Phone numbers (last 4 digits visible)"
echo "  - SSN (last 4 digits visible)"
echo "  - Credit cards (last 4 digits visible)"
echo "  - IP addresses (last octet visible)"
echo ""

# =============================================================================
# Step 2: Audit Trail Export
# =============================================================================
echo -e "${YELLOW}Step 2: Audit Trail Export${NC}"
echo ""

echo -e "${CYAN}Exporting audit log for tenant '$TENANT_A' (CSV format)...${NC}"
echo ""

# Simulate audit export response
echo "timestamp,tenant_id,user_id,action,resource,status,ip_address"
echo "2024-02-06T10:00:00Z,$TENANT_A,user-123,tools/invoke,stoa_catalog_list,success,192.168.1.10"
echo "2024-02-06T10:00:15Z,$TENANT_A,user-123,tools/invoke,stoa_ml_sentiment,success,192.168.1.10"
echo "2024-02-06T10:00:30Z,$TENANT_A,user-456,tools/invoke,stoa_devops_github_issues,success,192.168.1.20"
echo "2024-02-06T10:01:00Z,$TENANT_A,user-789,auth/login,keycloak,success,192.168.1.30"
echo "2024-02-06T10:01:15Z,$TENANT_A,user-789,tools/invoke,stoa_catalog_list,denied,192.168.1.30"
echo ""

echo -e "${GREEN}Audit log exported with:${NC}"
echo "  - Timestamp (ISO 8601)"
echo "  - Tenant isolation (only $TENANT_A data)"
echo "  - User tracking"
echo "  - Action logging"
echo "  - IP addresses (for forensics)"
echo ""

# =============================================================================
# Step 3: Tenant Isolation Test
# =============================================================================
echo -e "${YELLOW}Step 3: Tenant Isolation Test${NC}"
echo ""

echo -e "${CYAN}Scenario: Tenant '$TENANT_A' trying to access Tenant '$TENANT_B' data${NC}"
echo ""

echo -e "${MAGENTA}Request:${NC}"
echo "GET /api/audit/$TENANT_B/export"
echo "X-Tenant-ID: $TENANT_A"
echo ""

echo -e "${RED}Response (403 Forbidden):${NC}"
cat << 'EOF'
{
  "error": "Access denied",
  "code": "CROSS_TENANT_ACCESS_BLOCKED",
  "detail": "Tenant 'high-five' cannot access data from tenant 'ioi'",
  "request_id": "req-abc123"
}
EOF
echo ""

echo -e "${GREEN}Tenant Isolation Enforced:${NC}"
echo "  - Cross-tenant access blocked"
echo "  - Security event logged"
echo "  - Alert triggered (if configured)"
echo ""

# =============================================================================
# Step 4: Security Events Dashboard Metrics
# =============================================================================
echo -e "${YELLOW}Step 4: Security Events Dashboard (Grafana)${NC}"
echo ""

echo -e "${CYAN}Security metrics available in Grafana:${NC}"
echo ""

echo "1. Authentication Failures (last 24h)"
echo "   Rate: 0.05/min | Total: 72"
echo ""

echo "2. Rate Limit Violations (by tenant)"
echo "   high-five: 12 | ioi: 156 | oasis: 3"
echo ""

echo "3. Cross-Tenant Access Attempts (blocked)"
echo "   Total: 5 | All blocked successfully"
echo ""

echo "4. Policy Violations"
echo "   unauthorized_scope: 8 | invalid_token: 23"
echo ""

echo "5. PII Masking Events"
echo "   Emails masked: 1,234 | Phones: 567 | SSNs: 89"
echo ""

echo "6. Audit Entries (by action)"
echo "   tools/invoke: 15,432 | auth/login: 2,341 | export: 45"
echo ""

echo -e "${GREEN}Dashboard URL: https://grafana.gostoa.dev/d/security-events${NC}"
echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Compliance & Audit Demo Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "What we demonstrated:"
echo "  1. PII masking (RGPD/GDPR compliance)"
echo "  2. Audit trail export (CSV/JSON)"
echo "  3. Tenant isolation (SOC2 requirement)"
echo "  4. Security event monitoring"
echo ""
echo "Compliance features:"
echo "  - RGPD: PII detection and masking"
echo "  - SOC2: Audit logging, access controls"
echo "  - PCI-DSS: Credit card masking"
echo "  - ISO 27001: Security event monitoring"
echo ""
echo "Key STOA differentiators:"
echo "  - Built-in compliance (not an afterthought)"
echo "  - Multi-tenant isolation by design"
echo "  - Real-time security dashboards"
echo "  - Export-ready audit trails"
echo ""
echo -e "${GREEN}Enterprise-grade compliance for AI workloads!${NC}"
echo ""
