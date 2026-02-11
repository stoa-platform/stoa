//! STOA Gateway micro-benchmarks
//!
//! Validates ADR performance claims:
//! - ADR-034: Rust gateway fast-path latencies
//! - ADR-012: RBAC/auth overhead <1ms
//! - ADR-008: Semantic cache hit <50us
//! - ADR-024: Edge-MCP routing <5ms overhead
//!
//! Run: `cargo bench` (default features, no cmake/kafka required)

use criterion::{black_box, criterion_group, criterion_main, Criterion};

// ---------------------------------------------------------------------------
// 1. API key cache lookup (moka sync cache hit) — target <1us
//    Validates: ADR-012 auth overhead claim
// ---------------------------------------------------------------------------
fn bench_api_key_lookup(c: &mut Criterion) {
    use moka::sync::Cache;
    use std::time::Duration;

    let cache: Cache<String, String> = Cache::builder()
        .time_to_live(Duration::from_secs(300))
        .max_capacity(10_000)
        .build();

    // Pre-populate with 1000 keys
    for i in 0..1000 {
        cache.insert(format!("sk-test-{:04}", i), format!("tenant-{}", i % 10));
    }

    c.bench_function("api_key_cache_hit", |b| {
        b.iter(|| {
            let key = black_box("sk-test-0500");
            cache.get(key)
        })
    });

    c.bench_function("api_key_cache_miss", |b| {
        b.iter(|| {
            let key = black_box("sk-nonexistent-key");
            cache.get(key)
        })
    });
}

// ---------------------------------------------------------------------------
// 2. JWT header extraction (decode without signature verification) — target <100us
//    Validates: ADR-012 auth fast-path for cached tokens
// ---------------------------------------------------------------------------
fn bench_jwt_extract(c: &mut Criterion) {
    use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
    use serde::{Deserialize, Serialize};

    #[derive(Debug, Serialize, Deserialize)]
    struct Claims {
        sub: String,
        exp: usize,
        tenant_id: String,
        roles: Vec<String>,
    }

    // Create a real JWT for benchmarking (HS256, self-signed)
    let secret = b"bench-secret-key-not-for-production";
    let claims = Claims {
        sub: "user-123".to_string(),
        exp: 9_999_999_999,
        tenant_id: "oasis".to_string(),
        roles: vec!["stoa:read".to_string(), "stoa:write".to_string()],
    };
    let token = jsonwebtoken::encode(
        &jsonwebtoken::Header::default(),
        &claims,
        &jsonwebtoken::EncodingKey::from_secret(secret),
    )
    .expect("encode JWT");

    let decoding_key = DecodingKey::from_secret(secret);
    let mut validation = Validation::new(Algorithm::HS256);
    validation.validate_exp = false;

    c.bench_function("jwt_decode_hs256", |b| {
        b.iter(|| {
            decode::<Claims>(black_box(&token), &decoding_key, &validation).expect("valid token")
        })
    });

    // Benchmark just header decode (no signature check) — what we do for routing
    c.bench_function("jwt_header_decode", |b| {
        b.iter(|| jsonwebtoken::decode_header(black_box(&token)).expect("valid header"))
    });
}

// ---------------------------------------------------------------------------
// 3. Rate limit check (sliding window acquire) — target <500ns
//    Validates: ADR-022 multi-tenant isolation overhead
// ---------------------------------------------------------------------------
fn bench_rate_limit_check(c: &mut Criterion) {
    use stoa_gateway::config::Config;
    use stoa_gateway::rate_limit::RateLimiter;

    let config = Config {
        rate_limit_default: Some(10_000),
        rate_limit_window_seconds: Some(60),
        ..Config::default()
    };
    let limiter = RateLimiter::new(&config);

    c.bench_function("rate_limit_check_allowed", |b| {
        b.iter(|| {
            let result = limiter.check(black_box("tenant-bench"));
            black_box(result.allowed);
        })
    });

    // Consumer rate limiter (token bucket, CAB-1121)
    use stoa_gateway::quota::{ConsumerRateLimiter, RateLimiterConfig};

    let consumer_limiter = ConsumerRateLimiter::new(RateLimiterConfig {
        default_rate_per_minute: 100_000,
        ..RateLimiterConfig::default()
    });

    c.bench_function("consumer_rate_limit_check", |b| {
        b.iter(|| {
            let _ = consumer_limiter.check_rate_limit(black_box("consumer-bench"));
        })
    });
}

