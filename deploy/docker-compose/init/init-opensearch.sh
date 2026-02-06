#!/bin/sh
# =============================================================================
# STOA Platform - OpenSearch Init Script (CAB-1114 Phase 1)
# =============================================================================
# Creates index template, ISM policy, tenant indices, and seeds test data.
# Runs as a one-shot container via curlimages/curl:8.5.0
# =============================================================================

set -e

OS_HOST="http://opensearch:9200"

log() { echo "[INIT] $1"; }

# ---------------------------------------------------------------------------
# 1. Wait for OpenSearch (belt-and-suspenders, depends_on already checks)
# ---------------------------------------------------------------------------
log "Waiting for OpenSearch..."
for i in $(seq 1 30); do
  if curl -sf "${OS_HOST}/_cluster/health" > /dev/null 2>&1; then
    log "OpenSearch is ready"
    break
  fi
  sleep 2
done

# ---------------------------------------------------------------------------
# 2. Create ISM policy: stoa-logs-policy (14 days retention)
# ---------------------------------------------------------------------------
log "Creating ISM policy: stoa-logs-policy"
curl -sf -X PUT "${OS_HOST}/_plugins/_ism/policies/stoa-logs-policy" \
  -H "Content-Type: application/json" \
  -d '{
  "policy": {
    "description": "API call logs lifecycle - 14 days retention",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [{ "rollover": { "min_size": "5gb", "min_index_age": "1d" } }],
        "transitions": [{ "state_name": "warm", "conditions": { "min_index_age": "7d" } }]
      },
      {
        "name": "warm",
        "actions": [
          { "replica_count": { "number_of_replicas": 0 } },
          { "force_merge": { "max_num_segments": 1 } }
        ],
        "transitions": [{ "state_name": "delete", "conditions": { "min_index_age": "14d" } }]
      },
      {
        "name": "delete",
        "actions": [{ "delete": {} }],
        "transitions": []
      }
    ],
    "ism_template": [{ "index_patterns": ["stoa-logs-*"], "priority": 100 }]
  }
}' || log "ISM policy may already exist (OK)"

# ---------------------------------------------------------------------------
# 3. Create index template: stoa-logs
# ---------------------------------------------------------------------------
log "Creating index template: stoa-logs"
curl -sf -X PUT "${OS_HOST}/_index_template/stoa-logs" \
  -H "Content-Type: application/json" \
  -d '{
  "index_patterns": ["stoa-logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    },
    "mappings": {
      "properties": {
        "@timestamp":         { "type": "date" },
        "tenant_id":          { "type": "keyword" },
        "correlation_id":     { "type": "keyword" },
        "method":             { "type": "keyword" },
        "path":               { "type": "keyword" },
        "status":             { "type": "integer" },
        "consumer_id":        { "type": "keyword" },
        "consumer_name":      { "type": "keyword" },
        "api_name":           { "type": "keyword" },
        "api_version":        { "type": "keyword" },
        "latency_ms":         { "type": "float" },
        "request_size_bytes": { "type": "long" },
        "response_size_bytes":{ "type": "long" },
        "error_message":      { "type": "text" },
        "error_code":         { "type": "keyword" },
        "gateway_instance":   { "type": "keyword" },
        "environment":        { "type": "keyword" },
        "tags":               { "type": "keyword" }
      }
    }
  },
  "priority": 100
}' || log "Index template may already exist (OK)"

# ---------------------------------------------------------------------------
# 4. Create per-tenant indices with write aliases
# ---------------------------------------------------------------------------
log "Creating tenant-alpha index..."
curl -sf -X PUT "${OS_HOST}/stoa-logs-tenant-alpha-000001" \
  -H "Content-Type: application/json" \
  -d '{ "aliases": { "stoa-logs-tenant-alpha": { "is_write_index": true } } }' \
  || log "tenant-alpha index may already exist (OK)"

log "Creating tenant-beta index..."
curl -sf -X PUT "${OS_HOST}/stoa-logs-tenant-beta-000001" \
  -H "Content-Type: application/json" \
  -d '{ "aliases": { "stoa-logs-tenant-beta": { "is_write_index": true } } }' \
  || log "tenant-beta index may already exist (OK)"

# ---------------------------------------------------------------------------
# 5. Seed test data — tenant-alpha (~20 docs)
# ---------------------------------------------------------------------------
log "Injecting test data for tenant-alpha..."

