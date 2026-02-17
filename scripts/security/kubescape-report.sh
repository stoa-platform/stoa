#!/bin/sh
# Kubescape CIS Benchmark — pushes compliance scores to Pushgateway
# Designed for K8s CronJob with kubescape image
# Follows arena CronJob pattern (k8s/arena/cronjob-prod.yaml)
set -eu

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://pushgateway.monitoring.svc:9091}"
JOB_NAME="kubescape_compliance"
FRAMEWORKS="${FRAMEWORKS:-NSA MITRE}"
OUTPUT_DIR="/tmp/kubescape"

mkdir -p "$OUTPUT_DIR"

metrics=""

for framework in $FRAMEWORKS; do
  echo "=== Scanning framework: $framework ==="

  output_file="$OUTPUT_DIR/${framework}.json"

  # Run kubescape scan with JSON output
  kubescape scan framework "$framework" \
    --format json \
    --output "$output_file" \
    --logger error \
    2>&1 || true

  if [ ! -f "$output_file" ]; then
    echo "  FAIL: no output for $framework"
    metrics="${metrics}kubescape_compliance_score{framework=\"${framework}\"} 0
kubescape_controls_passed{framework=\"${framework}\"} 0
kubescape_controls_failed{framework=\"${framework}\"} 0
kubescape_controls_total{framework=\"${framework}\"} 0
"
    continue
  fi

  # Extract scores from JSON report
  # kubescape JSON has .summaryDetails.complianceScore (0-100)
  score=$(cat "$output_file" | grep -o '"complianceScore":[0-9.]*' | head -1 | cut -d: -f2 || echo "0")
  passed=$(cat "$output_file" | grep -o '"passedControls":[0-9]*' | head -1 | cut -d: -f2 || echo "0")
  failed=$(cat "$output_file" | grep -o '"failedControls":[0-9]*' | head -1 | cut -d: -f2 || echo "0")

  # Fallback: try alternative JSON paths
  if [ "$score" = "0" ] || [ -z "$score" ]; then
    score=$(python3 -c "
import json, sys
try:
    data = json.load(open('$output_file'))
    sd = data.get('summaryDetails', {})
    print(sd.get('complianceScore', 0))
except: print(0)
" 2>/dev/null || echo "0")
  fi

  if [ "$passed" = "0" ] || [ -z "$passed" ]; then
    passed=$(python3 -c "
import json, sys
try:
    data = json.load(open('$output_file'))
    sd = data.get('summaryDetails', {})
    rc = sd.get('controlCounters', sd.get('resourceCounters', {}))
    print(rc.get('passedControls', rc.get('passedResources', 0)))
except: print(0)
" 2>/dev/null || echo "0")
  fi

  if [ "$failed" = "0" ] || [ -z "$failed" ]; then
    failed=$(python3 -c "
import json, sys
try:
    data = json.load(open('$output_file'))
    sd = data.get('summaryDetails', {})
    rc = sd.get('controlCounters', sd.get('resourceCounters', {}))
    print(rc.get('failedControls', rc.get('failedResources', 0)))
except: print(0)
" 2>/dev/null || echo "0")
  fi

  total=$((passed + failed))
  echo "  Score: $score% | Passed: $passed | Failed: $failed | Total: $total"

  metrics="${metrics}kubescape_compliance_score{framework=\"${framework}\"} ${score}
kubescape_controls_passed{framework=\"${framework}\"} ${passed}
kubescape_controls_failed{framework=\"${framework}\"} ${failed}
kubescape_controls_total{framework=\"${framework}\"} ${total}
"
done

# Push to Pushgateway
echo ""
echo "=== Pushing metrics to $PUSHGATEWAY_URL ==="
echo "$metrics"

echo "$metrics" | curl --fail --silent --show-error \
  --data-binary @- \
  "${PUSHGATEWAY_URL}/metrics/job/${JOB_NAME}" \
  && echo "Push OK" \
  || echo "Push FAILED (non-fatal)"

# Cleanup
rm -rf "$OUTPUT_DIR"
