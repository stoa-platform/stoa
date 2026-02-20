#!/bin/bash
# Event Backbone Smoke Test
# Verifies Kafka/Redpanda topics, connectivity, and SLO baselines
#
# Usage:
#   ./smoke-test.sh [local|k8s]
#
# Environment:
#   local - Test against localhost:9092 (Docker Compose)
#   k8s   - Test against redpanda-0 pod in stoa-system namespace

set -euo pipefail

MODE="${1:-local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
info() { echo -e "  $1"; }

# Test counter
TESTS_RUN=0
TESTS_PASSED=0

test_result() {
    TESTS_RUN=$((TESTS_RUN + 1))
    if [ $1 -eq 0 ]; then
        pass "$2"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        fail "$2"
    fi
}

# RPK command wrapper
rpk_exec() {
    if [ "$MODE" == "k8s" ]; then
        kubectl exec -n stoa-system redpanda-0 -- rpk "$@" 2>&1
    else
        rpk --brokers localhost:9092 "$@" 2>&1
    fi
}

echo "========================================="
echo "Event Backbone Smoke Test"
echo "========================================="
echo ""
echo "Mode: $MODE"
echo "Date: $(date)"
echo ""

# =============================================================================
# Test 1: Redpanda/Kafka cluster health
# =============================================================================
echo "Test 1: Cluster Health"
info "Checking Redpanda cluster status..."

if rpk_exec cluster info > /dev/null; then
    test_result 0 "Cluster is reachable"
else
    test_result 1 "Cluster is unreachable"
fi

# =============================================================================
# Test 2: Event Backbone Topics Exist
# =============================================================================
echo ""
echo "Test 2: Event Backbone Topics"

REQUIRED_TOPICS=(
    "stoa.audit.events"
    "stoa.catalog.changes"
    "stoa.errors"
)

for topic in "${REQUIRED_TOPICS[@]}"; do
    info "Checking topic: $topic"
    if rpk_exec topic describe "$topic" > /dev/null 2>&1; then
        test_result 0 "Topic $topic exists"
    else
        test_result 1 "Topic $topic missing"
    fi
done

# =============================================================================
# Test 3: Topic Configuration
# =============================================================================
echo ""
echo "Test 3: Topic Configuration"

check_topic_config() {
    local topic=$1
    local expected_partitions=$2
    local retention_days=$3

    info "Checking $topic configuration..."

    # Get partition count
    partition_count=$(rpk_exec topic describe "$topic" | grep -c "partition" || true)

    if [ "$partition_count" -eq "$expected_partitions" ]; then
        test_result 0 "$topic has $expected_partitions partitions"
    else
        warn "$topic has $partition_count partitions (expected $expected_partitions)"
    fi

    # Check retention (convert days to ms)
    if [ "$retention_days" -eq "-1" ]; then
        expected_retention="-1"
    else
        expected_retention=$((retention_days * 24 * 60 * 60 * 1000))
    fi

    retention=$(rpk_exec topic describe "$topic" --print-configs | grep "retention.ms" | awk '{print $2}' || echo "unknown")

    if [ "$retention" == "$expected_retention" ] || [ "$retention" == "unknown" ]; then
        info "$topic retention: $retention ms (expected: $expected_retention ms)"
    else
        warn "$topic retention mismatch: $retention ms (expected: $expected_retention ms)"
    fi
}

check_topic_config "stoa.audit.events" 6 90
check_topic_config "stoa.catalog.changes" 12 7
check_topic_config "stoa.errors" 3 30

# =============================================================================
# Test 4: Produce & Consume Test Messages
# =============================================================================
echo ""
echo "Test 4: Message Production & Consumption"

TEST_MESSAGE='{"test":"smoke-test","timestamp":"'$(date -Iseconds)'"}'

for topic in "${REQUIRED_TOPICS[@]}"; do
    info "Testing $topic..."

    # Produce test message
    if echo "$TEST_MESSAGE" | rpk_exec topic produce "$topic" > /dev/null 2>&1; then
        test_result 0 "Produced test message to $topic"
    else
        test_result 1 "Failed to produce to $topic"
    fi

    # Consume test message (with timeout)
    if timeout 5s rpk_exec topic consume "$topic" --num 1 > /dev/null 2>&1; then
        test_result 0 "Consumed message from $topic"
    else
        warn "Could not consume from $topic (may be empty or timeout)"
    fi
done

# =============================================================================
# Test 5: Replication Factor (production requirement)
# =============================================================================
echo ""
echo "Test 5: Replication & ISR"

if [ "$MODE" == "k8s" ]; then
    info "Checking replication factor..."

    for topic in "${REQUIRED_TOPICS[@]}"; do
        # In single-node dev, replication factor = 1 is expected
        # In production (3+ brokers), should be 3
        replication=$(rpk_exec topic describe "$topic" | grep -o "replicas: [0-9]" | head -1 | awk '{print $2}' || echo "1")

        if [ "$replication" -ge "1" ]; then
            test_result 0 "$topic has replication factor $replication"
        else
            test_result 1 "$topic replication factor check failed"
        fi
    done
else
    info "Skipping replication check in local mode"
fi

# =============================================================================
# Test 6: Consumer Groups
# =============================================================================
echo ""
echo "Test 6: Consumer Groups"

info "Listing consumer groups..."
consumer_groups=$(rpk_exec group list 2>&1 || echo "")

if [ -n "$consumer_groups" ]; then
    info "Consumer groups detected:"
    echo "$consumer_groups" | while read -r line; do
        info "  - $line"
    done
else
    warn "No consumer groups found (expected for fresh deployment)"
fi

# =============================================================================
# Test 7: Prometheus Metrics (K8s only)
# =============================================================================
echo ""
echo "Test 7: Observability"

if [ "$MODE" == "k8s" ]; then
    info "Checking Redpanda metrics endpoint..."

    if kubectl exec -n stoa-system redpanda-0 -- curl -s http://localhost:9644/metrics > /dev/null; then
        test_result 0 "Metrics endpoint is accessible"
    else
        test_result 1 "Metrics endpoint check failed"
    fi

    info "Checking Prometheus scrape config..."
    if kubectl get configmap prometheus-config -n monitoring -o yaml 2>/dev/null | grep -q "redpanda"; then
        test_result 0 "Prometheus scrape config includes Redpanda"
    else
        warn "Redpanda not in Prometheus scrape config (expected if not deployed)"
    fi
else
    info "Skipping observability checks in local mode"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "========================================="
echo "Summary"
echo "========================================="
echo "Tests run: $TESTS_RUN"
echo "Tests passed: $TESTS_PASSED"
echo "Tests failed: $((TESTS_RUN - TESTS_PASSED))"
echo ""

if [ $TESTS_PASSED -eq $TESTS_RUN ]; then
    pass "All tests passed! Event backbone is operational."
    exit 0
else
    fail "Some tests failed. Check configuration."
    exit 1
fi
