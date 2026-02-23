//! Hop detection via RFC 9110 §7.6.3 Via header parsing.
//!
//! Parses Via headers from HTTP responses to identify intermediary proxies
//! and count network hops between the gateway and the backend.

use axum::http::HeaderMap;
use serde::Serialize;

/// A single intermediary hop parsed from a Via header.
#[derive(Debug, Clone, Serialize)]
pub struct HopInfo {
    /// HTTP protocol version (e.g. "1.1", "2.0").
    pub protocol: String,
    /// Pseudonym or hostname of the intermediary.
    pub pseudonym: String,
    /// Optional comment from the Via header.
    pub comment: Option<String>,
}

/// Aggregated hop chain from all Via headers in a response.
#[derive(Debug, Clone, Serialize)]
pub struct HopChain {
    pub hops: Vec<HopInfo>,
    pub total_hops: usize,
    pub detected_intermediaries: Vec<String>,
}

/// Parse all Via headers from a response HeaderMap.
///
/// Via header format (RFC 9110 §7.6.3):
///   Via = #( received-protocol RWS received-by [ RWS comment ] )
///   received-protocol = [ protocol-name "/" ] protocol-version
///   received-by = pseudonym [ ":" port ]
///
/// Example: `1.1 proxy-a, 2.0 cdn.example.com (CDN edge)`
pub fn parse_via_headers(headers: &HeaderMap) -> HopChain {
    let mut hops = Vec::new();

    for value in headers.get_all("via") {
        let Ok(s) = value.to_str() else { continue };
        // Each Via header can contain multiple comma-separated entries
        for entry in s.split(',') {
            if let Some(hop) = parse_single_via(entry.trim()) {
                hops.push(hop);
            }
        }
    }

    let total_hops = hops.len();
    let detected_intermediaries: Vec<String> = hops.iter().map(|h| h.pseudonym.clone()).collect();

    HopChain {
        hops,
        total_hops,
        detected_intermediaries,
    }
}

/// Parse a single Via entry: "1.1 proxy-name (optional comment)"
fn parse_single_via(entry: &str) -> Option<HopInfo> {
    if entry.is_empty() {
        return None;
    }

    // Extract optional comment in parentheses
    let (main_part, comment) = if let Some(paren_start) = entry.find('(') {
        let comment_end = entry.rfind(')').unwrap_or(entry.len());
        let comment = entry[paren_start + 1..comment_end].trim().to_string();
        (entry[..paren_start].trim(), Some(comment))
    } else {
        (entry, None)
    };

    // Split into protocol and pseudonym
    let mut parts = main_part.splitn(2, char::is_whitespace);
    let protocol_raw = parts.next()?.trim();
    let pseudonym = parts.next().unwrap_or("unknown").trim().to_string();

    // Protocol may include name: "HTTP/1.1" or just version: "1.1"
    let protocol = if let Some((_name, version)) = protocol_raw.split_once('/') {
        version.to_string()
    } else {
        protocol_raw.to_string()
    };

    if pseudonym.is_empty() {
        return None;
    }

    Some(HopInfo {
        protocol,
        pseudonym,
        comment,
    })
}

/// Detect intermediaries from common proxy headers (beyond Via).
///
/// Checks `X-Forwarded-For`, `X-Forwarded-By`, and `Server` headers
/// for additional intermediary signals.
pub fn detect_intermediaries(headers: &HeaderMap) -> Vec<String> {
    let mut intermediaries = Vec::new();

    // X-Forwarded-For can reveal proxy chain
    if let Some(xff) = headers.get("x-forwarded-for") {
        if let Ok(s) = xff.to_str() {
            // Multiple IPs = multiple intermediaries
            let ips: Vec<&str> = s.split(',').map(|ip| ip.trim()).collect();
            if ips.len() > 1 {
                // All but the last are intermediaries (last is the original client)
                for ip in &ips[..ips.len() - 1] {
                    intermediaries.push(format!("xff:{ip}"));
                }
            }
        }
    }

    // Server header may reveal CDN/proxy
    if let Some(server) = headers.get("server") {
        if let Ok(s) = server.to_str() {
            let lower = s.to_lowercase();
            if lower.contains("cloudflare")
                || lower.contains("nginx")
                || lower.contains("envoy")
                || lower.contains("haproxy")
                || lower.contains("varnish")
                || lower.contains("cdn")
            {
                intermediaries.push(format!("server:{s}"));
            }
        }
    }

    intermediaries
}

/// Build the Via header value for outgoing requests from this gateway.
pub fn build_via_value() -> String {
    format!("1.1 stoa-gateway ({})", env!("CARGO_PKG_VERSION"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    #[test]
    fn test_parse_single_via_header() {
        let mut headers = HeaderMap::new();
        headers.insert("via", HeaderValue::from_static("1.1 proxy-a"));

        let chain = parse_via_headers(&headers);
        assert_eq!(chain.total_hops, 1);
        assert_eq!(chain.hops[0].protocol, "1.1");
        assert_eq!(chain.hops[0].pseudonym, "proxy-a");
        assert!(chain.hops[0].comment.is_none());
    }

    #[test]
    fn test_parse_multiple_via_headers() {
        let mut headers = HeaderMap::new();
        headers.insert("via", HeaderValue::from_static("1.1 proxy-a, 2.0 cdn-edge"));

        let chain = parse_via_headers(&headers);
        assert_eq!(chain.total_hops, 2);
        assert_eq!(chain.hops[0].pseudonym, "proxy-a");
        assert_eq!(chain.hops[1].protocol, "2.0");
        assert_eq!(chain.hops[1].pseudonym, "cdn-edge");
        assert_eq!(chain.detected_intermediaries, vec!["proxy-a", "cdn-edge"]);
    }

    #[test]
    fn test_detect_intermediaries_from_server_header() {
        let mut headers = HeaderMap::new();
        headers.insert("server", HeaderValue::from_static("cloudflare"));

        let intermediaries = detect_intermediaries(&headers);
        assert_eq!(intermediaries.len(), 1);
        assert!(intermediaries[0].starts_with("server:"));
    }

    #[test]
    fn test_empty_headers_zero_hops() {
        let headers = HeaderMap::new();
        let chain = parse_via_headers(&headers);
        assert_eq!(chain.total_hops, 0);
        assert!(chain.hops.is_empty());
    }

    #[test]
    fn test_via_with_comment() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "via",
            HeaderValue::from_static("HTTP/1.1 cdn.example.com (CDN edge node)"),
        );

        let chain = parse_via_headers(&headers);
        assert_eq!(chain.total_hops, 1);
        assert_eq!(chain.hops[0].protocol, "1.1");
        assert_eq!(chain.hops[0].pseudonym, "cdn.example.com");
        assert_eq!(chain.hops[0].comment.as_deref(), Some("CDN edge node"));
    }
}
