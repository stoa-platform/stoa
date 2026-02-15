//! mTLS Certificate Binding (CAB-864)
//!
//! Implements:
//! - Stage 1: Header extraction + certificate validation
//! - Stage 3: Certificate-token binding verification (RFC 8705)
//!
//! Design doc: docs/CAB-864-MTLS-DESIGN.md
#![allow(dead_code)]

use axum::{
    body::Body,
    http::{Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chrono::{DateTime, Utc};
use ipnet::IpNet;
use serde::Serialize;
use std::{
    net::IpAddr,
    sync::atomic::{AtomicU64, Ordering},
};
use subtle::ConstantTimeEq;
use tracing::{debug, info, warn};

use crate::config::MtlsConfig;
use crate::metrics;

// =============================================================================
// Client Certificate Info (request extension)
// =============================================================================

/// Certificate metadata extracted from X-SSL-* headers.
///
/// Stored in request extensions by Stage 1 (extraction middleware).
/// Used by Stage 3 (binding verification) and downstream handlers.
#[derive(Debug, Clone)]
pub struct ClientCertInfo {
    /// SHA-256 fingerprint (hex lowercase, 64 chars)
    pub fingerprint: String,
    /// Subject Distinguished Name (RFC 2253)
    pub subject_dn: String,
    /// Issuer Distinguished Name
    pub issuer_dn: String,
    /// Certificate serial number (hex)
    pub serial: String,
    /// Certificate validity start
    pub not_before: Option<DateTime<Utc>>,
    /// Certificate validity end
    pub not_after: Option<DateTime<Utc>>,
}

// =============================================================================
// mTLS Error Responses (per design doc section 4)
// =============================================================================

#[derive(Debug, Serialize)]
pub struct MtlsError {
    pub error: String,
    pub detail: String,
}

impl MtlsError {
    fn cert_required() -> Self {
        Self {
            error: "MTLS_CERT_REQUIRED".to_string(),
            detail: "client certificate required".to_string(),
        }
    }

    fn cert_invalid(reason: &str) -> Self {
        Self {
            error: "MTLS_CERT_INVALID".to_string(),
            detail: format!("client certificate validation failed: {reason}"),
        }
    }

    fn cert_expired(date: &str) -> Self {
        Self {
            error: "MTLS_CERT_EXPIRED".to_string(),
            detail: format!("client certificate expired on {date}"),
        }
    }

    fn issuer_denied() -> Self {
        Self {
            error: "MTLS_ISSUER_DENIED".to_string(),
            detail: "certificate issuer not allowed".to_string(),
        }
    }

    fn binding_required() -> Self {
        Self {
            error: "MTLS_BINDING_REQUIRED".to_string(),
            detail: "certificate-bound token required".to_string(),
        }
    }

    fn binding_mismatch() -> Self {
        Self {
            error: "MTLS_BINDING_MISMATCH".to_string(),
            detail: "certificate binding mismatch".to_string(),
        }
    }

    fn untrusted_proxy() -> Self {
        Self {
            error: "MTLS_UNTRUSTED_PROXY".to_string(),
            detail: "mTLS headers from untrusted source".to_string(),
        }
    }
}

impl IntoResponse for MtlsError {
    fn into_response(self) -> Response {
        let status = match self.error.as_str() {
            "MTLS_CERT_REQUIRED" => StatusCode::UNAUTHORIZED,
            _ => StatusCode::FORBIDDEN,
        };
        (status, Json(self)).into_response()
    }
}

// =============================================================================
// mTLS Stats (counters for admin endpoint)
// =============================================================================

/// Atomic counters for mTLS validation stats.
pub struct MtlsStats {
    pub success: AtomicU64,
    pub no_cert: AtomicU64,
    pub invalid: AtomicU64,
    pub expired: AtomicU64,
    pub mismatch: AtomicU64,
    pub denied: AtomicU64,
}

impl MtlsStats {
    pub fn new() -> Self {
        Self {
            success: AtomicU64::new(0),
            no_cert: AtomicU64::new(0),
            invalid: AtomicU64::new(0),
            expired: AtomicU64::new(0),
            mismatch: AtomicU64::new(0),
            denied: AtomicU64::new(0),
        }
    }

    pub fn snapshot(&self) -> MtlsStatsSnapshot {
        MtlsStatsSnapshot {
            success: self.success.load(Ordering::Relaxed),
            no_cert: self.no_cert.load(Ordering::Relaxed),
            invalid: self.invalid.load(Ordering::Relaxed),
            expired: self.expired.load(Ordering::Relaxed),
            mismatch: self.mismatch.load(Ordering::Relaxed),
            denied: self.denied.load(Ordering::Relaxed),
        }
    }
}

impl Default for MtlsStats {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct MtlsStatsSnapshot {
    pub success: u64,
    pub no_cert: u64,
    pub invalid: u64,
    pub expired: u64,
    pub mismatch: u64,
    pub denied: u64,
}

// =============================================================================
// Fingerprint Normalization (design doc section 9)
// =============================================================================

/// Fingerprint format detection.
#[derive(Debug, PartialEq)]
enum FingerprintFormat {
    HexColons,
    Hex,
    Base64Url,
}

/// Detect the format of a fingerprint string.
fn detect_format(input: &str) -> FingerprintFormat {
    if input.contains(':') {
        FingerprintFormat::HexColons
    } else if input.len() == 64 && input.chars().all(|c| c.is_ascii_hexdigit()) {
        FingerprintFormat::Hex
    } else {
        FingerprintFormat::Base64Url
    }
}

/// Normalize a fingerprint to lowercase hex (64 chars).
///
/// Supports: hex_colons (a1:b2:...), hex (a1b2...), base64url.
pub fn normalize_fingerprint_to_hex(input: &str) -> Result<String, String> {
    match detect_format(input) {
        FingerprintFormat::HexColons => {
            let hex: String = input.replace(':', "").to_lowercase();
            if hex.len() != 64 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
                return Err("invalid hex_colons fingerprint".to_string());
            }
            Ok(hex)
        }
        FingerprintFormat::Hex => Ok(input.to_lowercase()),
        FingerprintFormat::Base64Url => {
            let bytes = URL_SAFE_NO_PAD
                .decode(input)
                .map_err(|e| format!("base64url decode failed: {e}"))?;
            if bytes.len() != 32 {
                return Err(format!(
                    "expected 32 bytes for SHA-256, got {}",
                    bytes.len()
                ));
            }
            Ok(hex::encode(&bytes))
        }
    }
}

/// Decode a fingerprint to raw bytes (32 bytes for SHA-256).
fn fingerprint_to_bytes(input: &str) -> Result<Vec<u8>, String> {
    match detect_format(input) {
        FingerprintFormat::HexColons => {
            let hex_str: String = input.replace(':', "").to_lowercase();
            hex::decode(&hex_str).map_err(|e| format!("hex decode failed: {e}"))
        }
        FingerprintFormat::Hex => {
            let lower = input.to_lowercase();
            hex::decode(&lower).map_err(|e| format!("hex decode failed: {e}"))
        }
        FingerprintFormat::Base64Url => URL_SAFE_NO_PAD
            .decode(input)
            .map_err(|e| format!("base64url decode failed: {e}")),
    }
}

/// hex encode helper (inline, no extra dep)
mod hex {
    pub fn encode(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }

    pub fn decode(s: &str) -> Result<Vec<u8>, String> {
        if !s.len().is_multiple_of(2) {
            return Err("odd hex length".to_string());
        }
        (0..s.len())
            .step_by(2)
            .map(|i| {
                u8::from_str_radix(&s[i..i + 2], 16)
                    .map_err(|e| format!("hex decode error at {i}: {e}"))
            })
            .collect()
    }
}

/// Timing-safe comparison of two fingerprints in any format.
///
/// Both are decoded to raw bytes, then compared using subtle::ConstantTimeEq.
pub fn fingerprints_match(a: &str, b: &str) -> Result<bool, String> {
    let bytes_a = fingerprint_to_bytes(a)?;
    let bytes_b = fingerprint_to_bytes(b)?;

    if bytes_a.len() != bytes_b.len() {
        return Ok(false);
    }

    Ok(bytes_a.ct_eq(&bytes_b).into())
}

// =============================================================================
// Trusted Proxy Check
// =============================================================================

/// Parse trusted proxy CIDRs and check if an IP is trusted.
fn is_trusted_proxy(ip: &IpAddr, trusted_proxies: &[String]) -> bool {
    if trusted_proxies.is_empty() {
        return true; // No restriction
    }

    for cidr in trusted_proxies {
        if let Ok(net) = cidr.parse::<IpNet>() {
            if net.contains(ip) {
                return true;
            }
        }
        // Also try parsing as a single IP
        if let Ok(single_ip) = cidr.parse::<IpAddr>() {
            if &single_ip == ip {
                return true;
            }
        }
    }
    false
}

/// Extract the client IP from request (X-Forwarded-For or connection).
fn extract_client_ip(request: &Request<Body>) -> Option<IpAddr> {
    // Try X-Forwarded-For first (rightmost is closest proxy)
    if let Some(xff) = request
        .headers()
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
    {
        // Take the last (rightmost) IP — closest to us
        if let Some(ip_str) = xff.split(',').next_back() {
            if let Ok(ip) = ip_str.trim().parse::<IpAddr>() {
                return Some(ip);
            }
        }
    }

    // Fallback: connection info from extensions
    request
        .extensions()
        .get::<axum::extract::ConnectInfo<std::net::SocketAddr>>()
        .map(|ci| ci.0.ip())
}

/// Check if a path should bypass mTLS entirely.
///
/// OAuth/MCP/discovery/health paths manage their own auth (Bearer tokens, public access).
/// These MUST NOT be blocked by mTLS even when `required_routes` includes `/mcp/*`.
/// Hardcoded intentionally: a config mistake must not break the OAuth flow.
fn is_mtls_bypass_path(path: &str) -> bool {
    const BYPASS_PREFIXES: &[&str] = &[
        "/.well-known/",
        "/oauth/",
        "/mcp/sse",
        "/mcp/tools/",
        "/mcp/v1/",
        "/health",
        "/ready",
        "/metrics",
    ];
    const BYPASS_EXACT: &[&str] = &["/mcp", "/mcp/capabilities", "/mcp/health"];

    BYPASS_PREFIXES.iter().any(|p| path.starts_with(p)) || BYPASS_EXACT.contains(&path)
}

/// Check if a request path matches any of the required routes patterns.
fn is_required_route(path: &str, required_routes: &[String]) -> bool {
    if required_routes.is_empty() {
        return false;
    }
    for pattern in required_routes {
        if pattern == "/*" || pattern == "*" {
            return true;
        }
        // Simple glob: /api/v1/payments/* matches /api/v1/payments/123
        if let Some(prefix) = pattern.strip_suffix("/*") {
            if path.starts_with(prefix) {
                return true;
            }
        } else if path == pattern {
            return true;
        }
    }
    false
}

// =============================================================================
// Stage 1: mTLS Header Extraction Middleware
// =============================================================================

/// mTLS header extraction middleware (Stage 1).
///
/// Reads X-SSL-* headers, validates certificate, stores ClientCertInfo in extensions.
/// If mTLS is disabled, this is a no-op (zero overhead).
pub async fn mtls_extraction_middleware(
    config: MtlsConfig,
    stats: std::sync::Arc<MtlsStats>,
    mut request: Request<Body>,
    next: Next,
) -> Result<Response, MtlsError> {
    // If mTLS disabled, skip entirely
    if !config.enabled {
        return Ok(next.run(request).await);
    }

    let path = request.uri().path().to_string();

    // OAuth/MCP/discovery paths bypass mTLS — they handle their own auth
    if is_mtls_bypass_path(&path) {
        return Ok(next.run(request).await);
    }

    let route_required = is_required_route(&path, &config.required_routes);

    // Check trusted proxy if configured
    if !config.trusted_proxies.is_empty() {
        if let Some(client_ip) = extract_client_ip(&request) {
            if !is_trusted_proxy(&client_ip, &config.trusted_proxies) {
                // Check if any X-SSL-* headers are present from untrusted source
                let has_ssl_headers = request.headers().get(&config.header_verify).is_some();
                if has_ssl_headers {
                    warn!(
                        client_ip = %client_ip,
                        "mTLS headers from untrusted proxy"
                    );
                    stats.denied.fetch_add(1, Ordering::Relaxed);
                    metrics::record_mtls_validation("denied", "unknown");
                    return Err(MtlsError::untrusted_proxy());
                }
            }
        }
    }

    // Read verify header
    let verify = request
        .headers()
        .get(&config.header_verify)
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    match verify {
        None => {
            // No cert presented
            if route_required {
                stats.no_cert.fetch_add(1, Ordering::Relaxed);
                metrics::record_mtls_validation("no_cert", "unknown");
                return Err(MtlsError::cert_required());
            }
            // Optional: continue without cert
            stats.no_cert.fetch_add(1, Ordering::Relaxed);
            metrics::record_mtls_validation("no_cert", "unknown");
            return Ok(next.run(request).await);
        }
        Some(ref v) if v != "SUCCESS" => {
            stats.invalid.fetch_add(1, Ordering::Relaxed);
            metrics::record_mtls_validation("invalid", "unknown");
            return Err(MtlsError::cert_invalid(v));
        }
        _ => {} // SUCCESS — continue
    }

    // Read fingerprint (required)
    let raw_fingerprint = request
        .headers()
        .get(&config.header_fingerprint)
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| {
            stats.invalid.fetch_add(1, Ordering::Relaxed);
            metrics::record_mtls_validation("invalid", "unknown");
            MtlsError::cert_invalid("missing fingerprint header")
        })?;

    let fingerprint = normalize_fingerprint_to_hex(raw_fingerprint).map_err(|e| {
        stats.invalid.fetch_add(1, Ordering::Relaxed);
        metrics::record_mtls_validation("invalid", "unknown");
        MtlsError::cert_invalid(&e)
    })?;

    // Read DN headers
    let subject_dn = request
        .headers()
        .get(&config.header_subject_dn)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    let issuer_dn = request
        .headers()
        .get(&config.header_issuer_dn)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    let serial = request
        .headers()
        .get(&config.header_serial)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    // Parse dates
    let not_before = request
        .headers()
        .get(&config.header_not_before)
        .and_then(|v| v.to_str().ok())
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|dt| dt.with_timezone(&Utc));

    let not_after = request
        .headers()
        .get(&config.header_not_after)
        .and_then(|v| v.to_str().ok())
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|dt| dt.with_timezone(&Utc));

    // Validate expiry
    if let Some(ref expiry) = not_after {
        if expiry < &Utc::now() {
            let date_str = expiry.to_rfc3339();
            warn!(
                cert_fingerprint = &fingerprint[..8],
                not_after = %date_str,
                "Client certificate expired"
            );
            stats.expired.fetch_add(1, Ordering::Relaxed);
            metrics::record_mtls_validation("expired", "unknown");
            return Err(MtlsError::cert_expired(&date_str));
        }
    }

    // Validate issuer
    if !config.allowed_issuers.is_empty()
        && !config
            .allowed_issuers
            .iter()
            .any(|allowed| allowed == &issuer_dn)
    {
        warn!(
            cert_fingerprint = &fingerprint[..8],
            issuer = %issuer_dn,
            "Certificate issuer not in allowed list"
        );
        stats.denied.fetch_add(1, Ordering::Relaxed);
        metrics::record_mtls_validation("denied", "unknown");
        return Err(MtlsError::issuer_denied());
    }

    let truncated_fp = &fingerprint[..std::cmp::min(8, fingerprint.len())];
    debug!(
        cert_fingerprint = truncated_fp,
        subject = %subject_dn,
        issuer = %issuer_dn,
        "mTLS certificate extracted"
    );

    let cert_info = ClientCertInfo {
        fingerprint,
        subject_dn,
        issuer_dn,
        serial,
        not_before,
        not_after,
    };

    // Store in request extensions for Stage 3 and handlers
    request.extensions_mut().insert(cert_info);
    metrics::record_mtls_validation("success", "unknown");

    Ok(next.run(request).await)
}

