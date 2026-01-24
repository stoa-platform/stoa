#!/bin/bash
# =============================================================================
# Verify and setup DNS for console.gostoa.dev
# CAB-237: Rename devops.gostoa.dev → console.gostoa.dev
# =============================================================================
#
# This script verifies DNS configuration for the console subdomain
# and optionally creates/updates Route53 records.
#
# Prerequisites:
#   - AWS CLI configured with Route53 access
#   - dig command available
#
# Usage:
#   ./verify-console-dns.sh [BASE_DOMAIN] [--create]
#
# Example:
#   ./verify-console-dns.sh gostoa.dev          # Verify only
#   ./verify-console-dns.sh gostoa.dev --create # Create if missing
# =============================================================================

set -e

# Configuration
BASE_DOMAIN="${1:-gostoa.dev}"
CREATE_MODE="${2:-}"
CONSOLE_DOMAIN="console.${BASE_DOMAIN}"

# Get hosted zone ID
get_hosted_zone_id() {
    aws route53 list-hosted-zones --query "HostedZones[?Name=='${BASE_DOMAIN}.'].Id" --output text | sed 's|/hostedzone/||'
}

echo "=== DNS Verification for ${CONSOLE_DOMAIN} ==="
echo ""

# Check current DNS resolution
echo "=== Current DNS Resolution ==="
echo "Checking ${CONSOLE_DOMAIN}..."
DNS_RESULT=$(dig +short ${CONSOLE_DOMAIN} 2>/dev/null || echo "NXDOMAIN")

if [ -z "${DNS_RESULT}" ] || [ "${DNS_RESULT}" = "NXDOMAIN" ]; then
    echo "❌ ${CONSOLE_DOMAIN} does not resolve"
    DNS_EXISTS=false
else
    echo "✅ ${CONSOLE_DOMAIN} resolves to: ${DNS_RESULT}"
    DNS_EXISTS=true
fi

echo ""

# Check if devops subdomain exists (for comparison/migration)
echo "=== Checking old devops subdomain ==="
DEVOPS_DOMAIN="devops.${BASE_DOMAIN}"
DEVOPS_RESULT=$(dig +short ${DEVOPS_DOMAIN} 2>/dev/null || echo "NXDOMAIN")

if [ -z "${DEVOPS_RESULT}" ] || [ "${DEVOPS_RESULT}" = "NXDOMAIN" ]; then
    echo "ℹ️  ${DEVOPS_DOMAIN} does not exist (already migrated or never created)"
else
    echo "⚠️  ${DEVOPS_DOMAIN} still resolves to: ${DEVOPS_RESULT}"
    echo "   Consider removing this record after migration"
fi

echo ""

# Check Route53 (if AWS CLI available)
if command -v aws &> /dev/null; then
    echo "=== Route53 Configuration ==="

    HOSTED_ZONE_ID=$(get_hosted_zone_id)

    if [ -z "${HOSTED_ZONE_ID}" ]; then
        echo "❌ Could not find hosted zone for ${BASE_DOMAIN}"
        echo "   Make sure AWS CLI is configured and you have Route53 access"
    else
        echo "Hosted Zone ID: ${HOSTED_ZONE_ID}"
        echo ""

        # List relevant records
        echo "Records for ${BASE_DOMAIN}:"
        aws route53 list-resource-record-sets \
            --hosted-zone-id ${HOSTED_ZONE_ID} \
            --query "ResourceRecordSets[?contains(Name, 'console') || contains(Name, 'devops')].[Name, Type, TTL, ResourceRecords[0].Value || AliasTarget.DNSName]" \
            --output table 2>/dev/null || echo "Could not list records"

        # Create record if requested
        if [ "${CREATE_MODE}" = "--create" ] && [ "${DNS_EXISTS}" = "false" ]; then
            echo ""
            echo "=== Creating DNS Record ==="

            # Get the ALB DNS name from Kubernetes ingress
            ALB_DNS=$(kubectl get ingress -n stoa-system -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")

            if [ -z "${ALB_DNS}" ]; then
                echo "❌ Could not determine ALB DNS name from Kubernetes ingress"
                echo "   Please provide ALB_DNS environment variable"
                exit 1
            fi

            echo "Creating CNAME record: ${CONSOLE_DOMAIN} -> ${ALB_DNS}"

            # Create change batch
            CHANGE_BATCH=$(cat <<EOF
{
    "Changes": [{
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": "${CONSOLE_DOMAIN}",
            "Type": "CNAME",
            "TTL": 300,
            "ResourceRecords": [{"Value": "${ALB_DNS}"}]
        }
    }]
}
EOF
)

            aws route53 change-resource-record-sets \
                --hosted-zone-id ${HOSTED_ZONE_ID} \
                --change-batch "${CHANGE_BATCH}"

            echo "✅ DNS record created"
            echo "   Note: DNS propagation may take a few minutes"
        fi
    fi
else
    echo "⚠️  AWS CLI not available, skipping Route53 checks"
fi

echo ""
echo "=== Summary ==="
if [ "${DNS_EXISTS}" = "true" ]; then
    echo "✅ ${CONSOLE_DOMAIN} is properly configured"
else
    echo "⚠️  ${CONSOLE_DOMAIN} needs DNS configuration"
    echo "   Run with --create flag to create the record automatically"
    echo "   Or manually add a CNAME/A record pointing to your ALB/ingress"
fi
