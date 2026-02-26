# Gateway Arena — Benchmark Methodology

STOA Gateway Arena is a continuous comparative benchmark for API gateways.
It measures pure gateway overhead using a co-located echo backend, ensuring
fair comparison across all participants.

## What Is Measured

The benchmark evaluates gateway performance across two layers:

- **Layer 0 (Proxy Baseline)** — raw throughput, burst handling, and ramp-up capacity
- **Layer 1 (Enterprise AI Readiness)** — MCP protocol support, auth chains, policy evaluation, and AI guardrails

All gateways proxy the same local nginx echo backend (static JSON, sub-millisecond
response time), so results reflect gateway overhead only — not backend or network latency.

## Layer 0 — Scoring Formula

Seven scenarios are executed per run (an eighth warm-up run is discarded):

| Scenario | VUs | Duration/Iterations | Weight |
|----------|-----|---------------------|--------|
| health | 1 | 10 iterations | — |
| sequential | 1 | 20 iterations | 0.10 |
| burst_10 | 10 | 10 iterations each | — |
| burst_50 | ramping 0-50-0 | 5s ramp, 10s hold, 3s down | 0.20 |
| burst_100 | ramping 0-100-0 | 5s ramp, 10s hold, 3s down | 0.20 |
| sustained | 1 | 100 iterations | — |
| ramp_up | 10-100 req/s | ramping arrival rate, 20s | 0.15 |

Additional weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| Availability | 0.15 | Health check success rate |
| Error Rate | 0.10 | Percentage of non-2xx responses |
| Consistency | 0.10 | IQR-based coefficient of variation: `(P75 - P25) / P50` |

**Composite score** = weighted sum of all components, each scored 0-100.

Latency scoring uses capped P95 values:

| Scenario | Latency Cap |
|----------|-------------|
| sequential | 400 ms |
| burst_50 | 2.5 s |
| burst_100 | 4.0 s |

Latency score per scenario: `max(0, 100 * (1 - P95 / cap))`

## Layer 1 — Enterprise AI Readiness

Eight dimensions measuring AI-native gateway capabilities:

| Dimension | Weight | Latency Cap | What It Tests |
|-----------|--------|-------------|---------------|
| MCP Discovery | 0.15 | 500 ms | `GET /mcp/capabilities` response |
| MCP Tool Execution | 0.20 | 500 ms | `POST /mcp/tools/list` (JSON-RPC or REST) |
| Auth Chain | 0.15 | 1 s | JWT validation + tool call |
| Policy Engine | 0.15 | 200 ms | OPA policy evaluation overhead |
| AI Guardrails | 0.10 | 1 s | PII detection in payload |
| Rate Limiting | 0.10 | 1 s | 429 enforcement accuracy |
| Resilience | 0.10 | 1 s | Bad tool call returns 4xx, not 5xx |
| Agent Governance | 0.05 | 2 s | Session/governance endpoints |

Dimension score: `0.6 * availability_score + 0.4 * latency_score`

Gateways without MCP support score **0** on MCP dimensions (not N/A).

## Statistical Method

Each benchmark session consists of **5 runs**. The first run is discarded as
warm-up. Results are computed from the remaining 4 runs:

- **Central tendency**: Median (robust to outliers)
- **Confidence intervals**: CI95 using t-distribution (df = 3 for 4 valid runs)
- **Consistency metric**: IQR-based CV `(P75 - P25) / P50` instead of standard
  deviation, which is more robust to bimodal latency distributions common in
  network benchmarks

## Fair Comparison Guarantees

1. **Same echo backend** — All gateways proxy to the same nginx container returning
   a static JSON payload in under 1 ms
2. **Same network** — K8s gateways are co-located in the same cluster; VPS gateways
   use a local Docker echo container on the same host
3. **Same k6 engine** — Identical k6 scripts, scenarios, and thresholds for all gateways
4. **Same scoring formula** — No per-gateway adjustments; the formula is applied uniformly

## Reproducibility

### Prerequisites

- [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) (v0.54+)
- Docker (for the echo backend)
- A running gateway instance

### Quick Local Run

```bash
./scripts/traffic/arena/run-local.sh http://localhost:8080
```

This starts a local echo backend, runs 3 key scenarios against the specified
gateway URL, and prints results. See [run-local.sh](../scripts/traffic/arena/run-local.sh)
for details.

### Full Benchmark (K8s)

The production benchmark runs as a K8s CronJob every 30 minutes. Results are
pushed to Prometheus Pushgateway and visualized in Grafana. See
[scripts/traffic/arena/](../scripts/traffic/arena/) for all benchmark scripts.

## Open Participation

Any API gateway can participate:

1. Deploy the gateway with access to the echo backend
2. Add the gateway entry to the benchmark configuration
3. Run the benchmark — same scenarios, same scoring, same CI95 methodology

The specification is open. We encourage gateway maintainers to run the benchmark
independently and share results.

## Source Code

All benchmark scripts are open source under Apache 2.0:

| File | Purpose |
|------|---------|
| [`benchmark.js`](../scripts/traffic/arena/benchmark.js) | k6 scenarios (Layer 0) |
| [`benchmark-enterprise.js`](../scripts/traffic/arena/benchmark-enterprise.js) | k6 scenarios (Layer 1) |
| [`run-arena.py`](../scripts/traffic/arena/run-arena.py) | Scoring engine (median, CI95, composite) |
| [`run-arena-enterprise.py`](../scripts/traffic/arena/run-arena-enterprise.py) | Enterprise scoring engine |
| [`run-arena.sh`](../scripts/traffic/arena/run-arena.sh) | Orchestrator (gateway x run x scenario) |
