//! Client IP and scheme behind a trusted proxy chain.
//!
//! `STOA_TRUSTED_PROXIES` is a list of CIDRs (or single IPs). When it is
//! non-empty, `X-Forwarded-For`, `X-Real-IP`, and `X-Forwarded-Proto` are
//! honored only if the TCP peer is inside that list. The client is the first
//! address from the right of `X-Forwarded-For` that is not itself a trusted
//! proxy, so a caller cannot spoof the leftmost hop.
//!
//! An empty list keeps the historical behaviour: leftmost `X-Forwarded-For`,
//! and the scheme stays `http` (forwarded proto is not trusted).

use ipnet::IpNet;
use std::net::IpAddr;

/// Client address and scheme after trusted-proxy resolution.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ForwardedClient {
    pub client_ip: String,
    pub scheme: String,
}

/// Resolve the client IP and scheme for one request.
///
/// `peer_ip` is the TCP peer (`ConnectInfo`). Header values are the raw
/// header strings, not split.
pub fn resolve_forwarded(
    peer_ip: Option<&str>,
    x_forwarded_for: Option<&str>,
    x_real_ip: Option<&str>,
    x_forwarded_proto: Option<&str>,
    trusted_proxies: &[String],
) -> ForwardedClient {
    let peer = peer_ip.unwrap_or("-").to_string();
    if trusted_proxies.is_empty() {
        let client_ip = leftmost_hop(x_forwarded_for)
            .or_else(|| non_empty(x_real_ip))
            .unwrap_or(peer);
        return ForwardedClient {
            client_ip,
            scheme: "http".to_string(),
        };
    }

    let peer_addr = peer_ip.and_then(|ip| ip.parse::<IpAddr>().ok());
    let peer_trusted = peer_addr.is_some_and(|ip| ip_is_trusted(ip, trusted_proxies));
    if !peer_trusted {
        return ForwardedClient {
            client_ip: peer,
            scheme: "http".to_string(),
        };
    }

    let client_ip = client_from_chain(x_forwarded_for, trusted_proxies)
        .or_else(|| non_empty(x_real_ip))
        .unwrap_or(peer);
    ForwardedClient {
        client_ip,
        scheme: forwarded_scheme(x_forwarded_proto),
    }
}

fn non_empty(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}

fn leftmost_hop(xff: Option<&str>) -> Option<String> {
    xff.and_then(|value| {
        value
            .split(',')
            .next()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
    })
}

/// Walk `X-Forwarded-For` from the right, skipping trusted proxies.
///
/// If every parsed hop is trusted, the leftmost hop is the original client
/// (it is itself on the trusted list). Unparseable hops are ignored.
fn client_from_chain(xff: Option<&str>, trusted: &[String]) -> Option<String> {
    let ips: Vec<IpAddr> = xff?
        .split(',')
        .filter_map(|hop| hop.trim().parse::<IpAddr>().ok())
        .collect();
    if ips.is_empty() {
        return None;
    }
    let mut index = ips.len();
    while index > 0 {
        index -= 1;
        if !ip_is_trusted(ips[index], trusted) {
            return Some(ips[index].to_string());
        }
    }
    Some(ips[0].to_string())
}

fn forwarded_scheme(proto: Option<&str>) -> String {
    proto
        .and_then(|value| value.split(',').next())
        .map(|value| value.trim().to_ascii_lowercase())
        .filter(|value| value == "http" || value == "https")
        .unwrap_or_else(|| "http".to_string())
}

fn ip_is_trusted(ip: IpAddr, trusted: &[String]) -> bool {
    trusted.iter().any(|entry| {
        let entry = entry.trim();
        if entry.is_empty() {
            return false;
        }
        if let Ok(net) = entry.parse::<IpNet>() {
            return net.contains(&ip);
        }
        entry.parse::<IpAddr>().is_ok_and(|single| single == ip)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trusted() -> Vec<String> {
        vec![
            "10.42.0.0/16".to_string(),
            "104.16.0.0/13".to_string(),
            "173.245.48.0/20".to_string(),
        ]
    }

    #[test]
    fn empty_list_keeps_leftmost_forwarded_for_and_ignores_proto() {
        let got = resolve_forwarded(
            Some("10.42.0.8"),
            Some("1.1.1.1, 203.0.113.5"),
            None,
            Some("https"),
            &[],
        );
        assert_eq!(got.client_ip, "1.1.1.1");
        assert_eq!(got.scheme, "http");
    }

    #[test]
    fn trusted_peer_skips_cloudflare_and_uses_real_client() {
        // Client prepended a spoof; ingress (pod CIDR) appended nothing extra
        // because Cloudflare is already the rightmost XFF hop.
        let got = resolve_forwarded(
            Some("10.42.1.9"),
            Some("1.1.1.1, 203.0.113.50, 104.16.1.2"),
            None,
            Some("https"),
            &trusted(),
        );
        assert_eq!(got.client_ip, "203.0.113.50");
        assert_eq!(got.scheme, "https");
    }

    #[test]
    fn untrusted_peer_ignores_forwarded_headers() {
        let got = resolve_forwarded(
            Some("203.0.113.9"),
            Some("1.1.1.1"),
            Some("8.8.8.8"),
            Some("https"),
            &trusted(),
        );
        assert_eq!(got.client_ip, "203.0.113.9");
        assert_eq!(got.scheme, "http");
    }

    #[test]
    fn trusted_peer_without_xff_uses_x_real_ip() {
        let got = resolve_forwarded(
            Some("10.42.0.2"),
            None,
            Some("198.51.100.20"),
            Some("http"),
            &trusted(),
        );
        assert_eq!(got.client_ip, "198.51.100.20");
        assert_eq!(got.scheme, "http");
    }

    #[test]
    fn unknown_proto_falls_back_to_http() {
        let got = resolve_forwarded(
            Some("10.42.0.2"),
            Some("203.0.113.7"),
            None,
            Some("spdy"),
            &trusted(),
        );
        assert_eq!(got.scheme, "http");
    }
}
