//! Hop Detection (CAB-1316 Phase 2)
//!
//! Analyzes HTTP headers to detect intermediate proxies and load balancers.
//! Builds a HopChain from `X-Forwarded-For`, `Via`, `X-Real-IP`, and
//! `Server-Timing` headers.

use serde::{Deserialize, Serialize};

/// Type of network hop in the request chain.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HopType {
    Client,
    Gateway,
    Proxy,
    LoadBalancer,
    Backend,
    Unknown,
}

impl std::fmt::Display for HopType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Client => write!(f, "client"),
            Self::Gateway => write!(f, "gateway"),
            Self::Proxy => write!(f, "proxy"),
            Self::LoadBalancer => write!(f, "load_balancer"),
            Self::Backend => write!(f, "backend"),
            Self::Unknown => write!(f, "unknown"),
        }
    }
}

/// A single hop in the network path.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hop {
    pub name: String,
    pub address: Option<String>,
    pub latency_ms: Option<f64>,
    pub hop_type: HopType,
}

/// Ordered chain of hops from client to backend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HopChain {
    pub hops: Vec<Hop>,
    pub total_detected: usize,
    pub total_latency_ms: Option<f64>,
}

impl HopChain {
    /// Return the hop consuming the most latency, if any.
    pub fn bottleneck(&self) -> Option<&Hop> {
        self.hops
            .iter()
            .filter(|h| h.latency_ms.is_some())
            .max_by(|a, b| {
                a.latency_ms
                    .unwrap_or(0.0)
                    .partial_cmp(&b.latency_ms.unwrap_or(0.0))
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
    }
}

/// Headers relevant to hop detection, extracted from the request/response.
#[derive(Debug, Default)]
pub struct HopHeaders {
    pub x_forwarded_for: Option<String>,
    pub via: Option<String>,
    pub x_real_ip: Option<String>,
    pub server_timing: Option<String>,
}

/// Detects intermediate hops from HTTP headers.
pub struct HopDetector;

impl HopDetector {
    /// Analyze headers and build a hop chain.
    pub fn detect(headers: &HopHeaders) -> HopChain {
        let mut hops = Vec::new();

        // Parse X-Forwarded-For: client, proxy1, proxy2
        if let Some(xff) = &headers.x_forwarded_for {
            let addresses: Vec<&str> = xff.split(',').map(|s| s.trim()).collect();
            for (i, addr) in addresses.iter().enumerate() {
                if addr.is_empty() {
                    continue;
                }
                let hop_type = if i == 0 {
                    HopType::Client
                } else {
                    HopType::Proxy
                };
                hops.push(Hop {
                    name: format!("hop-{}", i),
                    address: Some(addr.to_string()),
                    latency_ms: None,
                    hop_type,
                });
            }
        }

        // Parse X-Real-IP (if no XFF, use this as client hop)
        if hops.is_empty() {
            if let Some(real_ip) = &headers.x_real_ip {
                let trimmed = real_ip.trim();
                if !trimmed.is_empty() {
                    hops.push(Hop {
                        name: "client".to_string(),
                        address: Some(trimmed.to_string()),
                        latency_ms: None,
                        hop_type: HopType::Client,
                    });
                }
            }
        }

        // Parse Via: 1.1 proxy-name, 2.0 cdn.example.com
        if let Some(via) = &headers.via {
            for entry in via.split(',') {
                let entry = entry.trim();
                if entry.is_empty() {
                    continue;
                }
                let parts: Vec<&str> = entry.splitn(2, ' ').collect();
                let (protocol, pseudonym) = match parts.len() {
                    2 => (parts[0], parts[1]),
                    1 => ("", parts[0]),
                    _ => continue,
                };
                // Strip comment from pseudonym: "stoa-gateway (0.1.0)" -> "stoa-gateway"
                let clean_name = pseudonym
                    .split('(')
                    .next()
                    .unwrap_or(pseudonym)
                    .trim()
                    .to_string();

                let hop_type = Self::infer_hop_type(&clean_name, protocol);

                hops.push(Hop {
                    name: clean_name,
                    address: None,
                    latency_ms: None,
                    hop_type,
                });
            }
        }

        // Parse Server-Timing for latency info: server-timing: gateway;dur=5.2, backend;dur=120.5
        if let Some(st) = &headers.server_timing {
            Self::apply_server_timing(&mut hops, st);
        }

        let total_detected = hops.len();
        let total_latency_ms = {
            let sum: f64 = hops.iter().filter_map(|h| h.latency_ms).sum();
            if sum > 0.0 {
                Some(sum)
            } else {
                None
            }
        };

        HopChain {
            hops,
            total_detected,
            total_latency_ms,
        }
    }

    /// Infer hop type from name/protocol heuristics.
    fn infer_hop_type(name: &str, _protocol: &str) -> HopType {
        let lower = name.to_lowercase();
        if lower.contains("gateway") || lower.contains("stoa") {
            HopType::Gateway
        } else if lower.contains("cdn")
            || lower.contains("cloudflare")
            || lower.contains("akamai")
            || lower.contains("lb")
            || lower.contains("balancer")
            || lower.contains("haproxy")
            || lower.contains("nginx")
            || lower.contains("envoy")
        {
            HopType::LoadBalancer
        } else {
            HopType::Proxy
        }
    }

    /// Parse Server-Timing header and apply latency values to matching hops.
    fn apply_server_timing(hops: &mut Vec<Hop>, server_timing: &str) {
        for entry in server_timing.split(',') {
            let entry = entry.trim();
            if entry.is_empty() {
                continue;
            }
            // Format: name;dur=123.4;desc="description"
            let parts: Vec<&str> = entry.split(';').collect();
            let metric_name = parts[0].trim();
            let mut duration_ms = None;

            for part in &parts[1..] {
                let part = part.trim();
                if let Some(dur_str) = part.strip_prefix("dur=") {
                    duration_ms = dur_str.parse::<f64>().ok();
                }
            }

            // Try to match to an existing hop by name
            let mut matched = false;
            for hop in hops.iter_mut() {
                let hop_lower = hop.name.to_lowercase();
                if hop_lower.contains(&metric_name.to_lowercase())
                    || metric_name.to_lowercase().contains(&hop_lower)
                {
                    hop.latency_ms = duration_ms;
                    matched = true;
                    break;
                }
            }

            // If no match, add as a new hop with the timing data
            if !matched {
                if let Some(dur) = duration_ms {
                    hops.push(Hop {
                        name: metric_name.to_string(),
                        address: None,
                        latency_ms: Some(dur),
                        hop_type: HopType::Unknown,
                    });
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detect_empty_headers() {
        let chain = HopDetector::detect(&HopHeaders::default());
        assert!(chain.hops.is_empty());
        assert_eq!(chain.total_detected, 0);
        assert!(chain.total_latency_ms.is_none());
    }

    #[test]
    fn detect_x_forwarded_for_single() {
        let headers = HopHeaders {
            x_forwarded_for: Some("192.168.1.1".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 1);
        assert_eq!(chain.hops[0].hop_type, HopType::Client);
        assert_eq!(chain.hops[0].address.as_deref(), Some("192.168.1.1"));
    }

    #[test]
    fn detect_x_forwarded_for_chain() {
        let headers = HopHeaders {
            x_forwarded_for: Some("10.0.0.1, 10.0.0.2, 10.0.0.3".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 3);
        assert_eq!(chain.hops[0].hop_type, HopType::Client);
        assert_eq!(chain.hops[1].hop_type, HopType::Proxy);
        assert_eq!(chain.hops[2].hop_type, HopType::Proxy);
    }

    #[test]
    fn detect_x_real_ip_fallback() {
        let headers = HopHeaders {
            x_real_ip: Some("172.16.0.1".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 1);
        assert_eq!(chain.hops[0].hop_type, HopType::Client);
        assert_eq!(chain.hops[0].address.as_deref(), Some("172.16.0.1"));
    }

    #[test]
    fn detect_x_real_ip_skipped_when_xff_present() {
        let headers = HopHeaders {
            x_forwarded_for: Some("10.0.0.1".to_string()),
            x_real_ip: Some("172.16.0.1".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        // Should only have XFF hop, X-Real-IP is ignored when XFF present
        assert_eq!(chain.hops.len(), 1);
        assert_eq!(chain.hops[0].address.as_deref(), Some("10.0.0.1"));
    }

    #[test]
    fn detect_via_single_hop() {
        let headers = HopHeaders {
            via: Some("1.1 stoa-gateway (0.1.0)".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 1);
        assert_eq!(chain.hops[0].name, "stoa-gateway");
        assert_eq!(chain.hops[0].hop_type, HopType::Gateway);
    }

    #[test]
    fn detect_via_multiple_hops() {
        let headers = HopHeaders {
            via: Some("1.1 proxy-a, 2.0 cdn.example.com".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 2);
        assert_eq!(chain.hops[0].name, "proxy-a");
        assert_eq!(chain.hops[0].hop_type, HopType::Proxy);
        assert_eq!(chain.hops[1].name, "cdn.example.com");
        assert_eq!(chain.hops[1].hop_type, HopType::LoadBalancer);
    }

    #[test]
    fn detect_server_timing_matches_hop() {
        let headers = HopHeaders {
            via: Some("1.1 stoa-gateway".to_string()),
            server_timing: Some("gateway;dur=5.2".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 1);
        assert_eq!(chain.hops[0].latency_ms, Some(5.2));
    }

    #[test]
    fn detect_server_timing_adds_unmatched_hop() {
        let headers = HopHeaders {
            server_timing: Some("backend;dur=120.5".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 1);
        assert_eq!(chain.hops[0].name, "backend");
        assert_eq!(chain.hops[0].latency_ms, Some(120.5));
        assert!(chain.total_latency_ms.is_some());
    }

    #[test]
    fn detect_combined_xff_via_timing() {
        let headers = HopHeaders {
            x_forwarded_for: Some("10.0.0.1".to_string()),
            via: Some("1.1 stoa-gateway".to_string()),
            server_timing: Some("gateway;dur=3.0, backend;dur=50.0".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        // XFF client + Via gateway + Server-Timing backend (unmatched)
        assert_eq!(chain.total_detected, 3);
        assert!(chain.total_latency_ms.is_some());
    }

    #[test]
    fn infer_hop_type_gateway() {
        assert_eq!(
            HopDetector::infer_hop_type("stoa-gateway", "1.1"),
            HopType::Gateway
        );
    }

    #[test]
    fn infer_hop_type_cdn() {
        assert_eq!(
            HopDetector::infer_hop_type("cdn.example.com", "2.0"),
            HopType::LoadBalancer
        );
    }

    #[test]
    fn infer_hop_type_nginx() {
        assert_eq!(
            HopDetector::infer_hop_type("nginx", "1.1"),
            HopType::LoadBalancer
        );
    }

    #[test]
    fn infer_hop_type_haproxy() {
        assert_eq!(
            HopDetector::infer_hop_type("haproxy-lb", "1.1"),
            HopType::LoadBalancer
        );
    }

    #[test]
    fn infer_hop_type_generic_proxy() {
        assert_eq!(
            HopDetector::infer_hop_type("my-reverse-proxy", "1.1"),
            HopType::Proxy
        );
    }

    #[test]
    fn hop_chain_bottleneck() {
        let chain = HopChain {
            hops: vec![
                Hop {
                    name: "gw".into(),
                    address: None,
                    latency_ms: Some(5.0),
                    hop_type: HopType::Gateway,
                },
                Hop {
                    name: "backend".into(),
                    address: None,
                    latency_ms: Some(150.0),
                    hop_type: HopType::Backend,
                },
            ],
            total_detected: 2,
            total_latency_ms: Some(155.0),
        };
        let bottleneck = chain.bottleneck().expect("should find bottleneck");
        assert_eq!(bottleneck.name, "backend");
    }

    #[test]
    fn hop_chain_bottleneck_none_when_no_latency() {
        let chain = HopChain {
            hops: vec![Hop {
                name: "gw".into(),
                address: None,
                latency_ms: None,
                hop_type: HopType::Gateway,
            }],
            total_detected: 1,
            total_latency_ms: None,
        };
        assert!(chain.bottleneck().is_none());
    }

    #[test]
    fn detect_server_timing_multiple_entries() {
        let headers = HopHeaders {
            server_timing: Some("auth;dur=2.0, policy;dur=1.5, backend;dur=100.0".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 3);
        let total: f64 = chain.hops.iter().filter_map(|h| h.latency_ms).sum();
        assert!((total - 103.5).abs() < 0.01);
    }

    #[test]
    fn hop_serde_roundtrip() {
        let hop = Hop {
            name: "test-gw".into(),
            address: Some("10.0.0.1".into()),
            latency_ms: Some(5.5),
            hop_type: HopType::Gateway,
        };
        let json = serde_json::to_string(&hop).expect("serialize");
        let back: Hop = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.name, "test-gw");
        assert_eq!(back.hop_type, HopType::Gateway);
    }

    #[test]
    fn hop_chain_serde_roundtrip() {
        let chain = HopChain {
            hops: vec![],
            total_detected: 0,
            total_latency_ms: None,
        };
        let json = serde_json::to_string(&chain).expect("serialize");
        let back: HopChain = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.total_detected, 0);
    }

    #[test]
    fn detect_empty_xff_entries_skipped() {
        let headers = HopHeaders {
            x_forwarded_for: Some("10.0.0.1, , 10.0.0.3".to_string()),
            ..Default::default()
        };
        let chain = HopDetector::detect(&headers);
        assert_eq!(chain.hops.len(), 2);
    }

    #[test]
    fn hop_type_display() {
        assert_eq!(HopType::Client.to_string(), "client");
        assert_eq!(HopType::Gateway.to_string(), "gateway");
        assert_eq!(HopType::Proxy.to_string(), "proxy");
        assert_eq!(HopType::LoadBalancer.to_string(), "load_balancer");
        assert_eq!(HopType::Backend.to_string(), "backend");
        assert_eq!(HopType::Unknown.to_string(), "unknown");
    }
}
