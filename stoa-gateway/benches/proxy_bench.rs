//! Proxy hot path micro-benchmarks (CAB-1332)
//!
//! Validates performance optimization targets:
//! - Route lookup with Arc (vs clone): atomic increment vs 7 String copies
//! - Method comparison: as_str() vs to_string() allocation
//! - Header copy: HeaderMap clone overhead
//! - Traceparent generation: single-fill + pre-sized buffer
//! - URL construction: pre-allocated buffer
//!
//! Run: `cargo bench --bench proxy_bench`

use std::hint::black_box;

use criterion::{criterion_group, criterion_main, Criterion};

// ---------------------------------------------------------------------------
// 1. Route lookup — Arc<ApiRoute> vs full clone
//    Target: ~50ns (Arc clone) vs ~200ns (full clone)
// ---------------------------------------------------------------------------
fn bench_route_lookup(c: &mut Criterion) {
    use stoa_gateway::routes::registry::{ApiRoute, RouteRegistry};

    let registry = RouteRegistry::new();

    // Register 50 routes simulating a real deployment
    for i in 0..50 {
        registry.upsert(ApiRoute {
            id: format!("route-{}", i),
            name: format!("api-{}", i),
            tenant_id: format!("tenant-{}", i % 5),
            path_prefix: format!("/apis/tenant-{}/service-{}", i % 5, i),
            backend_url: format!("https://backend-{}.example.com/v1", i),
            methods: vec!["GET".to_string(), "POST".to_string()],
            spec_hash: format!("sha256:{:032x}", i),
            activated: true,
            classification: None,
            contract_key: None,
        });
    }

    c.bench_function("route_lookup_arc_50_routes", |b| {
        b.iter(|| registry.find_by_path(black_box("/apis/tenant-2/service-22/users")))
    });

    c.bench_function("route_lookup_arc_miss", |b| {
        b.iter(|| registry.find_by_path(black_box("/nonexistent/path")))
    });

    // 100 routes — stress test for linear scan
    let registry_100 = RouteRegistry::new();
    for i in 0..100 {
        registry_100.upsert(ApiRoute {
            id: format!("route-{}", i),
            name: format!("api-{}", i),
            tenant_id: format!("tenant-{}", i % 10),
            path_prefix: format!("/apis/tenant-{}/svc-{}", i % 10, i),
            backend_url: format!("https://backend-{}.example.com/v1", i),
            methods: vec!["GET".to_string()],
            spec_hash: String::new(),
            activated: true,
            classification: None,
            contract_key: None,
        });
    }

    c.bench_function("route_lookup_arc_100_routes", |b| {
        b.iter(|| registry_100.find_by_path(black_box("/apis/tenant-5/svc-55/data")))
    });
}

// ---------------------------------------------------------------------------
// 2. Method comparison — as_str() vs to_string()
//    Target: ~0ns (str comparison) vs ~30ns (String alloc + compare)
// ---------------------------------------------------------------------------
fn bench_method_comparison(c: &mut Criterion) {
    use axum::http::Method;

    let methods_list: Vec<String> = vec![
        "GET".to_string(),
        "POST".to_string(),
        "PUT".to_string(),
        "DELETE".to_string(),
    ];

    let method = Method::POST;

    // Current: as_str() comparison (zero alloc)
    c.bench_function("method_cmp_as_str", |b| {
        b.iter(|| {
            let m = black_box(&method);
            black_box(!methods_list.iter().any(|s| s == m.as_str()))
        })
    });

    // Baseline comparison: to_string() (allocating)
    c.bench_function("method_cmp_to_string", |b| {
        b.iter(|| {
            let m = black_box(&method);
            let s = m.to_string();
            black_box(!methods_list.contains(&s))
        })
    });
}

// ---------------------------------------------------------------------------
// 3. Header copy — clone overhead for realistic HeaderMap
//    Target: measure actual cost per request
// ---------------------------------------------------------------------------
fn bench_header_copy(c: &mut Criterion) {
    use axum::http::{HeaderMap, HeaderValue};

    // Build realistic request headers (12 headers, typical browser/API client)
    let mut headers = HeaderMap::new();
    headers.insert("content-type", HeaderValue::from_static("application/json"));
    headers.insert(
        "accept",
        HeaderValue::from_static("application/json, text/plain, */*"),
    );
    headers.insert(
        "authorization",
        HeaderValue::from_static(
            "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.sig",
        ),
    );
    headers.insert(
        "user-agent",
        HeaderValue::from_static("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"),
    );
    headers.insert("x-request-id", HeaderValue::from_static("req-abc-123-def"));
    headers.insert("x-forwarded-for", HeaderValue::from_static("192.168.1.100"));
    headers.insert("x-forwarded-proto", HeaderValue::from_static("https"));
    headers.insert("x-tenant-id", HeaderValue::from_static("acme-corporation"));
    headers.insert(
        "x-correlation-id",
        HeaderValue::from_static("corr-550e8400-e29b-41d4"),
    );
    headers.insert("accept-encoding", HeaderValue::from_static("gzip, deflate"));
    headers.insert("cache-control", HeaderValue::from_static("no-cache"));
    headers.insert("connection", HeaderValue::from_static("keep-alive"));

    c.bench_function("header_map_clone_12_headers", |b| {
        b.iter(|| black_box(headers.clone()))
    });

    // Minimal headers (3 — best case for deferred clone savings)
    let mut minimal = HeaderMap::new();
    minimal.insert("content-type", HeaderValue::from_static("application/json"));
    minimal.insert("accept", HeaderValue::from_static("*/*"));
    minimal.insert("host", HeaderValue::from_static("api.example.com"));

    c.bench_function("header_map_clone_3_headers", |b| {
        b.iter(|| black_box(minimal.clone()))
    });
}