// =============================================================================
// Stage 3: Certificate-Token Binding Verification
// =============================================================================

/// Verify RFC 8705 certificate-token binding.
///
/// Called after JWT auth. Compares cert fingerprint with cnf.x5t#S256.
pub fn verify_binding(
    cert_info: &ClientCertInfo,
    cnf_thumbprint: Option<&str>,
    require_binding: bool,
    stats: &MtlsStats,
) -> Result<(), MtlsError> {
    match cnf_thumbprint {
        None => {
            if require_binding {
                warn!(
                    cert_fingerprint = &cert_info.fingerprint[..8],
                    "JWT missing cnf claim but binding required"
                );
                stats.denied.fetch_add(1, Ordering::Relaxed);
                metrics::record_mtls_binding_check("denied");
                return Err(MtlsError::binding_required());
            }
            // Not required: warn and continue
            info!(
                cert_fingerprint = &cert_info.fingerprint[..8],
                "JWT has no cnf claim, binding not required — continuing"
            );
            stats.success.fetch_add(1, Ordering::Relaxed);
            metrics::record_mtls_binding_check("skipped");
            Ok(())
        }
        Some(thumbprint) => {
            // Compare: cert fingerprint (hex) vs cnf.x5t#S256 (base64url)
            match fingerprints_match(&cert_info.fingerprint, thumbprint) {
                Ok(true) => {
                    debug!(
                        cert_fingerprint = &cert_info.fingerprint[..8],
                        "Certificate-token binding verified"
                    );
                    stats.success.fetch_add(1, Ordering::Relaxed);
                    metrics::record_mtls_binding_check("match");
                    Ok(())
                }
                Ok(false) => {
                    warn!(
                        cert_fingerprint = &cert_info.fingerprint[..8],
                        "Certificate-token binding MISMATCH"
                    );
                    stats.mismatch.fetch_add(1, Ordering::Relaxed);
                    metrics::record_mtls_binding_check("mismatch");
                    Err(MtlsError::binding_mismatch())
                }
                Err(e) => {
                    warn!(
                        cert_fingerprint = &cert_info.fingerprint[..8],
                        error = %e,
                        "Fingerprint comparison error"
                    );
                    stats.invalid.fetch_add(1, Ordering::Relaxed);
                    metrics::record_mtls_binding_check("error");
                    Err(MtlsError::cert_invalid(&e))
                }
            }
        }
    }
}

