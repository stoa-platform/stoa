# STOA Gateway Load Benchmarks

Reproducible load tests for STOA Gateway using [hey](https://github.com/rakyll/hey).

## Prerequisites

```bash
brew install hey  # macOS
# or: go install github.com/rakyll/hey@latest
```

## Quick Start

```bash
# Against local Docker Compose
docker compose up -d
./scripts/benchmarks/load-test.sh --target http://localhost:8080

# Against VPS deployment
./scripts/benchmarks/load-test.sh --target http://51.83.45.13:8080 --duration 60
```

## What It Tests

| Scenario | Features Active | Measures |
|----------|----------------|----------|
| Health Check | None (baseline) | Raw HTTP throughput |
| Proxy Passthrough | Routing only | Proxy overhead vs direct |
| Proxy + API Key Auth | Routing + auth | Auth lookup overhead |
| Proxy + Auth + Rate Limit | Routing + auth + rate limit | Full pipeline overhead |

Each scenario runs at 5 concurrency levels (1, 10, 50, 100, 500) for 30 seconds per level.

The script configures gateway features via the Admin API between runs, so results
reflect real feature overhead rather than synthetic benchmarks.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--target <url>` | (required) | Gateway base URL |
| `--admin <url>` | same as target | Admin API base URL |
| `--duration <sec>` | 30 | Seconds per concurrency level |
| `--output <dir>` | `./benchmark-results` | Output directory |

Environment variable `STOA_ADMIN_TOKEN` overrides the admin API token (default: `arena-admin-token-2026`).

## Output

Results are saved as timestamped Markdown files in the output directory:

```
benchmark-results/
  benchmark-20260213-143052.md
```

Each report includes:
- Machine profile (CPU, RAM, OS)
- Markdown tables with RPS, P50/P95/P99 latency, error rate
- Notes on methodology

## Interpreting Results

- **RPS** (Requests Per Second): higher is better
- **P50/P95/P99**: latency at that percentile; lower is better
- **Errors**: percentage of non-200 responses; 0% is ideal
- Compare scenarios to see per-feature overhead (e.g., auth adds X ms)

## Reproducibility

For publishable results:
1. Run each benchmark 3 times
2. Report the median
3. Include the machine profile from the report header
4. Note if the backend is remote (httpbin.org) or local