// ---------------------------------------------------------------------------
// 4. Traceparent generation — optimized single-fill + pre-sized buffer
//    Target: <100ns for full traceparent string
// ---------------------------------------------------------------------------
fn bench_traceparent_gen(c: &mut Criterion) {
    use rand::rngs::SmallRng;
    use rand::{Rng, SeedableRng};

    // Optimized: single 24-byte fill + pre-sized buffer (CAB-1332)
    c.bench_function("traceparent_gen_optimized", |b| {
        let mut rng = SmallRng::from_os_rng();

        b.iter(|| {
            let mut bytes = [0u8; 24];
            rng.fill(&mut bytes);

            let mut buf = String::with_capacity(55);
            buf.push_str("00-");
            hex_encode_into(&bytes[..16], &mut buf);
            buf.push('-');
            hex_encode_into(&bytes[16..], &mut buf);
            buf.push_str("-01");
            black_box(buf)
        })
    });

    // Baseline: two separate fills + format! (old approach)
    c.bench_function("traceparent_gen_format", |b| {
        let mut rng = SmallRng::from_os_rng();

        b.iter(|| {
            let mut trace_bytes = [0u8; 16];
            let mut span_bytes = [0u8; 8];
            rng.fill(&mut trace_bytes);
            rng.fill(&mut span_bytes);

            let tp = format!(
                "00-{}-{}-01",
                hex_encode_alloc(&trace_bytes),
                hex_encode_alloc(&span_bytes),
            );
            black_box(tp)
        })
    });
}

/// Optimized hex encode: writes directly into caller's buffer.
fn hex_encode_into(bytes: &[u8], buf: &mut String) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for &b in bytes {
        buf.push(HEX[(b >> 4) as usize] as char);
        buf.push(HEX[(b & 0x0f) as usize] as char);
    }
}

/// Old-style hex encode: allocates a new String (baseline).
fn hex_encode_alloc(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push(HEX[(b >> 4) as usize] as char);
        s.push(HEX[(b & 0x0f) as usize] as char);
    }
    s
}

// ---------------------------------------------------------------------------
// 5. URL construction — pre-allocated buffer (already optimized, baseline)
//    Target: validate existing optimization holds
// ---------------------------------------------------------------------------
fn bench_url_construction(c: &mut Criterion) {
    let backend = "https://backend-22.example.com/v1";
    let remaining_path = "/users/550e8400-e29b-41d4/orders";
    let query = Some("page=1&limit=20&sort=created_at");

    // Current: pre-allocated String::with_capacity
    c.bench_function("url_build_prealloc", |b| {
        b.iter(|| {
            let be = black_box(backend);
            let rp = black_box(remaining_path);
            let q = black_box(query);
            let capacity = be.len() + rp.len() + q.map_or(0, |qq| 1 + qq.len());
            let mut url = String::with_capacity(capacity);
            url.push_str(be);
            url.push_str(rp);
            if let Some(qq) = q {
                url.push('?');
                url.push_str(qq);
            }
            black_box(url)
        })
    });

    // Baseline: format! (naive approach, for comparison)
    c.bench_function("url_build_format", |b| {
        b.iter(|| {
            let be = black_box(backend);
            let rp = black_box(remaining_path);
            let q = black_box(query);
            let url = match q {
                Some(qq) => format!("{}{}?{}", be, rp, qq),
                None => format!("{}{}", be, rp),
            };
            black_box(url)
        })
    });
}

// ---------------------------------------------------------------------------
// Criterion groups
// ---------------------------------------------------------------------------
criterion_group!(
    proxy_benches,
    bench_route_lookup,
    bench_method_comparison,
    bench_header_copy,
    bench_traceparent_gen,
    bench_url_construction,
);
criterion_main!(proxy_benches);