// =============================================================================
// Stage 3 Middleware: Certificate-Token Binding Verification (RFC 8705)
// =============================================================================

/// Extract cnf.x5t#S256 from a raw JWT token (base64 decode only, no signature check).
fn extract_cnf_from_jwt(token: &str) -> Option<String> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 3 {
        return None;
    }
    let bytes = URL_SAFE_NO_PAD.decode(parts[1]).ok()?;
    let value: serde_json::Value = serde_json::from_slice(&bytes).ok()?;
    value
        .get("cnf")?
        .get("x5t#S256")?
        .as_str()
        .map(|s| s.to_string())
}

/// Middleware: verify RFC 8705 certificate-token binding.
///
/// Runs after Stage 1 (extraction). Compares cert fingerprint from X-SSL-* headers
/// with cnf.x5t#S256 from the JWT. Returns 403 on mismatch (stolen token detection).
pub async fn mtls_binding_middleware(
    config: MtlsConfig,
    stats: std::sync::Arc<MtlsStats>,
    request: Request<Body>,
    next: Next,
) -> Response {
    if !config.enabled || !config.require_binding {
        return next.run(request).await;
    }

    // OAuth/MCP/discovery paths bypass mTLS binding — they use Bearer auth
    let path = request.uri().path().to_string();
    if is_mtls_bypass_path(&path) {
        return next.run(request).await;
    }

    // Check if cert info was extracted by Stage 1
    let cert_info = request.extensions().get::<ClientCertInfo>().cloned();
    let Some(cert) = cert_info else {
        // No cert: Stage 1 already handled (passed for non-required routes, rejected for required)
        return next.run(request).await;
    };

    // Extract cnf from JWT Authorization header
    let cnf_thumbprint = request
        .headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|auth| auth.strip_prefix("Bearer "))
        .and_then(extract_cnf_from_jwt);

    if let Err(err) = verify_binding(
        &cert,
        cnf_thumbprint.as_deref(),
        config.require_binding,
        &stats,
    ) {
        return err.into_response();
    }

    next.run(request).await
}