// ---------------------------------------------------------------------------
// 4. Path normalization (UUID → :id regex) — target <100ns
//    Validates: ADR-034 metrics overhead claim
// ---------------------------------------------------------------------------
fn bench_path_normalization(c: &mut Criterion) {
    use stoa_gateway::metrics::normalize_path;

    c.bench_function("path_normalize_static", |b| {
        b.iter(|| normalize_path(black_box("/mcp/tools/list")))
    });

    c.bench_function("path_normalize_uuid", |b| {
        b.iter(|| {
            normalize_path(black_box(
                "/admin/apis/550e8400-e29b-41d4-a716-446655440000",
            ))
        })
    });

    c.bench_function("path_normalize_nested", |b| {
        b.iter(|| {
            normalize_path(black_box(
                "/admin/quotas/abcdef12-3456-7890-abcd-ef1234567890/reset",
            ))
        })
    });
}

// ---------------------------------------------------------------------------
// 5. Semantic cache key generation + lookup — target <50us
//    Validates: ADR-008 cache hit latency claim
// ---------------------------------------------------------------------------
fn bench_semantic_cache(c: &mut Criterion) {
    use moka::sync::Cache;
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    use std::time::Duration;

    // Replicate SemanticCache::cache_key logic (private fn, bench the pattern)
    fn cache_key(tool_name: &str, tenant_id: &str, args_json: &str) -> String {
        let mut hasher = DefaultHasher::new();
        args_json.hash(&mut hasher);
        let args_hash = hasher.finish();
        format!("{}:{}:{:016x}", tenant_id, tool_name, args_hash)
    }

    c.bench_function("semantic_cache_key_gen", |b| {
        b.iter(|| {
            cache_key(
                black_box("stoa_catalog"),
                black_box("acme"),
                black_box(r#"{"category":"ml","limit":10}"#),
            )
        })
    });

    // Benchmark moka future cache get (sync wrapper for bench)
    let cache: Cache<String, String> = Cache::builder()
        .time_to_live(Duration::from_secs(60))
        .max_capacity(10_000)
        .build();

    // Pre-populate
    for i in 0..100 {
        let key = cache_key("stoa_catalog", &format!("tenant-{}", i), r#"{"page":1}"#);
        cache.insert(key, format!(r#"{{"apis":["api-{}"]}}"#, i));
    }

    let hit_key = cache_key("stoa_catalog", "tenant-50", r#"{"page":1}"#);

    c.bench_function("semantic_cache_hit", |b| {
        b.iter(|| cache.get(black_box(&hit_key)))
    });

    c.bench_function("semantic_cache_miss", |b| {
        b.iter(|| cache.get(black_box("nonexistent:key:0000000000000000")))
    });
}

// ---------------------------------------------------------------------------
// 6. Route matching (longest prefix match) — target <1us
//    Validates: ADR-024 edge-mcp routing overhead claim
// ---------------------------------------------------------------------------
fn bench_route_matching(c: &mut Criterion) {
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
            methods: vec![],
            spec_hash: String::new(),
            activated: true,
        });
    }

    c.bench_function("route_match_found", |b| {
        b.iter(|| registry.find_by_path(black_box("/apis/tenant-2/service-22/users")))
    });

    c.bench_function("route_match_not_found", |b| {
        b.iter(|| registry.find_by_path(black_box("/nonexistent/path")))
    });

    // Bench with deeper nesting
    registry.upsert(ApiRoute {
        id: "deep-route".to_string(),
        name: "deep-api".to_string(),
        tenant_id: "acme".to_string(),
        path_prefix: "/apis/acme/payments/v2/transactions".to_string(),
        backend_url: "https://payments.acme.com/v2".to_string(),
        methods: vec!["GET".to_string(), "POST".to_string()],
        spec_hash: String::new(),
        activated: true,
    });

    c.bench_function("route_match_deep_prefix", |b| {
        b.iter(|| registry.find_by_path(black_box("/apis/acme/payments/v2/transactions/tx-12345")))
    });
}

// ---------------------------------------------------------------------------
// Criterion groups
// ---------------------------------------------------------------------------
criterion_group!(
    benches,
    bench_api_key_lookup,
    bench_jwt_extract,
    bench_rate_limit_check,
    bench_path_normalization,
    bench_semantic_cache,
    bench_route_matching,
);
criterion_main!(benches);
