//! Outbound address policy with DNS resolution and resolved-address pinning
//! for dynamic MCP tool and OAuth2 HTTP requests.
//!
//! Resolves target hostnames to IPv4/IPv6 socket addresses before connecting,
//! rejects private/internal/special-use addresses unless the exact normalized
//! origin is explicitly allowlisted (for local isolated test mocks), disables
//! HTTP redirects, and pins `reqwest` to the validated resolved addresses.

use std::collections::HashSet;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use std::time::Duration;

use reqwest::Client;
use thiserror::Error;
use tracing::warn;
use url::Url;

use crate::proxy::credentials::normalize_origin;

/// Errors raised when an outbound URL is refused by [`OutboundAddressPolicy`].
#[derive(Debug, Error)]
pub enum OutboundPolicyError {
    #[error("invalid outbound URL")]
    InvalidUrl,

    #[error("unsupported URL scheme (only http and https are allowed)")]
    UnsupportedScheme,

    #[error("DNS resolution failed")]
    DnsResolutionFailed,

    #[error("resolved address is in a blocked range")]
    BlockedAddress,

    #[error("failed to construct pinned HTTP client")]
    ClientBuildFailed,
}

/// Outbound address policy with DNS resolution and resolved-address pinning.
#[derive(Debug, Clone, Default)]
pub struct OutboundAddressPolicy {
    /// Exact normalized origins (`scheme://host:port`) permitted to resolve to
    /// private/internal addresses (used strictly for isolated local mock fixtures).
    allowed_origins: HashSet<String>,
}

impl OutboundAddressPolicy {
    /// Create a policy with an optional allowlist of normalized origins.
    pub fn new<I, S>(allowed_origins: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let set = allowed_origins
            .into_iter()
            .filter_map(|origin| normalize_origin(origin.as_ref()))
            .collect();
        Self {
            allowed_origins: set,
        }
    }

    /// Resolve `raw_url` via DNS and verify every resolved IPv4/IPv6 address.
    ///
    /// Returns `(host, validated_socket_addrs)` on success.
    pub async fn validate_url(
        &self,
        raw_url: &str,
    ) -> Result<(String, Vec<SocketAddr>), OutboundPolicyError> {
        let parsed = Url::parse(raw_url).map_err(|_| OutboundPolicyError::InvalidUrl)?;
        let scheme = parsed.scheme();
        if scheme != "http" && scheme != "https" {
            return Err(OutboundPolicyError::UnsupportedScheme);
        }
        if !parsed.username().is_empty() || parsed.password().is_some() {
            return Err(OutboundPolicyError::InvalidUrl);
        }
        let host = parsed
            .host_str()
            .filter(|h| !h.is_empty())
            .ok_or(OutboundPolicyError::InvalidUrl)?
            .to_ascii_lowercase();
        let port = parsed
            .port_or_known_default()
            .ok_or(OutboundPolicyError::InvalidUrl)?;
        let origin_key = format!("{scheme}://{host}:{port}");
        let origin_allowlisted = self.allowed_origins.contains(&origin_key);

        // Strip brackets for literal IPv6 hosts before lookup_host.
        let lookup_host = host.trim_start_matches('[').trim_end_matches(']');
        let addrs: Vec<SocketAddr> = tokio::net::lookup_host((lookup_host, port))
            .await
            .map_err(|_| OutboundPolicyError::DnsResolutionFailed)?
            .collect();

        if addrs.is_empty() {
            return Err(OutboundPolicyError::DnsResolutionFailed);
        }

        for addr in &addrs {
            let allowed = match classify_ip(addr.ip()) {
                AddressClass::Public => true,
                AddressClass::AllowlistableLocal => origin_allowlisted,
                AddressClass::AlwaysBlocked => false,
            };
            if !allowed {
                warn!(
                    host = %host,
                    port,
                    ip = %addr.ip(),
                    "Outbound address policy blocked target"
                );
                return Err(OutboundPolicyError::BlockedAddress);
            }
        }

        Ok((lookup_host.to_string(), addrs))
    }