// =============================================================================
// Forward Headers (downstream)
// =============================================================================

/// Header names for forwarding cert info downstream.
pub const HEADER_AUTHENTICATED_FINGERPRINT: &str = "X-Authenticated-Client-Fingerprint";
pub const HEADER_AUTHENTICATED_SUBJECT: &str = "X-Authenticated-Client-Subject";

/// Insert downstream forwarding headers from cert info.
///
/// Fingerprint is truncated to first 16 chars for security.
pub fn insert_forward_headers(response: &mut Response, cert_info: &ClientCertInfo) {
    let truncated = &cert_info.fingerprint[..std::cmp::min(16, cert_info.fingerprint.len())];
    if let Ok(val) = axum::http::HeaderValue::from_str(truncated) {
        response
            .headers_mut()
            .insert(HEADER_AUTHENTICATED_FINGERPRINT, val);
    }
    if let Ok(val) = axum::http::HeaderValue::from_str(&cert_info.subject_dn) {
        response
            .headers_mut()
            .insert(HEADER_AUTHENTICATED_SUBJECT, val);
    }
}

// =============================================================================
// Admin Response Types
// =============================================================================

#[derive(Debug, Clone, Serialize)]
pub struct MtlsConfigResponse {
    pub enabled: bool,
    pub require_binding: bool,
    pub trusted_proxies_count: usize,
    pub allowed_issuers: Vec<String>,
    pub required_routes: Vec<String>,
    pub header_verify: String,
    pub header_fingerprint: String,
}

