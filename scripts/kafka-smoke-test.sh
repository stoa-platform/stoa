#!/bin/bash
# Kafka Topic Smoke Test
# CAB-498: Verify 3 core topics are created and operational
#
# Usage: ./scripts/kafka-smoke-test.sh
# Prerequisites: kubectl access to stoa-system namespace

set -e

NAMESPACE="stoa-system"
POD="redpanda-0"
BROKER="localhost:9092"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Kafka Topic Smoke Test (CAB-498)"
echo "=========================================="
echo ""

# Check Redpanda pod is running
echo -n "Checking Redpanda pod status... "
if kubectl get pod -n "$NAMESPACE" "$POD" &>/dev/null; then
    POD_STATUS=$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.status.phase}')
    if [ "$POD_STATUS" == "Running" ]; then
        echo -e "${GREEN}✓${NC} Running"
    else
        echo -e "${RED}✗${NC} Pod status: $POD_STATUS"
        exit 1
    fi
else
    echo -e "${RED}✗${NC} Pod not found"
    exit 1
fi

echo ""
echo "Testing 3 core topics:"
echo "  1. stoa.audit.trail (6 partitions, 90d retention)"
echo "  2. stoa.catalog.sync (12 partitions, 7d retention)"
echo "  3. stoa.error.snapshots (3 partitions, 30d retention)"
echo ""

TOPICS=("stoa.audit.trail" "stoa.catalog.sync" "stoa.error.snapshots")
EXPECTED_PARTITIONS=(6 12 3)
EXPECTED_RETENTION=(7776000000 604800000 2592000000)  # milliseconds

PASS_COUNT=0
FAIL_COUNT=0

for i in "${!TOPICS[@]}"; do
    TOPIC="${TOPICS[$i]}"
    EXPECTED_PARTS="${EXPECTED_PARTITIONS[$i]}"
    EXPECTED_RET="${EXPECTED_RETENTION[$i]}"

    echo "----------------------------------------"
    echo "Topic: $TOPIC"
    echo "----------------------------------------"

    # Check topic exists
    echo -n "  Existence check... "
    if kubectl exec -n "$NAMESPACE" "$POD" -- rpk topic list --brokers="$BROKER" 2>/dev/null | grep -q "^$TOPIC\s"; then
        echo -e "${GREEN}✓${NC} Topic exists"
    else
        echo -e "${RED}✗${NC} Topic not found"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    # Get topic details
    TOPIC_INFO=$(kubectl exec -n "$NAMESPACE" "$POD" -- rpk topic describe "$TOPIC" --brokers="$BROKER" 2>/dev/null)

    # Check partition count
    echo -n "  Partition count... "
    ACTUAL_PARTS=$(echo "$TOPIC_INFO" | grep -oP 'PARTITION\s+\K\d+' | sort -n | tail -1)
    ACTUAL_PARTS=$((ACTUAL_PARTS + 1))  # Convert 0-indexed to count
    if [ "$ACTUAL_PARTS" -eq "$EXPECTED_PARTS" ]; then
        echo -e "${GREEN}✓${NC} $ACTUAL_PARTS partitions"
    else
        echo -e "${RED}✗${NC} Expected $EXPECTED_PARTS, got $ACTUAL_PARTS"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi

    # Check retention policy
    echo -n "  Retention policy... "
    ACTUAL_RET=$(echo "$TOPIC_INFO" | grep -oP 'retention.ms\s+\K\d+' || echo "0")
    if [ "$ACTUAL_RET" -eq "$EXPECTED_RET" ]; then
        DAYS=$((EXPECTED_RET / 86400000))
        echo -e "${GREEN}✓${NC} ${DAYS}d retention"
    else
        echo -e "${YELLOW}⚠${NC} Expected $EXPECTED_RET ms, got $ACTUAL_RET ms"
        # Non-critical warning, don't fail
    fi

    # Smoke test: produce a message
    echo -n "  Produce test... "
    TEST_MSG="{\"test\":true,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"topic\":\"$TOPIC\"}"
    if echo "$TEST_MSG" | kubectl exec -i -n "$NAMESPACE" "$POD" -- rpk topic produce "$TOPIC" --brokers="$BROKER" 2>/dev/null | grep -q "Produced"; then
        echo -e "${GREEN}✓${NC} Message produced"
    else
        echo -e "${RED}✗${NC} Failed to produce"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    # Smoke test: consume the message
    echo -n "  Consume test... "
    if kubectl exec -n "$NAMESPACE" "$POD" -- rpk topic consume "$TOPIC" --brokers="$BROKER" --num=1 --format=json 2>/dev/null | grep -q "test"; then
        echo -e "${GREEN}✓${NC} Message consumed"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo -e "${RED}✗${NC} Failed to consume"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi

    echo ""
done

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "Passed: ${GREEN}${PASS_COUNT}/${#TOPICS[@]}${NC}"
echo -e "Failed: ${RED}${FAIL_COUNT}${NC}"
echo ""

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ All smoke tests passed${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
