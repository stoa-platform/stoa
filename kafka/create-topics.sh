#!/bin/bash
# Create Kafka/Redpanda topics from topic-policies.yaml
#
# Usage:
#   ./create-topics.sh [dry-run]
#
# Environment variables:
#   KAFKA_BROKER     - Kafka bootstrap server (default: localhost:9092)
#   REDPANDA_POD     - Kubernetes pod name (default: redpanda-0)
#   KAFKA_NAMESPACE  - Kubernetes namespace (default: kafka)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YAML_FILE="${SCRIPT_DIR}/topic-policies.yaml"
DRY_RUN="${1:-false}"

KAFKA_BROKER="${KAFKA_BROKER:-localhost:9092}"
REDPANDA_POD="${REDPANDA_POD:-redpanda-0}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-kafka}"

# Parse YAML and create topics
parse_yaml() {
    python3 -c "
import sys
import yaml

with open('${YAML_FILE}') as f:
    config = yaml.safe_load(f)

topics = config.get('topics', {})
for name, conf in topics.items():
    partitions = conf.get('partitions', 3)
    retention_days = conf.get('retention_days', 30)
    retention_ms = retention_days * 24 * 60 * 60 * 1000 if retention_days > 0 else -1
    delivery = conf.get('delivery', 'at_least_once')
    description = conf.get('description', '')

    print(f'{name}|{partitions}|{retention_ms}|{delivery}|{description}')
"
}

create_topic_rpk() {
    local topic=$1
    local partitions=$2
    local retention_ms=$3
    local delivery=$4
    local description=$5

    echo "Creating topic: $topic"
    echo "  Partitions: $partitions"
    echo "  Retention: $retention_ms ms"
    echo "  Delivery: $delivery"
    echo "  Description: $description"

    if [[ "$DRY_RUN" == "dry-run" ]]; then
        echo "  [DRY RUN] Would create topic"
    else
        # Check if running in Kubernetes
        if kubectl get pod -n "$KAFKA_NAMESPACE" "$REDPANDA_POD" &>/dev/null; then
            kubectl exec -n "$KAFKA_NAMESPACE" "$REDPANDA_POD" -- \
                rpk topic create "$topic" \
                --partitions "$partitions" \
                --replicas 3 \
                --config retention.ms="$retention_ms" \
                --config min.insync.replicas=2 || echo "  ⚠ Topic may already exist"
        else
            # Local Redpanda/Kafka
            rpk topic create "$topic" \
                --brokers "$KAFKA_BROKER" \
                --partitions "$partitions" \
                --replicas 3 \
                --config retention.ms="$retention_ms" \
                --config min.insync.replicas=2 || echo "  ⚠ Topic may already exist"
        fi
        echo "  ✓ Created"
    fi
    echo ""
}

verify_topics() {
    echo "Verifying topics..."
    if kubectl get pod -n "$KAFKA_NAMESPACE" "$REDPANDA_POD" &>/dev/null; then
        kubectl exec -n "$KAFKA_NAMESPACE" "$REDPANDA_POD" -- rpk topic list
    else
        rpk topic list --brokers "$KAFKA_BROKER"
    fi
}

main() {
    echo "STOA Kafka Topic Creator"
    echo "========================"
    echo ""

    if [[ "$DRY_RUN" == "dry-run" ]]; then
        echo "MODE: DRY RUN"
        echo ""
    fi

    # Check dependencies
    if ! command -v python3 &>/dev/null; then
        echo "Error: python3 not found"
        exit 1
    fi

    if ! python3 -c "import yaml" 2>/dev/null; then
        echo "Error: PyYAML not installed. Run: pip install pyyaml"
        exit 1
    fi

    # Create topics
    while IFS='|' read -r topic partitions retention_ms delivery description; do
        create_topic_rpk "$topic" "$partitions" "$retention_ms" "$delivery" "$description"
    done < <(parse_yaml)

    if [[ "$DRY_RUN" != "dry-run" ]]; then
        echo ""
        verify_topics
    fi

    echo ""
    echo "Done!"
}

main "$@"
