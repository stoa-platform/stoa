//! TCP early filter — pre-HTTP IP blocklist + rate limiting (CAB-1830).
//!
//! Runs as the outermost middleware layer, rejecting connections from
//! blocked IPs or rate-limited IPs before any HTTP/TLS processing.
//! Hook point: immediately after `TcpListener::accept()` via ConnectInfo.

use std::collections::{HashMap, HashSet};
use std::net::{IpAddr, SocketAddr};
use std::sync::Arc;
use std::time::Instant;

use axum::extract::ConnectInfo;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use ipnet::IpNet;
use parking_lot::Mutex;
use tracing::warn;

use crate::config::Config;

/// TCP-level connection filter: IP blocklist (HashSet O(1) + CIDR) and per-IP rate limiting.
pub struct TcpFilter {
    blocked_ips: HashSet<IpAddr>,
    blocked_cidrs: Vec<IpNet>,
    rate_limiter: Option<RateLimiter>,
}

struct RateLimiter {
    rate: f64,
    buckets: Mutex<HashMap<IpAddr, TokenBucket>>,
}

struct TokenBucket {
    tokens: f64,
    last_refill: Instant,
}

impl TcpFilter {
    /// Build from gateway config. Parses `STOA_IP_BLOCKLIST` (comma-separated)
    /// and `STOA_IP_BLOCKLIST_FILE` (one entry per line). Each entry is an IP or CIDR.
    pub fn from_config(config: &Config) -> Self {
        let mut blocked_ips = HashSet::new();
        let mut blocked_cidrs = Vec::new();

        // Parse comma-separated blocklist env var
        let entries = config
            .ip_blocklist
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());

        // Parse file-based blocklist (one IP/CIDR per line)
        let file_entries = config.ip_blocklist_file.as_deref().and_then(|path| {
            std::fs::read_to_string(path)
                .map_err(|e| warn!(path, error = %e, "failed to read IP blocklist file"))
                .ok()
        });
        let file_iter = file_entries
            .iter()
            .flat_map(|content| content.lines().map(|l| l.trim().to_string()))
            .filter(|s| !s.is_empty() && !s.starts_with('#'));

        for entry in entries.chain(file_iter) {
            if let Ok(net) = entry.parse::<IpNet>() {
                // Single-host CIDRs (/32 or /128) go to HashSet for O(1) lookup
                if is_single_host(&net) {
                    blocked_ips.insert(net.addr());
                } else {
                    blocked_cidrs.push(net);
                }
            } else if let Ok(ip) = entry.parse::<IpAddr>() {
                blocked_ips.insert(ip);
            } else {
                warn!(entry, "tcp_filter: invalid blocklist entry, skipping");
            }
        }

        let rate_limiter = config
            .tcp_rate_limit_per_ip
            .filter(|&r| r > 0.0)
            .map(|rate| RateLimiter {
                rate,
                buckets: Mutex::new(HashMap::new()),
            });

        tracing::info!(
            blocked_ips = blocked_ips.len(),
            blocked_cidrs = blocked_cidrs.len(),
            rate_limit = ?config.tcp_rate_limit_per_ip,
            "TCP filter initialized"
        );

        Self {
            blocked_ips,
            blocked_cidrs,
            rate_limiter,
        }
    }

    /// Returns `true` if the IP is allowed, `false` if rejected.
    pub fn check(&self, ip: &IpAddr) -> bool {
        // O(1) exact match
        if self.blocked_ips.contains(ip) {
            return false;
        }
        // CIDR scan
        for cidr in &self.blocked_cidrs {
            if cidr.contains(ip) {
                return false;
            }
        }
        // Token bucket rate limit
        if let Some(limiter) = &self.rate_limiter {
            return limiter.allow(ip);
        }
        true
    }

    /// Returns true if the filter has any rules configured.
    pub fn is_enabled(&self) -> bool {
        !self.blocked_ips.is_empty()
            || !self.blocked_cidrs.is_empty()
            || self.rate_limiter.is_some()
    }
}

fn is_single_host(net: &IpNet) -> bool {
    match net {
        IpNet::V4(v4) => v4.prefix_len() == 32,
        IpNet::V6(v6) => v6.prefix_len() == 128,
    }
}