impl From<&MtlsConfig> for MtlsConfigResponse {
    fn from(config: &MtlsConfig) -> Self {
        Self {
            enabled: config.enabled,
            require_binding: config.require_binding,
            trusted_proxies_count: config.trusted_proxies.len(),
            allowed_issuers: config.allowed_issuers.clone(),
            required_routes: config.required_routes.clone(),
            header_verify: config.header_verify.clone(),
            header_fingerprint: config.header_fingerprint.clone(),
        }
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // -------------------------------------------------------------------------
    // Fingerprint normalization
    // -------------------------------------------------------------------------

    #[test]
    fn test_normalize_hex() {
        let hex = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let result = normalize_fingerprint_to_hex(hex).unwrap();
        assert_eq!(result, hex);
    }

    #[test]
    fn test_normalize_hex_uppercase() {
        let hex = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2";
        let result = normalize_fingerprint_to_hex(hex).unwrap();
        assert_eq!(
            result,
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        );
    }

    #[test]
    fn test_normalize_hex_colons() {
        let colons = "a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2";
        let result = normalize_fingerprint_to_hex(colons).unwrap();
        assert_eq!(
            result,
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        );
    }

    #[test]
    fn test_normalize_base64url() {
        // 32 bytes of zeros → base64url = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        let zeros = [0u8; 32];
        let b64 = URL_SAFE_NO_PAD.encode(zeros);
        let result = normalize_fingerprint_to_hex(&b64).unwrap();
        assert_eq!(
            result,
            "0000000000000000000000000000000000000000000000000000000000000000"
        );
    }

    #[test]
    fn test_normalize_base64url_roundtrip() {
        let hex = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let bytes = hex::decode(hex).unwrap();
        let b64 = URL_SAFE_NO_PAD.encode(&bytes);
        let result = normalize_fingerprint_to_hex(&b64).unwrap();
        assert_eq!(result, hex);
    }

    // -------------------------------------------------------------------------
    // Fingerprint comparison (timing-safe)
    // -------------------------------------------------------------------------

    #[test]
    fn test_fingerprints_match_same_hex() {
        let fp = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        assert!(fingerprints_match(fp, fp).unwrap());
    }

    #[test]
    fn test_fingerprints_match_hex_vs_base64url() {
        let hex_fp = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let bytes = hex::decode(hex_fp).unwrap();
        let b64_fp = URL_SAFE_NO_PAD.encode(&bytes);
        assert!(fingerprints_match(hex_fp, &b64_fp).unwrap());
    }

    #[test]
    fn test_fingerprints_mismatch() {
        let fp_a = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let fp_b = "0000000000000000000000000000000000000000000000000000000000000000";
        assert!(!fingerprints_match(fp_a, fp_b).unwrap());
    }

    #[test]
    fn test_fingerprints_match_hex_colons_vs_hex() {
        let hex = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let colons = "a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2";
        assert!(fingerprints_match(hex, colons).unwrap());
    }

    // -------------------------------------------------------------------------
    // Trusted proxy
    // -------------------------------------------------------------------------

    #[test]
    fn test_trusted_proxy_empty_allows_all() {
        let ip: IpAddr = "192.168.1.1".parse().unwrap();
        assert!(is_trusted_proxy(&ip, &[]));
    }

    #[test]
    fn test_trusted_proxy_cidr_match() {
        let ip: IpAddr = "10.0.1.50".parse().unwrap();
        let proxies = vec!["10.0.0.0/8".to_string()];
        assert!(is_trusted_proxy(&ip, &proxies));
    }

    #[test]
    fn test_trusted_proxy_cidr_no_match() {
        let ip: IpAddr = "192.168.1.1".parse().unwrap();
        let proxies = vec!["10.0.0.0/8".to_string()];
        assert!(!is_trusted_proxy(&ip, &proxies));
    }

    #[test]
    fn test_trusted_proxy_exact_ip() {
        let ip: IpAddr = "10.0.1.5".parse().unwrap();
        let proxies = vec!["10.0.1.5".to_string()];
        assert!(is_trusted_proxy(&ip, &proxies));
    }

    // -------------------------------------------------------------------------
    // Required routes
    // -------------------------------------------------------------------------

    #[test]
    fn test_required_route_wildcard() {
        assert!(is_required_route("/api/v1/anything", &["/*".to_string()]));
    }

    #[test]
    fn test_required_route_prefix_match() {
        assert!(is_required_route(
            "/api/v1/payments/123",
            &["/api/v1/payments/*".to_string()]
        ));
    }

    #[test]
    fn test_required_route_no_match() {
        assert!(!is_required_route(
            "/api/v1/users/123",
            &["/api/v1/payments/*".to_string()]
        ));
    }

    #[test]
    fn test_required_route_exact_match() {
        assert!(is_required_route(
            "/api/v1/payments",
            &["/api/v1/payments".to_string()]
        ));
    }

    #[test]
    fn test_required_route_empty_no_match() {
        assert!(!is_required_route("/api/v1/payments", &[]));
    }

    // -------------------------------------------------------------------------
    // Format detection
    // -------------------------------------------------------------------------

    #[test]
    fn test_detect_hex_colons() {
        assert_eq!(detect_format("a1:b2:c3"), FingerprintFormat::HexColons);
    }

    #[test]
    fn test_detect_hex() {
        let hex = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        assert_eq!(detect_format(hex), FingerprintFormat::Hex);
    }

    #[test]
    fn test_detect_base64url() {
        let b64 = "obsz1234567890abcdefghijklmnopqrstuvwxyz_-A";
        assert_eq!(detect_format(b64), FingerprintFormat::Base64Url);
    }

    // -------------------------------------------------------------------------
    // Binding verification
    // -------------------------------------------------------------------------

    #[test]
    fn test_verify_binding_match() {
        let hex = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let bytes = hex::decode(hex).unwrap();
        let b64 = URL_SAFE_NO_PAD.encode(&bytes);

        let cert = ClientCertInfo {
            fingerprint: hex.to_string(),
            subject_dn: "CN=test".to_string(),
            issuer_dn: "CN=ca".to_string(),
            serial: "01".to_string(),
            not_before: None,
            not_after: None,
        };

        let stats = MtlsStats::new();
        assert!(verify_binding(&cert, Some(&b64), true, &stats).is_ok());
        assert_eq!(stats.success.load(Ordering::Relaxed), 1);
    }

    #[test]
    fn test_verify_binding_mismatch() {
        let hex = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
        let other_bytes = [0u8; 32];
        let other_b64 = URL_SAFE_NO_PAD.encode(other_bytes);

        let cert = ClientCertInfo {
            fingerprint: hex.to_string(),
            subject_dn: "CN=test".to_string(),
            issuer_dn: "CN=ca".to_string(),
            serial: "01".to_string(),
            not_before: None,
            not_after: None,
        };

        let stats = MtlsStats::new();
        let result = verify_binding(&cert, Some(&other_b64), true, &stats);
        assert!(result.is_err());
        assert_eq!(stats.mismatch.load(Ordering::Relaxed), 1);
    }

    #[test]
    fn test_verify_binding_no_cnf_required() {
        let cert = ClientCertInfo {
            fingerprint: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
                .to_string(),
            subject_dn: "CN=test".to_string(),
            issuer_dn: "CN=ca".to_string(),
            serial: "01".to_string(),
            not_before: None,
            not_after: None,
        };

        let stats = MtlsStats::new();
        let result = verify_binding(&cert, None, true, &stats);
        assert!(result.is_err());
        assert_eq!(stats.denied.load(Ordering::Relaxed), 1);
    }

    #[test]
    fn test_verify_binding_no_cnf_not_required() {
        let cert = ClientCertInfo {
            fingerprint: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
                .to_string(),
            subject_dn: "CN=test".to_string(),
            issuer_dn: "CN=ca".to_string(),
            serial: "01".to_string(),
            not_before: None,
            not_after: None,
        };

        let stats = MtlsStats::new();
        let result = verify_binding(&cert, None, false, &stats);
        assert!(result.is_ok());
        assert_eq!(stats.success.load(Ordering::Relaxed), 1);
    }

    // -------------------------------------------------------------------------
    // Config response
    // -------------------------------------------------------------------------

    #[test]
    fn test_mtls_config_response() {
        let config = MtlsConfig::default();
        let response = MtlsConfigResponse::from(&config);
        assert!(!response.enabled);
        assert!(response.require_binding);
        assert_eq!(response.trusted_proxies_count, 0);
    }

    // -------------------------------------------------------------------------
    // Stats
    // -------------------------------------------------------------------------

    #[test]
    fn test_mtls_stats_snapshot() {
        let stats = MtlsStats::new();
        stats.success.fetch_add(5, Ordering::Relaxed);
        stats.mismatch.fetch_add(2, Ordering::Relaxed);
        let snap = stats.snapshot();
        assert_eq!(snap.success, 5);
        assert_eq!(snap.mismatch, 2);
        assert_eq!(snap.no_cert, 0);
    }

    // -------------------------------------------------------------------------
    // Error types
    // -------------------------------------------------------------------------

    #[test]
    fn test_mtls_error_status_codes() {
        use axum::response::IntoResponse;

        let err = MtlsError::cert_required();
        let resp = err.into_response();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        let err = MtlsError::cert_invalid("test");
        let resp = err.into_response();
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);

        let err = MtlsError::binding_mismatch();
        let resp = err.into_response();
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    }

