# STOA Platform Load Testing

> **Phase**: 9.5 - Production Readiness
> **Ticket**: CAB-106
> **Tool**: K6 (Grafana Load Testing)
> **Last Updated**: 2026-01-05

## Overview

This directory contains K6 load testing scenarios for the STOA Platform. Tests are designed to validate performance SLOs and identify bottlenecks.

## Quick Start

### Prerequisites

- K6 installed locally (`brew install k6` on macOS)
- OR Docker + Docker Compose
- Keycloak credentials for authenticated tests

### Run a Smoke Test

```bash
# Local K6
./scripts/run-load-tests.sh -s smoke -e dev

# With Docker
./scripts/run-load-tests.sh -s smoke -e dev --docker

# With monitoring stack
./scripts/run-load-tests.sh -s load -e dev --docker --start-stack
```

## Test Scenarios

| Scenario | VUs | Duration | Purpose | Production Safe? |
|----------|-----|----------|---------|------------------|
| `smoke` | 5 | 30s | Basic validation | ✅ Yes |
| `load` | 100 | 5min | Normal traffic | ⚠️ Dev/Staging only |
| `stress` | 500 | 10min | High load capacity | ❌ No |
| `spike` | 1000 | 4min | Sudden surge | ❌ No |

### Smoke Test
Minimal load test suitable for production. Validates that all endpoints respond correctly.

```bash
./scripts/run-load-tests.sh -s smoke -e prod
```

### Load Test
Simulates expected production traffic (100 concurrent users). Tests SLO compliance under normal conditions.

```bash
./scripts/run-load-tests.sh -s load -e staging
```

### Stress Test
Tests system behavior under heavy load (500 users). Identifies breaking points and bottlenecks.

```bash
./scripts/run-load-tests.sh -s stress -e dev
```

### Spike Test
Simulates sudden traffic surge (1000 users spike). Tests autoscaling and recovery behavior.

```bash
./scripts/run-load-tests.sh -s spike -e dev
```

## SLO Thresholds

Based on platform SLO objectives:

| Metric | Target | SLO |
|--------|--------|-----|
| Latency p50 | < 200ms | - |
| Latency p95 | < 500ms | ✅ |
| Latency p99 | < 1000ms | ✅ |
| Error Rate | < 0.1% | ✅ |
| Availability | 99.9% | ✅ |

## Endpoints Tested

### Control-Plane API
- `GET /health` - Health check
- `GET /v1/apis` - List APIs
- `GET /v1/tenants` - List tenants
- `GET /v1/applications` - List applications
- `GET /v1/deployments` - List deployments

### MCP Gateway
- `GET /health` - Health check
- `GET /mcp/v1/tools` - List tools
- `GET /mcp/v1/tools/{name}` - Get tool details
- `POST /mcp/v1/tools/{name}/invoke` - Invoke tool
- `GET /mcp/v1/toolsets` - List toolsets

### API Gateway
- `GET /rest/apigateway/health` - Health check
- `GET /rest/apigateway/apis` - List APIs

## Directory Structure

```
tests/load/
├── k6/
│   ├── scenarios/
│   │   ├── smoke.js       # Minimal load test
│   │   ├── load.js        # Normal traffic simulation
│   │   ├── stress.js      # High load test
│   │   └── spike.js       # Sudden surge test
│   ├── lib/
│   │   ├── config.js      # Environment configuration
│   │   ├── auth.js        # Keycloak authentication
│   │   └── checks.js      # Common assertions
│   └── thresholds.js      # SLO thresholds
├── grafana/
│   ├── provisioning/      # Grafana auto-provisioning
│   └── dashboards/        # Pre-built dashboards
├── docker-compose.yml     # K6 + InfluxDB + Grafana
└── README.md              # This file
```

## Authentication

Tests support authenticated requests via Keycloak. Set credentials as environment variables:

```bash
# User authentication (password grant)
export TEST_USER="testuser"
export TEST_PASSWORD="testpassword"

# Service account (client credentials)
export CLIENT_SECRET="your-client-secret"
```

## Monitoring Stack

Start the monitoring stack to visualize results in real-time:

```bash
# Start InfluxDB + Grafana
cd tests/load
docker compose up -d influxdb grafana

# Access Grafana
open http://localhost:3001  # admin/admin
```

### Pre-built Dashboards

- **K6 Load Test Results** - Response times, error rates, throughput

## CI/CD Integration

### GitHub Actions

```yaml
- name: Run Load Tests
  run: |
    ./scripts/run-load-tests.sh -s smoke -e staging
  env:
    CLIENT_SECRET: ${{ secrets.KEYCLOAK_CLIENT_SECRET }}
```

### Custom Options

```bash
# Override VUs and duration
./scripts/run-load-tests.sh -s load --vus 50 --duration 2m

# Specify output directory
./scripts/run-load-tests.sh -s smoke -o ./my-results
```

## Results Analysis

Results are saved in `tests/load/results/<scenario>-<timestamp>/`:

- `results.json` - Full K6 output in JSON format
- `output.log` - Console output with summary

### Interpreting Results

```
✓ health responds
✓ health is 2xx
✓ api list responds

checks.........................: 98.50% ✓ 1970 ✗ 30
http_req_duration..............: avg=123.45ms p(95)=456.78ms p(99)=789.01ms
http_req_failed................: 0.50%  ✓ 10   ✗ 1990
http_reqs......................: 2000   66.67/s
```

## Troubleshooting

### "Token request failed"
- Verify Keycloak is accessible
- Check credentials are correct
- Ensure client has correct grant types enabled

### "Timeout during test"
- Check network connectivity to target environment
- Verify services are healthy before running tests
- Increase timeout in scenario options

### "Threshold exceeded"
- This is expected for stress/spike tests
- Review error rates and response times
- Check Kubernetes HPA scaling events

## Related Documentation

- [SLO/SLA Documentation](../../docs/SLO-SLA.md)
- [Monitoring Setup](../../docker/observability/README.md)
- [K6 Official Documentation](https://k6.io/docs/)