# Use current date components for realistic timestamps
NOW=$(date -u +%Y-%m-%dT%H:%M:%S.000Z 2>/dev/null || echo "2026-02-06T10:00:00.000Z")
TODAY=$(echo "$NOW" | cut -c1-10)

curl -sf -X POST "${OS_HOST}/_bulk" -H "Content-Type: application/x-ndjson" -d '
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:12:33.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a001","method":"GET","path":"/v1/apis","status":200,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":42.3,"request_size_bytes":256,"response_size_bytes":4820,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","read"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:13:01.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a002","method":"GET","path":"/v1/apis","status":200,"consumer_id":"consumer-2","consumer_name":"Dashboard Bot","api_name":"Catalog API","api_version":"v1","latency_ms":38.7,"request_size_bytes":210,"response_size_bytes":4820,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","read"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:15:22.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a003","method":"POST","path":"/v1/apis","status":201,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":156.2,"request_size_bytes":1480,"response_size_bytes":620,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","write"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:17:45.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a004","method":"POST","path":"/v1/apis","status":400,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":12.1,"request_size_bytes":980,"response_size_bytes":340,"error_code":"VALIDATION_ERROR","error_message":"Field displayName is required","gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","write","error"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:20:10.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a005","method":"GET","path":"/v1/apis/api-123","status":200,"consumer_id":"consumer-2","consumer_name":"Dashboard Bot","api_name":"Catalog API","api_version":"v1","latency_ms":28.5,"request_size_bytes":128,"response_size_bytes":2240,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","read"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:22:55.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a006","method":"GET","path":"/v1/apis/api-999","status":404,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":8.3,"request_size_bytes":128,"response_size_bytes":180,"error_code":"NOT_FOUND","error_message":"API api-999 not found","gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","read","error"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:25:30.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a007","method":"DELETE","path":"/v1/apis/api-456","status":401,"consumer_id":"consumer-3","consumer_name":"Rogue Client","api_name":"Catalog API","api_version":"v1","latency_ms":5.1,"request_size_bytes":128,"response_size_bytes":220,"error_code":"UNAUTHORIZED","error_message":"Missing or invalid bearer token","gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","delete","error","security"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:30:00.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a008","method":"POST","path":"/v1/tools/invoke","status":200,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Tool Invocation","api_version":"v1","latency_ms":1234.5,"request_size_bytes":2048,"response_size_bytes":8192,"gateway_instance":"gw-edge-01","environment":"production","tags":["tools","invoke"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:32:15.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a009","method":"POST","path":"/v1/tools/invoke","status":200,"consumer_id":"consumer-2","consumer_name":"Dashboard Bot","api_name":"Tool Invocation","api_version":"v1","latency_ms":890.2,"request_size_bytes":1536,"response_size_bytes":6144,"gateway_instance":"gw-edge-01","environment":"production","tags":["tools","invoke"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T08:35:42.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a010","method":"POST","path":"/v1/tools/invoke","status":500,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Tool Invocation","api_version":"v1","latency_ms":2500.0,"request_size_bytes":2048,"response_size_bytes":512,"error_code":"INTERNAL_ERROR","error_message":"Upstream tool timed out after 2500ms","gateway_instance":"gw-edge-01","environment":"production","tags":["tools","invoke","error","timeout"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:00:05.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a011","method":"GET","path":"/v1/subscriptions","status":200,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Subscription API","api_version":"v1","latency_ms":55.8,"request_size_bytes":180,"response_size_bytes":3200,"gateway_instance":"gw-edge-02","environment":"production","tags":["subscriptions","read"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:05:20.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a012","method":"POST","path":"/v1/subscriptions","status":201,"consumer_id":"consumer-2","consumer_name":"Dashboard Bot","api_name":"Subscription API","api_version":"v1","latency_ms":178.4,"request_size_bytes":920,"response_size_bytes":540,"gateway_instance":"gw-edge-02","environment":"production","tags":["subscriptions","write"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:10:33.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a013","method":"GET","path":"/v1/analytics/usage","status":200,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Analytics API","api_version":"v1","latency_ms":320.6,"request_size_bytes":256,"response_size_bytes":12800,"gateway_instance":"gw-edge-02","environment":"production","tags":["analytics","read"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:15:00.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a014","method":"PUT","path":"/v1/apis/api-123","status":200,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":145.3,"request_size_bytes":1800,"response_size_bytes":620,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","write"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:20:45.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a015","method":"GET","path":"/v1/apis","status":200,"consumer_id":"consumer-4","consumer_name":"Monitoring Agent","api_name":"Catalog API","api_version":"v1","latency_ms":35.2,"request_size_bytes":200,"response_size_bytes":4820,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","read","monitoring"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:25:10.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a016","method":"POST","path":"/v1/tools/invoke","status":200,"consumer_id":"consumer-4","consumer_name":"Monitoring Agent","api_name":"Tool Invocation","api_version":"v1","latency_ms":456.7,"request_size_bytes":1024,"response_size_bytes":4096,"gateway_instance":"gw-edge-02","environment":"production","tags":["tools","invoke","monitoring"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:30:22.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a017","method":"DELETE","path":"/v1/apis/api-789","status":200,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":92.1,"request_size_bytes":128,"response_size_bytes":180,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","delete"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:35:55.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a018","method":"POST","path":"/v1/tools/invoke","status":500,"consumer_id":"consumer-2","consumer_name":"Dashboard Bot","api_name":"Tool Invocation","api_version":"v1","latency_ms":1800.0,"request_size_bytes":2048,"response_size_bytes":480,"error_code":"UPSTREAM_ERROR","error_message":"Connection refused to backend service","gateway_instance":"gw-edge-02","environment":"production","tags":["tools","invoke","error"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:40:10.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a019","method":"GET","path":"/v1/health","status":200,"consumer_id":"consumer-4","consumer_name":"Monitoring Agent","api_name":"Health API","api_version":"v1","latency_ms":5.0,"request_size_bytes":64,"response_size_bytes":128,"gateway_instance":"gw-edge-01","environment":"production","tags":["health","monitoring"]}
{"index":{"_index":"stoa-logs-tenant-alpha-000001"}}
{"@timestamp":"'"${TODAY}"'T09:45:30.000Z","tenant_id":"tenant-alpha","correlation_id":"corr-a020","method":"POST","path":"/v1/apis","status":201,"consumer_id":"consumer-1","consumer_name":"AI Agent Alpha","api_name":"Catalog API","api_version":"v1","latency_ms":168.9,"request_size_bytes":1650,"response_size_bytes":640,"gateway_instance":"gw-edge-01","environment":"production","tags":["catalog","write"]}
'

# ---------------------------------------------------------------------------
# 6. Seed test data — tenant-beta (~15 docs)
# ---------------------------------------------------------------------------
log "Injecting test data for tenant-beta..."

curl -sf -X POST "${OS_HOST}/_bulk" -H "Content-Type: application/x-ndjson" -d '
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:00:12.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b001","method":"GET","path":"/v2/products","status":200,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Product API","api_version":"v2","latency_ms":67.4,"request_size_bytes":300,"response_size_bytes":9600,"gateway_instance":"gw-edge-03","environment":"production","tags":["products","read"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:05:45.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b002","method":"POST","path":"/v2/orders","status":201,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Order API","api_version":"v2","latency_ms":234.8,"request_size_bytes":3200,"response_size_bytes":1024,"gateway_instance":"gw-edge-03","environment":"production","tags":["orders","write"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:10:20.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b003","method":"GET","path":"/v2/products/prod-42","status":200,"consumer_id":"consumer-11","consumer_name":"Search Indexer","api_name":"Product API","api_version":"v2","latency_ms":22.1,"request_size_bytes":180,"response_size_bytes":2800,"gateway_instance":"gw-edge-03","environment":"production","tags":["products","read"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:15:33.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b004","method":"PUT","path":"/v2/products/prod-42","status":400,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Product API","api_version":"v2","latency_ms":15.3,"request_size_bytes":2100,"response_size_bytes":380,"error_code":"VALIDATION_ERROR","error_message":"Price must be a positive number","gateway_instance":"gw-edge-03","environment":"production","tags":["products","write","error"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:20:00.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b005","method":"GET","path":"/v2/orders","status":403,"consumer_id":"consumer-12","consumer_name":"Unauthorized App","api_name":"Order API","api_version":"v2","latency_ms":6.8,"request_size_bytes":200,"response_size_bytes":280,"error_code":"FORBIDDEN","error_message":"Insufficient scope: orders:read required","gateway_instance":"gw-edge-03","environment":"production","tags":["orders","read","error","security"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:25:15.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b006","method":"POST","path":"/v2/payments/charge","status":200,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Payment API","api_version":"v2","latency_ms":890.5,"request_size_bytes":1500,"response_size_bytes":620,"gateway_instance":"gw-edge-04","environment":"production","tags":["payments","write"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:30:42.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b007","method":"POST","path":"/v2/payments/charge","status":500,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Payment API","api_version":"v2","latency_ms":2100.0,"request_size_bytes":1500,"response_size_bytes":420,"error_code":"GATEWAY_TIMEOUT","error_message":"Payment provider did not respond within 2000ms","gateway_instance":"gw-edge-04","environment":"production","tags":["payments","write","error","timeout"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:35:10.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b008","method":"GET","path":"/v2/products","status":200,"consumer_id":"consumer-11","consumer_name":"Search Indexer","api_name":"Product API","api_version":"v2","latency_ms":78.9,"request_size_bytes":350,"response_size_bytes":15360,"gateway_instance":"gw-edge-03","environment":"production","tags":["products","read","bulk"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:40:25.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b009","method":"DELETE","path":"/v2/orders/ord-101","status":200,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Order API","api_version":"v2","latency_ms":110.4,"request_size_bytes":128,"response_size_bytes":200,"gateway_instance":"gw-edge-03","environment":"production","tags":["orders","delete"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:45:55.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b010","method":"POST","path":"/v2/notifications/send","status":200,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Notification API","api_version":"v2","latency_ms":145.6,"request_size_bytes":800,"response_size_bytes":320,"gateway_instance":"gw-edge-04","environment":"production","tags":["notifications","write"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:50:30.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b011","method":"GET","path":"/v2/analytics/revenue","status":200,"consumer_id":"consumer-11","consumer_name":"Search Indexer","api_name":"Analytics API","api_version":"v2","latency_ms":445.2,"request_size_bytes":280,"response_size_bytes":18400,"gateway_instance":"gw-edge-04","environment":"production","tags":["analytics","read"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T07:55:10.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b012","method":"POST","path":"/v2/orders","status":201,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Order API","api_version":"v2","latency_ms":198.3,"request_size_bytes":2800,"response_size_bytes":980,"gateway_instance":"gw-edge-03","environment":"production","tags":["orders","write"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T08:00:00.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b013","method":"GET","path":"/v2/health","status":200,"consumer_id":"consumer-13","consumer_name":"Health Monitor","api_name":"Health API","api_version":"v2","latency_ms":4.2,"request_size_bytes":64,"response_size_bytes":128,"gateway_instance":"gw-edge-03","environment":"production","tags":["health","monitoring"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T08:05:22.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b014","method":"POST","path":"/v2/products","status":201,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Product API","api_version":"v2","latency_ms":134.7,"request_size_bytes":2400,"response_size_bytes":680,"gateway_instance":"gw-edge-03","environment":"production","tags":["products","write"]}
{"index":{"_index":"stoa-logs-tenant-beta-000001"}}
{"@timestamp":"'"${TODAY}"'T08:10:45.000Z","tenant_id":"tenant-beta","correlation_id":"corr-b015","method":"POST","path":"/v2/payments/refund","status":200,"consumer_id":"consumer-10","consumer_name":"E-Commerce Bot","api_name":"Payment API","api_version":"v2","latency_ms":780.3,"request_size_bytes":1200,"response_size_bytes":540,"gateway_instance":"gw-edge-04","environment":"production","tags":["payments","write","refund"]}
'

# ---------------------------------------------------------------------------
# 7. Refresh indices to make data searchable immediately
# ---------------------------------------------------------------------------
log "Refreshing indices..."
curl -sf -X POST "${OS_HOST}/stoa-logs-tenant-alpha-*/_refresh" > /dev/null
curl -sf -X POST "${OS_HOST}/stoa-logs-tenant-beta-*/_refresh" > /dev/null

# ---------------------------------------------------------------------------
# 8. DoD Summary
# ---------------------------------------------------------------------------
sleep 1
echo ""
echo "========================================="
echo "CAB-1114 Phase 1 — Init Complete"
echo "  Template: stoa-logs ✓"
echo "  ISM Policy: stoa-logs-policy ✓"
ALPHA_COUNT=$(curl -s "${OS_HOST}/stoa-logs-tenant-alpha-*/_count" | grep -o '"count":[0-9]*')
BETA_COUNT=$(curl -s "${OS_HOST}/stoa-logs-tenant-beta-*/_count" | grep -o '"count":[0-9]*')
echo "  tenant-alpha docs: ${ALPHA_COUNT}"
echo "  tenant-beta docs: ${BETA_COUNT}"
echo "========================================="