    /// Validate `raw_url` and build a `reqwest::Client` pinned to the validated
    /// resolved socket addresses with proxies and redirects disabled.
    pub async fn validate_and_build_client(
        &self,
        raw_url: &str,
        timeout: Duration,
    ) -> Result<Client, OutboundPolicyError> {
        let (host, addrs) = self.validate_url(raw_url).await?;
        Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .resolve_to_addrs(&host, &addrs)
            .timeout(timeout)
            .build()
            .map_err(|_| OutboundPolicyError::ClientBuildFailed)
    }
}

/// Classification of an IP address under the outbound address policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AddressClass {
    /// Publicly routable global unicast address.
    Public,
    /// RFC 1918 private, IPv4/IPv6 loopback, or IPv6 ULA address: blocked by
    /// default and permitted ONLY when the exact normalized origin is allowlisted.
    AllowlistableLocal,
    /// Special-use address (link-local, unspecified, broadcast, multicast, CGNAT,
    /// documentation, benchmark, discard, Teredo, 6to4 relay, IETF protocol,
    /// site-local, local-use NAT64, reserved, or non-public embedded IPv4 in
    /// transition forms): ALWAYS rejected, even for allowlisted origins.
    AlwaysBlocked,
}

/// Returns `true` if `ip` is blocked by default (any non-public range).
pub fn is_blocked_ip(ip: IpAddr) -> bool {
    classify_ip(ip) != AddressClass::Public
}

fn classify_ip(ip: IpAddr) -> AddressClass {
    match ip {
        IpAddr::V4(v4) => classify_ipv4(v4),
        IpAddr::V6(v6) => classify_ipv6(v6),
    }
}

fn classify_ipv4(v4: Ipv4Addr) -> AddressClass {
    let o = v4.octets();
    let is_cgnat = o[0] == 100 && (o[1] & 0b1100_0000) == 64; // 100.64.0.0/10
    let is_current_net = o[0] == 0; // 0.0.0.0/8
    let is_ietf_proto = o[0] == 192 && o[1] == 0 && o[2] == 0; // 192.0.0.0/24
    let is_6to4_relay = o[0] == 192 && o[1] == 88 && o[2] == 99; // 192.88.99.0/24
    let is_benchmark = o[0] == 198 && (o[1] == 18 || o[1] == 19); // 198.18.0.0/15
    let is_reserved = o[0] >= 240; // 240.0.0.0/4

    if v4.is_link_local()
        || v4.is_unspecified()
        || v4.is_broadcast()
        || v4.is_multicast()
        || v4.is_documentation()
        || is_cgnat
        || is_current_net
        || is_ietf_proto
        || is_6to4_relay
        || is_benchmark
        || is_reserved
    {
        return AddressClass::AlwaysBlocked;
    }

    if v4.is_loopback() || v4.is_private() {
        return AddressClass::AllowlistableLocal;
    }

    AddressClass::Public
}

/// Extract an embedded IPv4 address from IPv6 transition/compatible formats:
/// - `::ffff:a.b.c.d` (IPv4-mapped)
/// - `::a.b.c.d` (deprecated IPv4-compatible, excluding `::` and `::1`)
/// - `::ffff:0:a.b.c.d` (RFC 2765 SIIT IPv4-translated)
/// - `64:ff9b::/96` (RFC 6052 well-known NAT64)
/// - `64:ff9b:1::/48` (RFC 8215 local-use NAT64)
/// - `2002::/16` (RFC 3056 6to4)
fn extract_embedded_ipv4(v6: Ipv6Addr) -> Option<Ipv4Addr> {
    if let Some(v4) = v6.to_ipv4_mapped() {
        return Some(v4);
    }
    let seg = v6.segments();
    let b = v6.octets();

    // `::a.b.c.d` (IPv4-compatible, excluding `::` and `::1` which are classified directly).
    if seg[0..6] == [0, 0, 0, 0, 0, 0] && !v6.is_unspecified() && !v6.is_loopback() {
        return Some(Ipv4Addr::new(b[12], b[13], b[14], b[15]));
    }
    // `::ffff:0:a.b.c.d` (RFC 2765 SIIT IPv4-translated).
    if seg[0..4] == [0, 0, 0, 0] && seg[4] == 0xffff && seg[5] == 0 {
        return Some(Ipv4Addr::new(b[12], b[13], b[14], b[15]));
    }
    // `64:ff9b::/96` (RFC 6052 well-known NAT64).
    if seg[0] == 0x0064 && seg[1] == 0xff9b && seg[2..6] == [0, 0, 0, 0] {
        return Some(Ipv4Addr::new(b[12], b[13], b[14], b[15]));
    }
    // `64:ff9b:1::/48` (RFC 8215 local-use NAT64): inspect trailing /96 IPv4 if present,
    // otherwise RFC 6052 /48 embedded IPv4 (`b[6], b[7], b[9], b[10]`, skipping `u` byte `b[8]`).
    if seg[0] == 0x0064 && seg[1] == 0xff9b && seg[2] == 0x0001 {
        if seg[3..6] == [0, 0, 0] {
            return Some(Ipv4Addr::new(b[12], b[13], b[14], b[15]));
        }
        return Some(Ipv4Addr::new(b[6], b[7], b[9], b[10]));
    }
    // `2002::/16` (RFC 3056 6to4).
    if seg[0] == 0x2002 {
        return Some(Ipv4Addr::new(b[2], b[3], b[4], b[5]));
    }

    None
}

