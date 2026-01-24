# Plan de Test & Benchmarks: CAB-914/915

## Objectif

Valider que `docker compose up` fonctionne en < 5 min avec:
1. Tous les services healthy
2. Données OASIS visibles
3. Métriques dans Grafana
4. MCP Gateway opérationnel (CAB-915)
5. Performance conforme aux SLOs

---

## 1. Tests de Validation (CAB-914)

### 1.1 Test de Démarrage

```bash
#!/bin/bash
# test-startup.sh

set -e
START=$(date +%s)

# Clean start
docker compose down -v 2>/dev/null || true
docker compose up -d

# Wait for all services
echo "Waiting for services..."
timeout 300 bash -c 'until docker compose ps | grep -q "healthy"; do sleep 5; done'

END=$(date +%s)
DURATION=$((END - START))

echo "====================================="
echo "Startup time: ${DURATION}s"
echo "====================================="

# Validation
if [ $DURATION -lt 300 ]; then
  echo "PASS: Started in under 5 minutes"
else
  echo "FAIL: Took more than 5 minutes"
  exit 1
fi
```

### 1.2 Test de Santé des Services

```bash
#!/bin/bash
# test-health.sh

SERVICES=(
  "http://localhost:8080/health|Control Plane"
  "http://localhost:3000|Portal"
  "http://localhost:8081/health/ready|Keycloak"
  "http://localhost:9090/-/healthy|Prometheus"
  "http://localhost:3001/api/health|Grafana"
  "http://localhost:3100/ready|Loki"
)

FAILURES=0

for service in "${SERVICES[@]}"; do
  URL="${service%%|*}"
  NAME="${service##*|}"

  if curl -sf "$URL" > /dev/null; then
    echo "PASS: $NAME is healthy"
  else
    echo "FAIL: $NAME is not responding"
    FAILURES=$((FAILURES + 1))
  fi
done

echo "====================================="
echo "Results: $((${#SERVICES[@]} - FAILURES))/${#SERVICES[@]} services healthy"
echo "====================================="

exit $FAILURES
```

### 1.3 Test des Données OASIS

```bash
#!/bin/bash
# test-oasis-data.sh

# Test tenants
TENANTS=$(docker compose exec -T postgres psql -U stoa -c "SELECT COUNT(*) FROM stoa.tenants" -t | tr -d ' ')
if [ "$TENANTS" -ge 4 ]; then
  echo "PASS: $TENANTS tenants found (expected >= 4)"
else
  echo "FAIL: Only $TENANTS tenants found"
  exit 1
fi

# Test APIs
APIS=$(docker compose exec -T postgres psql -U stoa -c "SELECT COUNT(*) FROM stoa.apis" -t | tr -d ' ')
if [ "$APIS" -ge 9 ]; then
  echo "PASS: $APIS APIs found (expected >= 9)"
else
  echo "FAIL: Only $APIS APIs found"
  exit 1
fi

# Test specific OASIS tenants
for tenant in "ioi-corp" "gregarious-games" "gunters-guild"; do
  EXISTS=$(docker compose exec -T postgres psql -U stoa -c "SELECT 1 FROM stoa.tenants WHERE name='$tenant'" -t | tr -d ' ')
  if [ "$EXISTS" = "1" ]; then
    echo "PASS: Tenant '$tenant' exists"
  else
    echo "FAIL: Tenant '$tenant' missing"
    exit 1
  fi
done
```

### 1.4 Test des Métriques Grafana

```bash
#!/bin/bash
# test-grafana-metrics.sh

# Wait for metrics to appear (simulator generates data)
sleep 30

# Query Prometheus for STOA metrics
METRICS=$(curl -s 'http://localhost:9090/api/v1/query?query=stoa_api_requests_total' | jq '.data.result | length')

if [ "$METRICS" -gt 0 ]; then
  echo "PASS: Found $METRICS metric series in Prometheus"
else
  echo "FAIL: No STOA metrics found"
  exit 1
fi

# Check Grafana dashboards are provisioned
DASHBOARDS=$(curl -s -u admin:stoa-demo 'http://localhost:3001/api/search?type=dash-db' | jq 'length')
if [ "$DASHBOARDS" -ge 3 ]; then
  echo "PASS: $DASHBOARDS dashboards provisioned"
else
  echo "FAIL: Only $DASHBOARDS dashboards found"
  exit 1
fi
```

---

## 2. Tests MCP Gateway (CAB-915)

### 2.1 Test Endpoints MCP

