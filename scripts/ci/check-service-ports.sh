#!/usr/bin/env bash
# Cross-repo service port drift detection (CAB-1935)
#
# Validates that svc.cluster.local references in k8s deployment manifests
# use the correct service ports (from stoa-infra Helm charts).
#
# Usage: ./scripts/ci/check-service-ports.sh
# Exit: 0 = OK, 1 = mismatch found

set -eo pipefail

# Known service ports (source: stoa-infra/charts/*/values.yaml)
# Update this list when a service port changes in stoa-infra.
KNOWN_PORTS="
stoa-control-plane-api:8000
stoa-control-plane-ui:80
stoa-portal:80
stoa-gateway:80
stoa-link:8081
keycloak:8080
opensearch-dashboards:5601
grafana:3000
prometheus-kube-prometheus-prometheus:9090
redpanda:9092
"

get_expected_port() {
    echo "$KNOWN_PORTS" | grep "^$1:" | cut -d: -f2
}

ERRORS=0

echo "Service Port Consistency Check"
echo "==============================="

for manifest in */k8s/deployment.yaml; do
    [ -f "$manifest" ] || continue

    # Extract service:port pairs from svc.cluster.local URLs
    grep -oE '[a-z0-9-]+\.[a-z0-9-]+\.svc\.cluster\.local:[0-9]+' "$manifest" 2>/dev/null | while read -r match; do
        svc_name="${match%%.*}"
        used_port="${match##*:}"

        expected=$(get_expected_port "$svc_name")
        if [ -n "$expected" ] && [ "$used_port" != "$expected" ]; then
            echo ""
            echo "  MISMATCH  $manifest"
            echo "    Service:  $svc_name"
            echo "    Used:     :$used_port"
            echo "    Expected: :$expected"
            # Write to temp file since we're in a subshell (pipe)
            echo "1" >> /tmp/port-check-errors.$$
        fi
    done
done

if [ -f /tmp/port-check-errors.$$ ]; then
    ERRORS=$(wc -l < /tmp/port-check-errors.$$)
    rm -f /tmp/port-check-errors.$$
fi

echo ""
echo "-------------------------------"
if [ "$ERRORS" -gt 0 ]; then
    echo "FAIL: $ERRORS port mismatch(es) found"
    echo "Fix: update the port to match stoa-infra/charts/<component>/values.yaml"
    exit 1
else
    echo "OK: all service ports consistent"
    exit 0
fi