    // -------------------------------------------------------------------------
    // Hex module
    // -------------------------------------------------------------------------

    #[test]
    fn test_hex_encode_decode() {
        let data = vec![0xa1, 0xb2, 0xc3, 0xd4];
        let encoded = hex::encode(&data);
        assert_eq!(encoded, "a1b2c3d4");
        let decoded = hex::decode(&encoded).unwrap();
        assert_eq!(decoded, data);
    }

    #[test]
    fn test_hex_decode_invalid() {
        assert!(hex::decode("zz").is_err());
        assert!(hex::decode("abc").is_err()); // odd length
    }

    // -------------------------------------------------------------------------
    // mTLS bypass paths (OAuth/MCP/discovery coexistence)
    // -------------------------------------------------------------------------

    #[test]
    fn test_bypass_oauth_paths() {
        assert!(is_mtls_bypass_path("/.well-known/oauth-protected-resource"));
        assert!(is_mtls_bypass_path(
            "/.well-known/oauth-authorization-server"
        ));
        assert!(is_mtls_bypass_path("/oauth/register"));
        assert!(is_mtls_bypass_path("/oauth/token"));
        assert!(is_mtls_bypass_path("/oauth/authorize"));
    }

    #[test]
    fn test_bypass_mcp_paths() {
        assert!(is_mtls_bypass_path("/mcp"));
        assert!(is_mtls_bypass_path("/mcp/sse"));
        assert!(is_mtls_bypass_path("/mcp/sse?session=abc"));
        assert!(is_mtls_bypass_path("/mcp/capabilities"));
        assert!(is_mtls_bypass_path("/mcp/health"));
        assert!(is_mtls_bypass_path("/mcp/tools/list"));
        assert!(is_mtls_bypass_path("/mcp/v1/sse"));
    }

    #[test]
    fn test_bypass_infra_paths() {
        assert!(is_mtls_bypass_path("/health"));
        assert!(is_mtls_bypass_path("/health/live"));
        assert!(is_mtls_bypass_path("/ready"));
        assert!(is_mtls_bypass_path("/metrics"));
        assert!(is_mtls_bypass_path("/metrics/prometheus"));
    }

    #[test]
    fn test_no_bypass_api_proxy_paths() {
        assert!(!is_mtls_bypass_path("/api/v1/payments"));
        assert!(!is_mtls_bypass_path("/api/v1/users/123"));
        assert!(!is_mtls_bypass_path("/proxy/backend"));
        assert!(!is_mtls_bypass_path("/admin/apis"));
        assert!(!is_mtls_bypass_path("/admin/health"));
        assert!(!is_mtls_bypass_path("/"));
    }
}