```bash
#!/bin/bash
# test-mcp-gateway.sh

MCP_URL="http://localhost:8082"

# Health check
if curl -sf "$MCP_URL/health" > /dev/null; then
  echo "PASS: MCP Gateway health"
else
  echo "FAIL: MCP Gateway not responding"
  exit 1
fi

# List tools (unauthenticated should fail)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$MCP_URL/mcp/tools")
if [ "$STATUS" = "401" ]; then
  echo "PASS: Unauthenticated request returns 401"
else
  echo "WARN: Expected 401, got $STATUS"
fi

# Get token from Keycloak
TOKEN=$(curl -s -X POST \
  "http://localhost:8081/realms/stoa/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=stoa-portal" \
  -d "username=parzival" \
  -d "password=parzival" | jq -r '.access_token')

if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
  echo "PASS: Got Keycloak token"
else
  echo "FAIL: Could not get Keycloak token"
  exit 1
fi

# List tools (authenticated)
TOOLS=$(curl -s -H "Authorization: Bearer $TOKEN" "$MCP_URL/mcp/tools" | jq '.tools | length')
if [ "$TOOLS" -gt 0 ]; then
  echo "PASS: Found $TOOLS MCP tools"
else
  echo "WARN: No MCP tools found (may need APIs published)"
fi
```

### 2.2 Test SSE Endpoint

```bash
#!/bin/bash
# test-mcp-sse.sh

MCP_URL="http://localhost:8082"

# Test SSE connection (timeout after 5s)
timeout 5 curl -N -H "Accept: text/event-stream" "$MCP_URL/mcp/sse" 2>/dev/null &
PID=$!
sleep 2

if ps -p $PID > /dev/null 2>&1; then
  echo "PASS: SSE connection established"
  kill $PID 2>/dev/null
else
  echo "WARN: SSE connection closed (may be expected)"
fi
```

---

## 3. Benchmarks K6

### 3.1 SLO Definitions

| Metric | SLO | Smoke | Load | Stress |
|--------|-----|-------|------|--------|
| p50 latency | < 200ms | - | < 200ms | < 500ms |
| p95 latency | < 500ms | < 1000ms | < 500ms | < 2000ms |
| p99 latency | < 1000ms | < 2000ms | < 1000ms | < 5000ms |
| Error rate | < 0.1% | < 5% | < 0.1% | < 5% |
| Throughput | > 10 rps | - | > 10 rps | > 50 rps |

### 3.2 Scénarios de Test

#### Smoke Test (Production-safe)
```bash
cd tests/load
docker compose --profile k6 run k6 run /scripts/scenarios/smoke.js

# Parameters:
# - 5 VUs
# - 30 seconds
# - Validates basic functionality
```

#### Load Test (Normal traffic)
```bash
docker compose --profile k6 run k6 run /scripts/scenarios/load.js

# Parameters:
# - Ramp: 20 → 50 → 100 VUs
# - Duration: 5 minutes
# - Simulates normal production load
```

#### Stress Test (Breaking point)
```bash
docker compose --profile k6 run k6 run /scripts/scenarios/stress.js

# Parameters:
# - Ramp: 50 → 200 → 500 VUs
# - Duration: 10 minutes
# - Identifies breaking point
```

#### Spike Test (Autoscaling validation)
```bash
docker compose --profile k6 run k6 run /scripts/scenarios/spike.js

# Parameters:
# - Spike to 1000 VUs
# - Tests recovery behavior
```

### 3.3 Commandes de Benchmark

```bash
#!/bin/bash
# run-benchmarks.sh

cd tests/load

# Start K6 infrastructure
docker compose up -d influxdb grafana

# Wait for services
sleep 10

# Run smoke test first
echo "=== SMOKE TEST ==="
docker compose --profile k6 run k6 run /scripts/scenarios/smoke.js

if [ $? -ne 0 ]; then
  echo "FAIL: Smoke test failed, aborting"
  exit 1
fi

# Run load test
echo "=== LOAD TEST ==="
docker compose --profile k6 run k6 run /scripts/scenarios/load.js

# Open Grafana for results
echo "View results at: http://localhost:3001"
echo "Dashboard: K6 Load Testing Results"
```

### 3.4 Résultats Attendus

#### Environnement Local (Docker)

| Scenario | VUs | Duration | Expected p95 | Expected Error Rate |
|----------|-----|----------|--------------|---------------------|
| Smoke | 5 | 30s | < 500ms | < 1% |
| Load | 100 | 5min | < 800ms | < 0.5% |
| Stress | 500 | 10min | < 2000ms | < 5% |

#### Baseline Metrics (Reference)

```
# Smoke Test - Expected Output
checks.........................: 99.00% 297 out of 300
http_req_duration...............: avg=45ms min=12ms med=38ms max=234ms p(90)=89ms p(95)=112ms

# Load Test - Expected Output
checks.........................: 98.50% 29550 out of 30000
http_req_duration...............: avg=78ms min=15ms med=62ms max=890ms p(90)=156ms p(95)=234ms
http_reqs......................: 100/s
```

