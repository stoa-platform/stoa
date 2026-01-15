# Kafka Bridge - Gateway Error Snapshots Relay

HTTP to Kafka relay service for capturing error snapshots from any API Gateway.

## Overview

```
┌─────────────────┐
│    webMethods   │───┐
└─────────────────┘   │
                      │
┌─────────────────┐   │    HTTP POST     ┌─────────────────┐         ┌───────┐
│      Kong       │───┼──────────────→   │  Kafka Bridge   │────────→│ Kafka │
└─────────────────┘   │   /snapshots     │                 │         │       │
                      │                  └─────────────────┘         └───────┘
┌─────────────────┐   │
│  Traefik/Other  │───┘
└─────────────────┘
```

## Features

- **Gateway Agnostic**: Works with any gateway that supports HTTP POST
- **PII Masking**: Automatically redacts sensitive headers and body fields
- **Schema Normalization**: Converts to unified ErrorSnapshot format
- **Async Publishing**: Non-blocking Kafka publishing
- **Batch Support**: `/snapshots/batch` endpoint for bulk publishing

## API Endpoints

### POST /snapshots

Publish a single error snapshot.

```bash
curl -X POST http://kafka-bridge:8080/snapshots \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-acme",
    "trigger": "5xx",
    "request": {
      "method": "POST",
      "path": "/api/v1/payments",
      "headers": {"Authorization": "Bearer secret", "Content-Type": "application/json"},
      "body": {"amount": 100, "password": "secret123"},
      "client_ip": "192.168.1.100"
    },
    "response": {
      "status": 502,
      "body": {"error": "upstream_timeout"},
      "duration_ms": 30042
    },
    "api_name": "Payment-API",
    "api_version": "1.0"
  }'
```

Response:
```json
{"id": "SNP-20260115-094512-a1b2c3d4", "status": "accepted"}
```

### POST /snapshots/batch

Publish multiple snapshots.

```bash
curl -X POST http://kafka-bridge:8080/snapshots/batch \
  -H "Content-Type: application/json" \
  -d '[{"tenant_id": "...", ...}, {"tenant_id": "...", ...}]'
```

### GET /health

Health check endpoint.

```json
{"status": "healthy", "kafka_connected": true}
```

---

## Gateway Integration Examples

### webMethods API Gateway

Use **Custom Extension** policy to send HTTP POST on error responses.

1. Create a Custom Extension in webMethods Admin UI
2. Configure:
   - **Endpoint**: `http://kafka-bridge.stoa-system:8080/snapshots`
   - **Method**: POST
   - **Condition**: `${response.statusCode} >= 400`

**Payload Template** (in Custom Extension):
```json
{
  "tenant_id": "${request.headers['X-Tenant-ID']}",
  "trigger": "${response.statusCode >= 500 ? '5xx' : '4xx'}",
  "request": {
    "method": "${request.method}",
    "path": "${request.path}",
    "headers": ${request.headers.toJson()},
    "body": ${request.body},
    "client_ip": "${request.clientIP}"
  },
  "response": {
    "status": ${response.statusCode},
    "body": ${response.body},
    "duration_ms": ${response.duration}
  },
  "api_name": "${api.name}",
  "api_version": "${api.version}",
  "trace_id": "${request.headers['X-Trace-ID']}"
}
```

---

### Kong Gateway

Use the **http-log** plugin.

```yaml
# kong.yaml
plugins:
  - name: http-log
    config:
      http_endpoint: http://kafka-bridge.stoa-system:8080/snapshots
      method: POST
      content_type: application/json
      custom_fields_by_lua:
        tenant_id: "return kong.request.get_header('X-Tenant-ID') or 'unknown'"
        trigger: "return kong.response.get_status() >= 500 and '5xx' or '4xx'"
      # Only on errors
      flush_timeout: 1
```

Or use **post-function** plugin for more control:

```lua
-- kong/plugins/error-snapshot/handler.lua
local http = require "resty.http"
local cjson = require "cjson"

function ErrorSnapshotHandler:log(conf)
    local status = kong.response.get_status()
    if status < 400 then return end

    local snapshot = {
        tenant_id = kong.request.get_header("X-Tenant-ID") or "unknown",
        trigger = status >= 500 and "5xx" or "4xx",
        request = {
            method = kong.request.get_method(),
            path = kong.request.get_path(),
            headers = kong.request.get_headers(),
            body = kong.request.get_body(),
            client_ip = kong.client.get_ip()
        },
        response = {
            status = status,
            body = kong.response.get_body(),
            duration_ms = math.floor(kong.request.get_elapsed_time())
        },
        api_name = kong.router.get_service().name,
        trace_id = kong.request.get_header("X-Trace-ID")
    }

    local httpc = http.new()
    httpc:request_uri(conf.bridge_url, {
        method = "POST",
        body = cjson.encode(snapshot),
        headers = {["Content-Type"] = "application/json"}
    })
end
```

---

### Traefik

Use **middleware** with access logs + Promtail, or create a custom plugin.

**Option 1: Access Logs + Promtail** (simpler)

```yaml
# traefik.yaml
accessLog:
  filePath: "/var/log/traefik/access.log"
  format: json
  filters:
    statusCodes:
      - "400-599"
  fields:
    headers:
      defaultMode: keep
```

Then use Promtail to ship to Kafka Bridge.

**Option 2: Custom Middleware Plugin**

```go
// plugins-local/error-snapshot/main.go
package error_snapshot

import (
    "bytes"
    "encoding/json"
    "net/http"
)

func (e *ErrorSnapshot) ServeHTTP(rw http.ResponseWriter, req *http.Request) {
    recorder := &responseRecorder{ResponseWriter: rw}
    e.next.ServeHTTP(recorder, req)

    if recorder.status >= 400 {
        go e.publishSnapshot(req, recorder)
    }
}

func (e *ErrorSnapshot) publishSnapshot(req *http.Request, res *responseRecorder) {
    snapshot := map[string]interface{}{
        "tenant_id": req.Header.Get("X-Tenant-ID"),
        "trigger":   getTrigger(res.status),
        "request": map[string]interface{}{
            "method":    req.Method,
            "path":      req.URL.Path,
            "headers":   req.Header,
            "client_ip": req.RemoteAddr,
        },
        "response": map[string]interface{}{
            "status":      res.status,
            "duration_ms": res.duration,
        },
    }

    body, _ := json.Marshal(snapshot)
    http.Post(e.bridgeURL, "application/json", bytes.NewReader(body))
}
```

---

### APISIX

Use the **http-logger** plugin.

```yaml
# apisix/routes/error-logging.yaml
plugins:
  http-logger:
    uri: http://kafka-bridge.stoa-system:8080/snapshots
    batch_max_size: 10
    inactive_timeout: 5
    include_resp_body: true
    include_req_body: true
    concat_method: json
```

---

### Envoy

Use **HTTP tap** or **access log** with gRPC/HTTP sink.

```yaml
# envoy.yaml
static_resources:
  listeners:
    - name: listener_0
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                access_log:
                  - name: envoy.access_loggers.http_grpc
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.access_loggers.grpc.v3.HttpGrpcAccessLogConfig
                      common_config:
                        log_name: error_snapshots
                        transport_api_version: V3
                        grpc_service:
                          envoy_grpc:
                            cluster_name: kafka_bridge
                      additional_request_headers_to_log:
                        - x-tenant-id
                        - x-trace-id
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda.stoa-system:9093` | Kafka/Redpanda servers |
| `KAFKA_TOPIC` | `stoa.errors.snapshots` | Target topic |
| `KAFKA_SASL_USERNAME` | - | SASL username (optional) |
| `KAFKA_SASL_PASSWORD` | - | SASL password (optional) |
| `LOG_LEVEL` | `INFO` | Log level |

## Deployment

```bash
# Build
docker buildx build --platform linux/amd64,linux/arm64 \
  -t your-registry/kafka-bridge:latest --push .

# Deploy via Helm
helm upgrade --install stoa-platform ./charts/stoa-platform \
  --set kafkaBridge.enabled=true \
  --set kafkaBridge.image.repository=your-registry/kafka-bridge
```

## PII Masking

The following are automatically redacted:

**Headers:**
- `authorization`, `x-api-key`, `cookie`, `x-auth-token`
- `x-access-token`, `proxy-authorization`, `x-csrf-token`

**Body fields:**
- `password`, `passwd`, `secret`, `token`, `api_key`
- `access_token`, `refresh_token`, `credit_card`, `cvv`, `ssn`

Masked fields are tracked in the `masked_fields` array of the snapshot.
