# STOA Mock Backends

Mock APIs for Central Bank Demo (CAB-1018). Provides three production-grade mock implementations demonstrating STOA Platform patterns: **Circuit Breaker** (Fraud Detection), **Idempotency + Saga** (Settlement), and **Semantic Cache** (Sanctions Screening). All data is 100% synthetic with `X-Demo-Mode: true` headers on all responses.

## Quick Start

### Docker Compose (Recommended)

```bash
cd deploy/docker-compose
docker compose up mock-backends -d

# Verify
curl http://localhost:8090/health
```

### Local Development

```bash
cd mock-backends
pip install -r requirements.txt
uvicorn src.main:app --port 8090 --reload

# Run tests
pytest tests/ -v
```

### Access Points

| Endpoint | URL |
|----------|-----|
| API Docs (Swagger) | http://localhost:8090/docs |
| ReDoc | http://localhost:8090/redoc |
| Health | http://localhost:8090/health |
| Metrics (Prometheus) | http://localhost:8090/metrics |

## APIs

| API | Endpoint | Pattern | Description |
|-----|----------|---------|-------------|
| **Fraud Detection** | `POST /v1/transactions/score` | Circuit Breaker | Real-time transaction fraud scoring |
| **Settlement** | `POST /v1/settlements` | Idempotency + Saga | Interbank settlement with rollback |
| **Sanctions** | `POST /v1/screening/check` | Semantic Cache | Entity screening against OFAC/EU/UN |

### Response Headers (All Endpoints)

```
X-Demo-Mode: true
X-Data-Classification: SYNTHETIC
X-Trace-Id: <uuid>
```

## Demo Scenarios

### 1. Circuit Breaker Pattern (Fraud Detection)

Demonstrates latency spikes and circuit breaker fallback.

```bash
# Normal request (~50ms)
curl -X POST http://localhost:8090/v1/transactions/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "TXN-001",
    "amount": 5000,
    "currency": "EUR",
    "sender_iban": "FR7630006000011234567890189",
    "receiver_iban": "FR7630006000011234567890190"
  }'

# Trigger latency spike (2000ms for next 3 requests)
curl -X POST "http://localhost:8090/demo/trigger/spike?num_requests=3"

# Call again - observe processing_time_ms > 2000
curl -X POST http://localhost:8090/v1/transactions/score \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "TXN-002", "amount": 5000, "currency": "EUR", "sender_iban": "FR76...", "receiver_iban": "FR76..."}'

# Force circuit OPEN (returns 503 with fallback)
curl -X POST http://localhost:8090/demo/trigger/circuit-open

# Call - observe 503 with fallback_used: true
curl -X POST http://localhost:8090/v1/transactions/score \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "TXN-003", "amount": 5000, "currency": "EUR", "sender_iban": "FR76...", "receiver_iban": "FR76..."}'

# Reset to normal
curl -X POST http://localhost:8090/demo/trigger/reset
```

### 2. Idempotency + Saga Pattern (Settlement)

Demonstrates idempotent requests and saga compensation (rollback).

```bash
# Create settlement (first request)
curl -X POST http://localhost:8090/v1/settlements \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: setl-demo-001" \
  -d '{
    "settlement_id": "SETL-001",
    "amount": 50000,
    "currency": "EUR",
    "debtor_iban": "FR7630006000011234567890189",
    "creditor_iban": "DE89370400440532013000",
    "reference": "INV-2026-001"
  }'
# Response: idempotency_hit: false, status: COMPLETED

# Retry with SAME idempotency key
curl -X POST http://localhost:8090/v1/settlements \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: setl-demo-001" \
  -d '{...same payload...}'
# Response: idempotency_hit: true (cached response)

# Trigger rollback for next settlement
curl -X POST http://localhost:8090/demo/trigger/rollback

# Create settlement - will fail and rollback
curl -X POST http://localhost:8090/v1/settlements \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: setl-demo-002" \
  -d '{
    "settlement_id": "SETL-002",
    "amount": 75000,
    "currency": "EUR",
    "debtor_iban": "FR7630006000011234567890189",
    "creditor_iban": "DE89370400440532013000"
  }'
# Response: status: ROLLED_BACK, steps include compensation actions

# Check settlement status with audit trail
curl http://localhost:8090/v1/settlements/SETL-002/status
```

