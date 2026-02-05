//! Traffic Capture Module
//!
//! Captures HTTP traffic from various sources for analysis.
//! Works with the ShadowService in mode/shadow.rs.

use crate::mode::shadow::{CapturedRequest, CapturedResponse, CapturedTransaction};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{error, info, warn};

/// Traffic capture source types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum CaptureSource {
    /// Envoy tap filter
    EnvoyTap {
        /// Tap service endpoint
        endpoint: String,
    },

    /// Port mirroring
    PortMirror {
        /// Network interface to capture from
        interface: String,
        /// Ports to capture
        ports: Vec<u16>,
    },

    /// Inline capture (copy traffic)
    Inline,

    /// Kafka topic replay
    KafkaReplay {
        /// Kafka brokers
        brokers: Vec<String>,
        /// Topic name
        topic: String,
        /// Consumer group
        group_id: String,
    },
}

/// Traffic capture service
pub struct TrafficCapture {
    /// Capture source
    source: CaptureSource,

    /// Transaction sender
    tx: mpsc::Sender<CapturedTransaction>,

    /// Running flag
    running: Arc<std::sync::atomic::AtomicBool>,
}

impl TrafficCapture {
    /// Create a new traffic capture service
    pub fn new(source: CaptureSource, buffer_size: usize) -> (Self, mpsc::Receiver<CapturedTransaction>) {
        let (tx, rx) = mpsc::channel(buffer_size);
        let capture = Self {
            source,
            tx,
            running: Arc::new(std::sync::atomic::AtomicBool::new(false)),
        };
        (capture, rx)
    }

    /// Start capturing traffic
    pub async fn start(&self) {
        self.running.store(true, std::sync::atomic::Ordering::SeqCst);
        info!(source = ?self.source, "Starting traffic capture");

        match &self.source {
            CaptureSource::EnvoyTap { endpoint } => {
                self.capture_envoy_tap(endpoint).await;
            }
            CaptureSource::PortMirror { interface, ports } => {
                self.capture_port_mirror(interface, ports).await;
            }
            CaptureSource::Inline => {
                // Inline capture is handled by the proxy middleware
                info!("Inline capture mode - traffic captured via proxy");
            }
            CaptureSource::KafkaReplay { brokers, topic, group_id } => {
                self.capture_kafka_replay(brokers, topic, group_id).await;
            }
        }
    }

    /// Stop capturing
    pub fn stop(&self) {
        self.running.store(false, std::sync::atomic::Ordering::SeqCst);
        info!("Stopping traffic capture");
    }

    /// Capture from Envoy tap filter
    async fn capture_envoy_tap(&self, _endpoint: &str) {
        // TODO: Implement Envoy tap integration
        // - Connect to tap service gRPC endpoint
        // - Stream TraceWrapper messages
        // - Convert to CapturedTransaction
        warn!("Envoy tap capture not yet implemented");
    }

    /// Capture via port mirroring
    async fn capture_port_mirror(&self, _interface: &str, _ports: &[u16]) {
        // TODO: Implement pcap-based capture
        // - Use libpcap/pnet to capture packets
        // - Reassemble TCP streams
        // - Parse HTTP requests/responses
        warn!("Port mirror capture not yet implemented");
    }

    /// Replay from Kafka topic
    async fn capture_kafka_replay(&self, _brokers: &[String], _topic: &str, _group_id: &str) {
        // TODO: Implement Kafka consumer
        // - Consume from topic
        // - Deserialize transactions
        // - Send to analyzer
        warn!("Kafka replay capture not yet implemented");
    }

    /// Submit a captured transaction (for inline mode)
    pub async fn submit(&self, transaction: CapturedTransaction) {
        if let Err(e) = self.tx.send(transaction).await {
            error!("Failed to send captured transaction: {}", e);
        }
    }

