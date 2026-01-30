# STOA Platform - DX Benchmarks

Developer Experience (DX) benchmarks for the STOA Platform quickstart environment.

## OSS Killer Standard Targets

| Metric | Target | Description |
|--------|--------|-------------|
| Cold start | < 120s | Full build + containers up + health check |
| Warm start | < 30s | Cached images + containers up + health check |
| First API call | < 0.5s | POST /api/v1/invites response time |

## Latest Results

**Date**: 2026-01-24
**Commit**: CAB-909 implementation

| Metric | Result | Target | Status | vs Target |
|--------|--------|--------|--------|-----------|
| Cold start | 24.64s | < 120s | PASS | 4.9x faster |
| Warm start | 17.11s | < 30s | PASS | 1.75x faster |
| First API | 0.078s | < 0.5s | PASS | 6.4x faster |

### Machine Profile

| Property | Value |
|----------|-------|
| CPU | Apple M1 Ultra |
| RAM | 64 GB |
| Docker | 29.1.3 |
| OS | macOS Darwin 25.2.0 |

## How to Reproduce

### Prerequisites

- Docker Desktop installed and running
- Python 3.x (for timing calculations)
- curl

### Run Benchmark

```bash
cd stoa-quickstart
chmod +x benchmark.sh
./benchmark.sh
```

### CI Mode (no colors)

```bash
./benchmark.sh --ci
```

### Expected Output

```
STOA Platform - OSS Killer DX Benchmark
========================================

## Machine Profile

| Property | Value |
|----------|-------|
| Date | 2026-01-24T16:30:00+00:00 |
| OS | Darwin 25.2.0 |
| CPU | Apple M1 Ultra |
| RAM | 64 GB |
| Docker | 29.1.3 |

Preparing environment...
Running cold start benchmark... 24.64s
Running warm start benchmark... 17.11s
Running first API call benchmark... 0.08s

## Benchmark Results

| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Cold start | 24.64s | < 120s | PASS |
| Warm start | 17.11s | < 30s | PASS |
| First API | 0.08s | < 0.5s | PASS |

All benchmarks passed!
```

## Benchmark History

| Date | Commit | Cold | Warm | API | Machine |
|------|--------|------|------|-----|---------|
| 2026-01-24 | CAB-909 | 24.64s | 17.11s | 0.078s | M1 Ultra |

## Contributing

When submitting PRs that affect startup time or API performance:

1. Run `./benchmark.sh` before and after changes
2. Include results in PR description
3. Ensure all targets still pass

## Architecture Notes

### What's Measured

- **Cold start**: `docker compose up -d --build` from clean state until `/health` returns 200
- **Warm start**: `docker compose up -d` with cached images until `/health` returns 200
- **First API**: POST request to `/api/v1/invites` endpoint

### Services Started

- PostgreSQL 16
- Redpanda (Kafka-compatible)
- Keycloak 22
- Control Plane (FastAPI)

### Optimization Opportunities

If benchmarks degrade, check:

1. **Cold start slow**: Docker layer caching, multi-stage builds, dependency count
2. **Warm start slow**: Health check intervals, container dependencies
3. **API slow**: Database connection pooling, cold function execution