fn classify_ipv6(v6: Ipv6Addr) -> AddressClass {
    if v6.is_unspecified() {
        return AddressClass::AlwaysBlocked;
    }
    if v6.is_loopback() {
        return AddressClass::AllowlistableLocal;
    }

    let seg = v6.segments();

    // `64:ff9b:1::/48` is local-use NAT64 (RFC 8215): inspect embedded IPv4 and always block.
    if seg[0] == 0x0064 && seg[1] == 0xff9b && seg[2] == 0x0001 {
        if let Some(v4) = extract_embedded_ipv4(v6) {
            let _ = classify_ipv4(v4);
        }
        return AddressClass::AlwaysBlocked;
    }

    // Any transition/compatible IPv6 carrying an embedded IPv4 inherits the IPv4 check;
    // non-public embedded IPv4 in transition encodings is never exempted by allowlist.
    if let Some(v4) = extract_embedded_ipv4(v6) {
        return match classify_ipv4(v4) {
            AddressClass::Public => AddressClass::Public,
            AddressClass::AllowlistableLocal | AddressClass::AlwaysBlocked => {
                AddressClass::AlwaysBlocked
            }
        };
    }

    let is_ula = (seg[0] & 0xfe00) == 0xfc00; // fc00::/7
    let is_link_local = (seg[0] & 0xffc0) == 0xfe80; // fe80::/10
    let is_site_local = (seg[0] & 0xffc0) == 0xfec0; // fec0::/10
    let is_teredo = seg[0] == 0x2001 && seg[1] == 0x0000; // 2001::/32
    let is_doc = seg[0] == 0x2001 && seg[1] == 0x0db8; // 2001:db8::/32
    let is_discard = seg[0] == 0x0100 && seg[1] == 0 && seg[2] == 0 && seg[3] == 0; // 100::/64

    if v6.is_multicast() || is_link_local || is_site_local || is_teredo || is_doc || is_discard {
        return AddressClass::AlwaysBlocked;
    }

    if is_ula {
        return AddressClass::AllowlistableLocal;
    }

    AddressClass::Public
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blocks_special_use_and_embedded_ipv4_transition_ranges() {
        let blocked = [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.5",
            "192.168.1.10",
            "169.254.169.254",
            "100.64.0.1",
            "192.0.0.1",
            "192.88.99.1",
            "0.0.0.0",
            "255.255.255.255",
            "224.0.0.1",
            "::1",
            "::",
            "fc00::1",
            "fd12:3456::1",
            "fe80::1",
            "fec0::1",
            "2001::1",
            "100::1",
            // Embedded IPv4 transition/compatible forms
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "::ffff:10.0.0.1",
            "::127.0.0.1",
            "::169.254.169.254",
            "::ffff:0:127.0.0.1",
            "::ffff:0:169.254.169.254",
            "64:ff9b::127.0.0.1",
            "64:ff9b::169.254.169.254",
            "64:ff9b::10.0.0.1",
            "64:ff9b:1::127.0.0.1",
            "64:ff9b:1::10.0.0.1",
            "64:ff9b:1::93.184.216.34",
            "2002:7f00:0001::1",
            "2002:a9fe:a9fe::1",
            "2002:0a00:0001::1",
        ];
        for raw in blocked {
            let ip: IpAddr = raw.parse().unwrap();
            assert!(is_blocked_ip(ip), "expected {raw} to be blocked");
        }

        let public_ips = [
            "93.184.216.34",
            "1.1.1.1",
            "2606:2800:220:1:248:1893:25c8:1946",
            "64:ff9b::93.184.216.34",
            "2002:5db8:d822::1",
        ];
        for raw in public_ips {
            let ip: IpAddr = raw.parse().unwrap();
            assert!(!is_blocked_ip(ip), "expected {raw} to be allowed");
        }
    }

    #[tokio::test]
    async fn allowlisted_origin_never_exempts_link_local_or_special_use_ranges() {
        let policy = OutboundAddressPolicy::new([
            "http://169.254.169.254:80",
            "http://[fe80::1]:80",
            "http://100.64.0.1:80",
            "http://192.0.0.1:80",
            "http://192.88.99.1:80",
            "http://[fec0::1]:80",
            "http://[2001::1]:80",
            "http://[100::1]:80",
            "http://[::ffff:169.254.169.254]:80",
            "http://[64:ff9b::169.254.169.254]:80",
        ]);
        for url in [
            "http://169.254.169.254/latest/meta-data/",
            "http://[fe80::1]/",
            "http://100.64.0.1/",
            "http://192.0.0.1/",
            "http://192.88.99.1/",
            "http://[fec0::1]/",
            "http://[2001::1]/",
            "http://[100::1]/",
            "http://[::ffff:169.254.169.254]/",
            "http://[64:ff9b::169.254.169.254]/",
        ] {
            assert!(
                matches!(
                    policy.validate_url(url).await,
                    Err(OutboundPolicyError::BlockedAddress)
                ),
                "allowlisted origin must still block {url}"
            );
        }
    }

    #[tokio::test]
    async fn blocks_localhost_dns_by_default_and_allows_only_exact_allowlisted_origin() {
        let strict = OutboundAddressPolicy::default();
        assert!(matches!(
            strict.validate_url("http://localhost:9000/payments").await,
            Err(OutboundPolicyError::BlockedAddress)
        ));
        assert!(matches!(
            strict.validate_url("http://127.0.0.1:9000/payments").await,
            Err(OutboundPolicyError::BlockedAddress)
        ));
        assert!(matches!(
            strict.validate_url("file:///etc/passwd").await,
            Err(OutboundPolicyError::UnsupportedScheme)
        ));

        let scoped = OutboundAddressPolicy::new(["http://127.0.0.1:9000"]);
        assert!(scoped
            .validate_url("http://127.0.0.1:9000/payments")
            .await
            .is_ok());
        // Different port is NOT allowlisted and remains blocked.
        assert!(matches!(
            scoped.validate_url("http://127.0.0.1:9001/payments").await,
            Err(OutboundPolicyError::BlockedAddress)
        ));
    }

    #[tokio::test]
    async fn oauth2_token_url_outbound_policy_blocks_before_any_http_request() {
        use crate::proxy::credentials::{
            AuthType, BackendCredential, CredentialStore, OAuth2Config,
        };
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let blocked_oauth = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/oauth2/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "unused",
                "expires_in": 300
            })))
            .expect(0)
            .mount(&blocked_oauth)
            .await;

        let store = CredentialStore::new();
        store.upsert(BackendCredential {
            route_id: "mcp-tool:acme:payments_oauth".to_string(),
            auth_type: AuthType::OAuth2ClientCredentials,
            header_name: "Authorization".to_string(),
            header_value: String::new(),
            oauth2: Some(OAuth2Config {
                token_url: format!("{}/oauth2/token", blocked_oauth.uri()),
                client_id: "cid".to_string(),
                client_secret: "csec".to_string(),
            }),
            allowed_origin: Some("https://api.example.com:443".to_string()),
            shared_with_tenants: false,
        });

        let policy = OutboundAddressPolicy::default();
        let err = store
            .get_oauth2_token_guarded("mcp-tool:acme:payments_oauth", &policy)
            .await
            .unwrap_err();
        assert!(err.contains("blocked"), "unexpected error: {err}");
        assert_eq!(blocked_oauth.received_requests().await.unwrap().len(), 0);
    }
}