    /// Parse raw HTTP request
    pub fn parse_request(raw: &[u8]) -> Option<CapturedRequest> {
        // Simple HTTP/1.1 request parsing
        let text = std::str::from_utf8(raw).ok()?;
        let mut lines = text.lines();

        // Parse request line
        let request_line = lines.next()?;
        let parts: Vec<&str> = request_line.split_whitespace().collect();
        if parts.len() < 2 {
            return None;
        }

        let method = parts[0].to_string();
        let full_path = parts[1];

        // Split path and query
        let (path, query_string) = if let Some(idx) = full_path.find('?') {
            (&full_path[..idx], Some(&full_path[idx + 1..]))
        } else {
            (full_path, None)
        };

        // Parse query params
        let query_params: HashMap<String, String> = query_string
            .map(|qs| {
                qs.split('&')
                    .filter_map(|pair| {
                        let mut kv = pair.splitn(2, '=');
                        Some((kv.next()?.to_string(), kv.next().unwrap_or("").to_string()))
                    })
                    .collect()
            })
            .unwrap_or_default();

        // Parse headers
        let mut headers = HashMap::new();
        let mut content_type = None;
        let mut body_start = 0;

        for line in lines {
            if line.is_empty() {
                body_start = text.find("\r\n\r\n").map(|i| i + 4)
                    .or_else(|| text.find("\n\n").map(|i| i + 2))
                    .unwrap_or(raw.len());
                break;
            }

            if let Some(idx) = line.find(':') {
                let name = line[..idx].trim().to_lowercase();
                let value = line[idx + 1..].trim().to_string();

                if name == "content-type" {
                    content_type = Some(value.clone());
                }

                // Redact sensitive headers
                if !is_sensitive_header(&name) {
                    headers.insert(name, value);
                }
            }
        }

        // Parse body if JSON
        let body = if body_start < raw.len() && content_type.as_deref() == Some("application/json") {
            serde_json::from_slice(&raw[body_start..]).ok()
        } else {
            None
        };

        Some(CapturedRequest {
            method,
            path: path.to_string(),
            query_params,
            headers,
            content_type,
            body,
            body_size: raw.len().saturating_sub(body_start),
        })
    }

    /// Parse raw HTTP response
    pub fn parse_response(raw: &[u8]) -> Option<CapturedResponse> {
        let text = std::str::from_utf8(raw).ok()?;
        let mut lines = text.lines();

        // Parse status line
        let status_line = lines.next()?;
        let parts: Vec<&str> = status_line.split_whitespace().collect();
        if parts.len() < 2 {
            return None;
        }

        let status_code: u16 = parts[1].parse().ok()?;

        // Parse headers
        let mut headers = HashMap::new();
        let mut content_type = None;
        let mut body_start = 0;

        for line in lines {
            if line.is_empty() {
                body_start = text.find("\r\n\r\n").map(|i| i + 4)
                    .or_else(|| text.find("\n\n").map(|i| i + 2))
                    .unwrap_or(raw.len());
                break;
            }

            if let Some(idx) = line.find(':') {
                let name = line[..idx].trim().to_lowercase();
                let value = line[idx + 1..].trim().to_string();

                if name == "content-type" {
                    content_type = Some(value.clone());
                }

                headers.insert(name, value);
            }
        }

        // Parse body if JSON
        let body = if body_start < raw.len() && content_type.as_deref().map(|ct| ct.contains("json")).unwrap_or(false) {
            serde_json::from_slice(&raw[body_start..]).ok()
        } else {
            None
        };

        Some(CapturedResponse {
            status_code,
            headers,
            content_type,
            body,
            body_size: raw.len().saturating_sub(body_start),
        })
    }
}

/// Check if header contains sensitive data
fn is_sensitive_header(name: &str) -> bool {
    matches!(
        name,
        "authorization" | "cookie" | "set-cookie" | "x-api-key" | "x-auth-token"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_request() {
        let raw = b"GET /api/v1/users?page=1&limit=10 HTTP/1.1\r\nHost: example.com\r\nContent-Type: application/json\r\n\r\n";

        let request = TrafficCapture::parse_request(raw).unwrap();
        assert_eq!(request.method, "GET");
        assert_eq!(request.path, "/api/v1/users");
        assert_eq!(request.query_params.get("page"), Some(&"1".to_string()));
        assert_eq!(request.query_params.get("limit"), Some(&"10".to_string()));
    }

    #[test]
    fn test_parse_response() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}";

        let response = TrafficCapture::parse_response(raw).unwrap();
        assert_eq!(response.status_code, 200);
        assert!(response.body.is_some());
    }

    #[test]
    fn test_sensitive_header() {
        assert!(is_sensitive_header("authorization"));
        assert!(is_sensitive_header("cookie"));
        assert!(!is_sensitive_header("content-type"));
    }
}
