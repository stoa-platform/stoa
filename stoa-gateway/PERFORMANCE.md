# STOA Gateway — Performance Guide

## Benchmarks

Two Criterion benchmark suites measure gateway performance:

### `gateway_bench` — ADR validation benchmarks

Validates ADR performance claims (auth, cache, routing, rate limiting).

```bash
cargo bench --bench gateway_bench
```

### `proxy_bench` — Proxy hot path benchmarks (CAB-1332)

Measures the cost of each operation in the dynamic proxy request path:

```bash
cargo bench --bench proxy_bench
```

| Operation | Target | Measured | Notes |
|-----------|--------|----------|-------|
| Route lookup (50 routes) | <500ns | ~279ns | Arc clone (atomic increment) |
| Route lookup (100 routes) | <500ns | ~377ns | Linear scan, still sub-µs |
| Method comparison (as_str) | <10ns | ~4.8ns | Zero allocation |
| Method comparison (to_string) | — | ~26ns | Baseline (5.5x slower) |
| Header clone (12 headers) | <200ns | ~127ns | Only on retry path |
| Traceparent gen (optimized) | <100ns | ~52ns | Single RNG fill + pre-sized buf |
| Traceparent gen (format!) | — | ~151ns | Baseline (2.9x slower) |
| URL construction (prealloc) | <50ns | ~27ns | Pre-allocated capacity |

### Running specific benchmarks

```bash
# Run a single benchmark by name
cargo bench --bench proxy_bench -- route_lookup

# Run with more iterations for stable results
cargo bench --bench proxy_bench -- --sample-size 200

# Save baseline for regression comparison
cargo bench --bench proxy_bench -- --save-baseline before
# ... make changes ...
cargo bench --bench proxy_bench -- --baseline before
```

## Performance Budgets

Total proxy overhead budget: **<1ms per request** (gateway added latency).

| Component | Budget | Actual |
|-----------|--------|--------|
| Route lookup | 500ns | 279ns |
| Method check | 10ns | 5ns |
| URL construction | 50ns | 27ns |
| Traceparent generation | 100ns | 52ns |
| Header copy (to backend) | 200ns | 127ns |
| SSRF check | 500ns | ~200ns |
| **Total gateway overhead** | **<1.5µs** | **~690ns** |

Note: These are micro-benchmark numbers. Real-world overhead includes async runtime scheduling, network I/O, and TLS negotiation with the backend.

## Profiling with Flamegraph

For identifying new bottlenecks:

```bash
# Install flamegraph tool
cargo install flamegraph

# Run gateway under load and capture flamegraph
# Terminal 1: start gateway
cargo run --release

# Terminal 2: generate load with k6
k6 run scripts/traffic/arena/benchmark.js --env SCENARIO=sequential --env TARGET=http://localhost:8080

# Terminal 3: capture flamegraph
cargo flamegraph --bin stoa-gateway -- --config config/dev.yaml
# Output: flamegraph.svg
```

## Arena Integration Benchmarks

For end-to-end latency measurement under realistic conditions, use the Gateway Arena:

```bash
# Local: run k6 against local gateway
k6 run scripts/traffic/arena/benchmark.js \
  --env TARGET=http://localhost:8080 \
  --env SCENARIO=sequential

# K8s: trigger a manual benchmark run
kubectl create job --from=cronjob/gateway-arena arena-manual -n stoa-system
```

See `gateway-arena.md` in `.claude/rules/` for full Arena documentation.

## Key Optimizations (CAB-1332)

1. **Arc\<ApiRoute\> in RouteRegistry** — `find_by_path()` returns `Arc<ApiRoute>` (atomic ref count increment) instead of deep-cloning 7+ String fields per request.

2. **Zero-alloc method comparison** — Uses `Method::as_str()` for direct string slice comparison instead of `method.to_string()` which allocates on every request.

3. **Deferred header clone** — `HeaderMap::clone()` only happens when retry is needed (502/503 on idempotent methods). Non-retryable and non-idempotent requests skip the clone entirely.

4. **Optimized traceparent generation** — Single 24-byte RNG fill + direct hex write into pre-sized 55-byte buffer. Eliminates two separate `String` allocations from the old `format!()` approach.

5. **Pre-allocated URL buffer** — `String::with_capacity(exact_size)` avoids reallocations during URL construction.

6. **Shared static reqwest client** — Single `reqwest::Client` with aggressive connection pooling (256 idle/host, TCP keepalive, TCP_NODELAY).

7. **Thread-local PRNG** — `SmallRng` avoids `getrandom()` syscall per request for traceparent generation.