impl RateLimiter {
    fn allow(&self, ip: &IpAddr) -> bool {
        let mut buckets = self.buckets.lock();
        let now = Instant::now();
        let bucket = buckets.entry(*ip).or_insert_with(|| TokenBucket {
            tokens: self.rate,
            last_refill: now,
        });

        let elapsed = now.duration_since(bucket.last_refill).as_secs_f64();
        bucket.tokens = (bucket.tokens + elapsed * self.rate).min(self.rate);
        bucket.last_refill = now;

        if bucket.tokens >= 1.0 {
            bucket.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

/// Outermost middleware: rejects blocked or rate-limited IPs before HTTP processing.
/// Named `pre_tls_filter` per CAB-1830 spec — runs at the earliest point after accept().
pub async fn pre_tls_filter(
    filter: Arc<TcpFilter>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    // Extract peer address from ConnectInfo (set by into_make_service_with_connect_info)
    let peer_ip = request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map(|ci| ci.0.ip());

    if let Some(ip) = peer_ip {
        if !filter.check(&ip) {
            crate::metrics::TCP_CONNECTIONS_REJECTED_PRE_TLS
                .with_label_values(&[reject_reason(&filter, &ip)])
                .inc();
            warn!(peer = %ip, "connection rejected pre-TLS (blocklist/rate-limit)");
            return StatusCode::FORBIDDEN.into_response();
        }
    }

    next.run(request).await
}

/// Determine the rejection reason for metrics labeling.
fn reject_reason(filter: &TcpFilter, ip: &IpAddr) -> &'static str {
    if filter.blocked_ips.contains(ip) {
        return "blocklist_ip";
    }
    for cidr in &filter.blocked_cidrs {
        if cidr.contains(ip) {
            return "blocklist_cidr";
        }
    }
    "rate_limit"
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config_blocklist(entries: &str) -> Config {
        Config {
            ip_blocklist: entries.to_string(),
            ..Config::default()
        }
    }

    #[test]
    fn test_exact_ip_blocked() {
        let filter = TcpFilter::from_config(&config_blocklist("1.2.3.4"));
        assert!(!filter.check(&"1.2.3.4".parse().unwrap()));
        assert!(filter.check(&"1.2.3.5".parse().unwrap()));
    }

    #[test]
    fn test_cidr_blocked() {
        let filter = TcpFilter::from_config(&config_blocklist("10.0.0.0/8"));
        assert!(!filter.check(&"10.1.2.3".parse().unwrap()));
        assert!(filter.check(&"11.0.0.1".parse().unwrap()));
    }

    #[test]
    fn test_ipv6_blocked() {
        let filter = TcpFilter::from_config(&config_blocklist("fd00::/8"));
        assert!(!filter.check(&"fd00::1".parse().unwrap()));
        assert!(filter.check(&"2001:db8::1".parse().unwrap()));
    }

    #[test]
    fn test_empty_blocklist_allows_all() {
        let filter = TcpFilter::from_config(&config_blocklist(""));
        assert!(filter.check(&"1.2.3.4".parse().unwrap()));
        assert!(!filter.is_enabled());
    }

    #[test]
    fn test_multiple_entries() {
        let filter = TcpFilter::from_config(&config_blocklist("1.2.3.4, 10.0.0.0/8, ::1"));
        assert!(!filter.check(&"1.2.3.4".parse().unwrap()));
        assert!(!filter.check(&"10.255.0.1".parse().unwrap()));
        assert!(!filter.check(&"::1".parse().unwrap()));
        assert!(filter.check(&"8.8.8.8".parse().unwrap()));
    }

    #[test]
    fn test_single_host_cidr_uses_hashset() {
        let filter = TcpFilter::from_config(&config_blocklist("1.2.3.4/32"));
        assert!(!filter.check(&"1.2.3.4".parse().unwrap()));
        assert!(filter
            .blocked_ips
            .contains(&"1.2.3.4".parse::<IpAddr>().unwrap()));
        assert!(filter.blocked_cidrs.is_empty());
    }

    #[test]
    fn test_rate_limiter_basic() {
        let config = Config {
            tcp_rate_limit_per_ip: Some(2.0),
            ..Config::default()
        };
        let filter = TcpFilter::from_config(&config);
        let ip: IpAddr = "1.2.3.4".parse().unwrap();

        assert!(filter.check(&ip));
        assert!(filter.check(&ip));
        assert!(!filter.check(&ip)); // exhausted
    }

    #[test]
    fn test_rate_limiter_per_ip_isolation() {
        let config = Config {
            tcp_rate_limit_per_ip: Some(1.0),
            ..Config::default()
        };
        let filter = TcpFilter::from_config(&config);
        let ip1: IpAddr = "1.1.1.1".parse().unwrap();
        let ip2: IpAddr = "2.2.2.2".parse().unwrap();

        assert!(filter.check(&ip1));
        assert!(filter.check(&ip2));
        assert!(!filter.check(&ip1));
    }

    #[test]
    fn test_blocklist_checked_before_rate_limit() {
        let config = Config {
            ip_blocklist: "5.5.5.5".to_string(),
            tcp_rate_limit_per_ip: Some(100.0),
            ..Config::default()
        };
        let filter = TcpFilter::from_config(&config);

        assert!(!filter.check(&"5.5.5.5".parse().unwrap()));
        assert!(filter.check(&"6.6.6.6".parse().unwrap()));
    }

    #[test]
    fn test_invalid_entry_skipped() {
        let filter = TcpFilter::from_config(&config_blocklist("1.2.3.4, not-an-ip, 10.0.0.0/8"));
        assert!(!filter.check(&"1.2.3.4".parse().unwrap()));
        assert!(!filter.check(&"10.0.0.1".parse().unwrap()));
        assert!(filter.check(&"11.0.0.1".parse().unwrap()));
    }

    #[test]
    fn test_reject_reason() {
        let filter = TcpFilter::from_config(&config_blocklist("1.2.3.4, 10.0.0.0/8"));
        assert_eq!(
            reject_reason(&filter, &"1.2.3.4".parse().unwrap()),
            "blocklist_ip"
        );
        assert_eq!(
            reject_reason(&filter, &"10.0.0.1".parse().unwrap()),
            "blocklist_cidr"
        );
        assert_eq!(
            reject_reason(&filter, &"8.8.8.8".parse().unwrap()),
            "rate_limit"
        );
    }
}