### 3. Semantic Cache Pattern (Sanctions Screening)

Demonstrates cache hits with normalized entity names.

```bash
# Screen sanctioned entity (cache miss)
curl -X POST http://localhost:8090/v1/screening/check \
  -H "Content-Type: application/json" \
  -d '{
    "entity_name": "Ivan Petrov",
    "entity_type": "PERSON",
    "country": "RU"
  }'
# Response: result: HIT, cached: false, matches: [OFAC]

# Screen SAME entity with different case (cache hit)
curl -X POST http://localhost:8090/v1/screening/check \
  -H "Content-Type: application/json" \
  -d '{
    "entity_name": "IVAN PETROV",
    "entity_type": "PERSON",
    "country": "RU"
  }'
# Response: cached: true (normalized key match)

# Screen with hyphen variation (cache hit)
curl -X POST http://localhost:8090/v1/screening/check \
  -H "Content-Type: application/json" \
  -d '{
    "entity_name": "ivan-petrov",
    "entity_type": "PERSON",
    "country": "RU"
  }'
# Response: cached: true

# Clear cache
curl -X POST http://localhost:8090/demo/trigger/cache-clear

# Screen again (cache miss)
curl -X POST http://localhost:8090/v1/screening/check \
  -H "Content-Type: application/json" \
  -d '{"entity_name": "Ivan Petrov", "entity_type": "PERSON", "country": "RU"}'
# Response: cached: false

# Get sanctions list versions
curl http://localhost:8090/v1/screening/lists/version
```

## Demo Trigger Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /demo/trigger/spike?num_requests=N` | Activate 2s latency for N fraud requests |
| `POST /demo/trigger/circuit-open` | Force circuit breaker OPEN (503 responses) |
| `POST /demo/trigger/rollback` | Force next settlement to rollback |
| `POST /demo/trigger/cache-clear` | Clear semantic cache |
| `POST /demo/trigger/reset` | Reset all demo state to normal |
| `GET /demo/state` | Get current demo state (debugging) |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ENVIRONMENT` | `demo` | Environment name |
| `DEMO_MODE` | `true` | Enable X-Demo-Mode headers |
| `AUTH_ENABLED` | `false` | Enable authentication (disabled for demo) |
| `DEMO_SCENARIOS_ENABLED` | `true` | Enable /demo/trigger/* endpoints |
| `METRICS_ENABLED` | `true` | Enable Prometheus metrics |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8090` | Server port |

## Development

### Run Tests

```bash
cd mock-backends
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Test Coverage

```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

### Lint

```bash
ruff check src/ tests/
ruff format src/ tests/
```

### Project Structure

```
mock-backends/
├── src/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Pydantic settings
│   ├── logging_config.py       # Structlog configuration
│   ├── middleware/             # Request/response middleware
│   ├── routers/                # API endpoints
│   ├── schemas/                # Pydantic models
│   └── services/               # Business logic
├── tests/                      # Pytest tests
├── contracts/                  # UAC YAML contracts
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

## UAC Contracts

API contracts are defined in `contracts/` directory using the STOA Universal API Contract format:

- `fraud-detection.uac.yaml` - Circuit breaker, 100ms p95 SLA
- `settlement.uac.yaml` - Idempotency, saga compensation, 99.99% availability
- `sanctions-screening.uac.yaml` - Semantic cache, regulatory compliance

## Metrics

Prometheus metrics available at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `stoa_mock_requests_total` | Counter | Total requests by endpoint and status |
| `stoa_mock_request_duration_seconds` | Histogram | Request latency distribution |
| `stoa_fraud_circuit_state` | Gauge | Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) |
| `stoa_sanctions_cache_hits_total` | Counter | Semantic cache hit count |
| `stoa_settlement_saga_state` | Gauge | Saga execution state |

## License

Proprietary - STOA Platform
