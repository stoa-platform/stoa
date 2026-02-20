#!/bin/bash
# Verify Kafka/Redpanda topics match topic-policies.yaml configuration
#
# Usage:
#   ./verify-topics.sh
#
# Environment variables:
#   REDPANDA_POD     - Kubernetes pod name (default: redpanda-0)
#   KAFKA_NAMESPACE  - Kubernetes namespace (default: kafka)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YAML_FILE="${SCRIPT_DIR}/topic-policies.yaml"

REDPANDA_POD="${REDPANDA_POD:-redpanda-0}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-kafka}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "STOA Kafka Topic Verification"
echo "=============================="
echo ""

# Parse expected topics from YAML
parse_expected_topics() {
    python3 -c "
import yaml

with open('${YAML_FILE}') as f:
    config = yaml.safe_load(f)

topics = config.get('topics', {})
for name, conf in topics.items():
    partitions = conf.get('partitions', 3)
    retention_days = conf.get('retention_days', 30)
    print(f'{name}|{partitions}|{retention_days}')
"
}

# Get actual topics from Redpanda
get_actual_topics() {
    if kubectl get pod -n "$KAFKA_NAMESPACE" "$REDPANDA_POD" &>/dev/null; then
        kubectl exec -n "$KAFKA_NAMESPACE" "$REDPANDA_POD" -- rpk topic describe "$1" 2>/dev/null || echo "NOT_FOUND"
    else
        echo "Error: Cannot connect to Redpanda pod"
        exit 1
    fi
}

# Main verification
verify() {
    local total=0
    local ok=0
    local missing=0
    local mismatch=0

    echo "Checking topics..."
    echo ""

    while IFS='|' read -r topic expected_partitions expected_retention; do
        ((total++))

        printf "%-40s " "$topic"

        describe_output=$(get_actual_topics "$topic")

        if [[ "$describe_output" == "NOT_FOUND" ]]; then
            echo -e "${RED}✗ MISSING${NC}"
            ((missing++))
        else
            # Extract actual partitions (rpk output format)
            actual_partitions=$(echo "$describe_output" | grep -oP 'partition count:\s+\K\d+' || echo "0")

            if [[ "$actual_partitions" == "$expected_partitions" ]]; then
                echo -e "${GREEN}✓ OK${NC} (partitions: $actual_partitions)"
                ((ok++))
            else
                echo -e "${YELLOW}⚠ MISMATCH${NC} (expected: $expected_partitions, actual: $actual_partitions)"
                ((mismatch++))
            fi
        fi
    done < <(parse_expected_topics)

    echo ""
    echo "Summary:"
    echo "--------"
    echo "Total topics: $total"
    echo -e "${GREEN}OK: $ok${NC}"
    echo -e "${YELLOW}Mismatches: $mismatch${NC}"
    echo -e "${RED}Missing: $missing${NC}"

    if [[ $missing -gt 0 ]] || [[ $mismatch -gt 0 ]]; then
        echo ""
        echo "Run ./create-topics.sh to create missing topics"
        exit 1
    fi
}

# Check dependencies
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

if ! python3 -c "import yaml" 2>/dev/null; then
    echo "Error: PyYAML not installed. Run: pip install pyyaml"
    exit 1
fi

verify