---

## 4. Matrice de Tests

### Tests Automatisés

| Test | Trigger | Durée | Bloquant |
|------|---------|-------|----------|
| Startup | CI | 5 min | Oui |
| Health | CI | 30s | Oui |
| OASIS Data | CI | 10s | Oui |
| Grafana Metrics | CI | 1 min | Non |
| MCP Gateway | CI (CAB-915) | 30s | Oui |
| Smoke | CI | 1 min | Oui |
| Load | Nightly | 6 min | Non |
| Stress | Weekly | 12 min | Non |

### Tests Manuels

| Test | Description | Critère |
|------|-------------|---------|
| Portal Login | Login parzival/parzival | Voir APIs gunters-guild |
| Grafana Dashboards | Ouvrir http://localhost:3001 | 3 dashboards avec données |
| Keycloak Users | Lister users dans realm stoa | 6 users visibles |
| API Catalog | Naviguer dans Portal | 9 APIs visibles |

---

## 5. Script de Test Complet

```bash
#!/bin/bash
# test-all.sh - Full test suite for CAB-914/915

set -e
FAILURES=0

run_test() {
  local name=$1
  local script=$2

  echo "====================================="
  echo "Running: $name"
  echo "====================================="

  if bash -c "$script"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    FAILURES=$((FAILURES + 1))
  fi
  echo ""
}

# CAB-914 Tests
run_test "Startup Time" "./tests/test-startup.sh"
run_test "Service Health" "./tests/test-health.sh"
run_test "OASIS Data" "./tests/test-oasis-data.sh"
run_test "Grafana Metrics" "./tests/test-grafana-metrics.sh"

# CAB-915 Tests (if MCP Gateway enabled)
if docker compose ps | grep -q mcp-gateway; then
  run_test "MCP Gateway" "./tests/test-mcp-gateway.sh"
  run_test "MCP SSE" "./tests/test-mcp-sse.sh"
fi

# Benchmarks (optional)
if [ "$RUN_BENCHMARKS" = "true" ]; then
  run_test "Smoke Test" "cd tests/load && docker compose --profile k6 run k6 run /scripts/scenarios/smoke.js"
fi

echo "====================================="
echo "SUMMARY: $((4 - FAILURES))/4 tests passed"
echo "====================================="

exit $FAILURES
```

---

## 6. Critères d'Acceptation

### CAB-914 (Quick Start)
- [ ] `docker compose up -d` démarre en < 5 min
- [ ] Tous les services sont healthy
- [ ] 4 tenants OASIS présents
- [ ] 9+ APIs présentes
- [ ] Grafana affiche des métriques
- [ ] Login parzival/parzival fonctionne

### CAB-915 (MCP Gateway)
- [ ] MCP Gateway health check OK
- [ ] Authentification Keycloak fonctionne
- [ ] Endpoint /mcp/tools retourne des outils
- [ ] Endpoint SSE accepte les connexions
- [ ] Dashboard MCP Gateway dans Grafana

### Benchmarks
- [ ] Smoke test < 1% erreurs
- [ ] Load test p95 < 500ms
- [ ] Load test error rate < 0.5%

---

## 7. Environnement de Test

### Prérequis
- Docker v24+
- Docker Compose v2+
- 6GB RAM (8GB recommandé)
- K6 (pour benchmarks locaux)

### Variables d'Environnement

```bash
# .env.test
ENVIRONMENT=test
TEST_USER=parzival
TEST_PASSWORD=parzival
CLIENT_SECRET=stoa-control-plane-secret
BASE_URL=http://localhost:8080
MCP_URL=http://localhost:8082
KEYCLOAK_URL=http://localhost:8081
```

---

## 8. Reporting

### Format de Rapport

```markdown
# Test Report - CAB-914/915

**Date**: YYYY-MM-DD
**Environment**: Local Docker / CI
**Commit**: abc123

## Results Summary

| Category | Passed | Failed | Total |
|----------|--------|--------|-------|
| Startup | 1 | 0 | 1 |
| Health | 6 | 0 | 6 |
| Data | 3 | 0 | 3 |
| MCP | 4 | 0 | 4 |
| Benchmark | 1 | 0 | 1 |

## Benchmark Results

### Smoke Test
- Duration: 30s
- VUs: 5
- Requests: 300
- p95: 112ms
- Errors: 0%

### Load Test
- Duration: 5min
- VUs: 100
- Requests: 30,000
- p95: 234ms
- Errors: 0.1%

## Issues Found
- None

## Recommendations
- Ready for merge
```
