#!/bin/sh
# TLS Certificate Expiry Checker — pushes metrics to Pushgateway
# Designed for K8s CronJob (alpine + openssl + curl)
# Follows arena CronJob pattern (k8s/arena/cronjob-prod.yaml)
set -eu

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://pushgateway.monitoring.svc:9091}"
JOB_NAME="tls_cert_monitor"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-5}"

# Endpoints to check — all *.gostoa.dev HTTPS services
HOSTS="${HOSTS:-console.gostoa.dev portal.gostoa.dev api.gostoa.dev mcp.gostoa.dev auth.gostoa.dev vault.gostoa.dev argocd.gostoa.dev}"

metrics=""

for host in $HOSTS; do
  echo "--- Checking $host ---"

  # Get certificate expiry date via openssl
  expiry_date=$(echo | openssl s_client -servername "$host" -connect "$host:443" \
    -verify_quiet 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null \
    | sed 's/notAfter=//' || echo "")

  if [ -z "$expiry_date" ]; then
    echo "  FAIL: could not retrieve certificate for $host"
    metrics="${metrics}tls_cert_expiry_days{host=\"${host}\"} -1
tls_cert_valid{host=\"${host}\"} 0
"
    continue
  fi

  # Calculate days until expiry
  expiry_epoch=$(date -d "$expiry_date" +%s 2>/dev/null || date -jf "%b %d %T %Y %Z" "$expiry_date" +%s 2>/dev/null || echo "0")
  now_epoch=$(date +%s)

  if [ "$expiry_epoch" -eq 0 ]; then
    echo "  FAIL: could not parse expiry date '$expiry_date' for $host"
    metrics="${metrics}tls_cert_expiry_days{host=\"${host}\"} -1
tls_cert_valid{host=\"${host}\"} 0
"
    continue
  fi

  days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

  if [ "$days_left" -gt 0 ]; then
    valid=1
    echo "  OK: $days_left days remaining (expires: $expiry_date)"
  else
    valid=0
    echo "  EXPIRED: certificate expired $((days_left * -1)) days ago"
  fi

  metrics="${metrics}tls_cert_expiry_days{host=\"${host}\"} ${days_left}
tls_cert_valid{host=\"${host}\"} ${valid}
"
done

# Push to Pushgateway
echo ""
echo "--- Pushing metrics to $PUSHGATEWAY_URL ---"
echo "$metrics"

echo "$metrics" | curl --fail --silent --show-error \
  --data-binary @- \
  "${PUSHGATEWAY_URL}/metrics/job/${JOB_NAME}" \
  && echo "Push OK" \
  || echo "Push FAILED (non-fatal)"
