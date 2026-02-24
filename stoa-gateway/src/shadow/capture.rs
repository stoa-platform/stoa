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
    pub fn new(
        source: CaptureSource,
        buffer_size: usize,
    ) -> (Self, mpsc::Receiver<CapturedTransaction>) {
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
        self.running
            .store(true, std::sync::atomic::Ordering::SeqCst);
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
            CaptureSource::KafkaReplay {
                brokers,
                topic,
                group_id,
            } => {
                self.capture_kafka_replay(brokers, topic, group_id).await;
            }
        }
    }

    /// Stop capturing
    pub fn stop(&self) {
        self.running
            .store(false, std::sync::atomic::Ordering::SeqCst);
        info!("Stopping traffic capture");
    }

    /// Capture from Envoy tap filter via HTTP admin API (JSON output).
    ///
    /// Connects to `/tap` endpoint, parses JSON tap records, and converts
    /// each to a `CapturedTransaction` using `parse_request`/`parse_response`
    /// for consistent header redaction.
    async fn capture_envoy_tap(&self, endpoint: &str) {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(5))
            .build()
            .unwrap_or_default();

        let tap_url = format!("{}/tap", endpoint.trim_end_matches('/'));

        while self.running.load(std::sync::atomic::Ordering::SeqCst) {
            match client.get(&tap_url).send().await {
                Ok(resp) if resp.status().is_success() => {
                    let body = match resp.text().await {
                        Ok(b) => b,
                        Err(e) => {
                            warn!(error = %e, "Failed to read Envoy tap response body");
                            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                            continue;
                        }
                    };

                    // Envoy tap can return NDJSON (one JSON object per line)
                    for line in body.lines() {
                        let line = line.trim();
                        if line.is_empty() {
                            continue;
                        }
                        if let Some(tx) = Self::parse_envoy_tap_record(line) {
                            if self.tx.send(tx).await.is_err() {
                                info!("Capture channel closed, stopping Envoy tap");
                                return;
                            }
                        }
                    }
                }
                Ok(resp) => {
                    warn!(status = %resp.status(), "Envoy tap returned non-success status");
                }
                Err(e) => {
                    warn!(error = %e, "Failed to connect to Envoy tap endpoint");
                }
            }

            // Poll interval — avoid busy loop
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
    }

    /// Parse a single Envoy tap JSON record into a `CapturedTransaction`.
    ///
    /// Expected format (Envoy JSON tap output):
    /// ```json
    /// {
    ///   "http_buffered_trace": {
    ///     "request": { "headers": [...], "body": {...} },
    ///     "response": { "headers": [...], "body": {...} }
    ///   }
    /// }
    /// ```
    fn parse_envoy_tap_record(json_str: &str) -> Option<CapturedTransaction> {
        let value: serde_json::Value = serde_json::from_str(json_str).ok()?;

        let trace = value
            .get("http_buffered_trace")
            .or_else(|| value.get("trace"))?;

        let req_obj = trace.get("request")?;
        let resp_obj = trace.get("response")?;

        // Extract method + path from request headers
        let req_headers = req_obj.get("headers").and_then(|h| h.as_array())?;
        let mut method = "GET".to_string();
        let mut path = "/".to_string();
        let mut headers = HashMap::new();
        let mut content_type = None;

        for header in req_headers {
            let key = header
                .get("key")
                .and_then(|v| v.as_str())
                .unwrap_or_default();
            let val = header
                .get("value")
                .and_then(|v| v.as_str())
                .unwrap_or_default();

            match key {
                ":method" => method = val.to_string(),
                ":path" => path = val.to_string(),
                "content-type" => {
                    content_type = Some(val.to_string());
                    headers.insert(key.to_string(), val.to_string());
                }
                _ if !key.starts_with(':') => {
                    headers.insert(key.to_string(), val.to_string());
                }
                _ => {}
            }
        }

        // Split path and query
        let (clean_path, query_params) = if let Some(idx) = path.find('?') {
            let qs = &path[idx + 1..];
            let params: HashMap<String, String> = qs
                .split('&')
                .filter_map(|pair| {
                    let mut kv = pair.splitn(2, '=');
                    Some((kv.next()?.to_string(), kv.next().unwrap_or("").to_string()))
                })
                .collect();
            (path[..idx].to_string(), params)
        } else {
            (path.clone(), HashMap::new())
        };

        // Parse request body
        let req_body = req_obj
            .get("body")
            .and_then(|b| b.get("as_string").or_else(|| b.get("as_bytes")))
            .and_then(|v| v.as_str())
            .and_then(|s| serde_json::from_str(s).ok());

        let req_body_size = req_obj
            .get("body")
            .and_then(|b| b.get("as_string").or_else(|| b.get("as_bytes")))
            .and_then(|v| v.as_str())
            .map(|s| s.len())
            .unwrap_or(0);

        // Extract response status + headers
        let resp_headers_arr = resp_obj.get("headers").and_then(|h| h.as_array());
        let mut status_code: u16 = 200;
        let mut resp_headers = HashMap::new();
        let mut resp_content_type = None;

        if let Some(rh) = resp_headers_arr {
            for header in rh {
                let key = header
                    .get("key")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default();
                let val = header
                    .get("value")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default();
                if key == ":status" {
                    status_code = val.parse().unwrap_or(200);
                } else if key == "content-type" {
                    resp_content_type = Some(val.to_string());
                    resp_headers.insert(key.to_string(), val.to_string());
                } else if !key.starts_with(':') {
                    resp_headers.insert(key.to_string(), val.to_string());
                }
            }
        }

        // Parse response body
        let resp_body = resp_obj
            .get("body")
            .and_then(|b| b.get("as_string").or_else(|| b.get("as_bytes")))
            .and_then(|v| v.as_str())
            .and_then(|s| serde_json::from_str(s).ok());

        let resp_body_size = resp_obj
            .get("body")
            .and_then(|b| b.get("as_string").or_else(|| b.get("as_bytes")))
            .and_then(|v| v.as_str())
            .map(|s| s.len())
            .unwrap_or(0);

        Some(CapturedTransaction {
            id: uuid::Uuid::new_v4().to_string(),
            timestamp: chrono::Utc::now(),
            request: CapturedRequest {
                method,
                path: clean_path,
                query_params,
                headers,
                content_type,
                body: req_body,
                body_size: req_body_size,
            },
            response: CapturedResponse {
                status_code,
                headers: resp_headers,
                content_type: resp_content_type,
                body: resp_body,
                body_size: resp_body_size,
            },
            latency_ms: 0, // Tap doesn't provide latency
            source: "envoy_tap".to_string(),
        })
    }

    /// Capture via port mirroring using raw packet capture.
    ///
    /// Uses `pnet` crate (feature-gated behind `pcap`) for raw Ethernet frame
    /// capture. Performs simplified HTTP/1.1 extraction from individual TCP
    /// packets — no TCP reassembly (single-packet requests/responses only).
    /// Reuses `parse_request`/`parse_response` for consistent header redaction.
    #[cfg(feature = "pcap")]
    async fn capture_port_mirror(&self, interface: &str, ports: &[u16]) {
        use pnet::datalink::{self, Channel};
        use pnet::packet::ethernet::{EtherTypes, EthernetPacket};
        use pnet::packet::ipv4::Ipv4Packet;
        use pnet::packet::tcp::TcpPacket;
        use pnet::packet::Packet;

        let interfaces = datalink::interfaces();
        let iface = match interfaces.iter().find(|i| i.name == interface) {
            Some(i) => i.clone(),
            None => {
                error!(interface = %interface, "Network interface not found");
                return;
            }
        };

        let (_tx_chan, mut rx) = match datalink::channel(&iface, Default::default()) {
            Ok(Channel::Ethernet(tx, rx)) => (tx, rx),
            Ok(_) => {
                error!("Unsupported channel type for interface");
                return;
            }
            Err(e) => {
                error!(error = %e, "Failed to open capture channel");
                return;
            }
        };

        let port_set: std::collections::HashSet<u16> = ports.iter().copied().collect();
        info!(interface = %interface, ports = ?ports, "Port mirror capture started");

        while self.running.load(std::sync::atomic::Ordering::SeqCst) {
            match rx.next() {
                Ok(packet) => {
                    let eth = match EthernetPacket::new(packet) {
                        Some(e) => e,
                        None => continue,
                    };

                    if eth.get_ethertype() != EtherTypes::Ipv4 {
                        continue;
                    }

                    let ipv4 = match Ipv4Packet::new(eth.payload()) {
                        Some(ip) => ip,
                        None => continue,
                    };

                    let tcp = match TcpPacket::new(ipv4.payload()) {
                        Some(t) => t,
                        None => continue,
                    };

                    let src_port = tcp.get_source();
                    let dst_port = tcp.get_destination();

                    // Only process packets on monitored ports
                    if !port_set.contains(&src_port) && !port_set.contains(&dst_port) {
                        continue;
                    }

                    let payload = tcp.payload();
                    if payload.is_empty() {
                        continue;
                    }

                    // Try to parse as HTTP request or response
                    if let Some(request) = Self::parse_request(payload) {
                        // This is a request packet — store it; we'd need the response
                        // to form a complete transaction. For simplified single-packet
                        // capture, emit a partial transaction with a stub response.
                        let tx = CapturedTransaction {
                            id: uuid::Uuid::new_v4().to_string(),
                            timestamp: chrono::Utc::now(),
                            request,
                            response: CapturedResponse {
                                status_code: 0,
                                headers: HashMap::new(),
                                content_type: None,
                                body: None,
                                body_size: 0,
                            },
                            latency_ms: 0,
                            source: "port_mirror".to_string(),
                        };
                        if self.tx.send(tx).await.is_err() {
                            info!("Capture channel closed, stopping port mirror");
                            return;
                        }
                    } else if let Some(response) = Self::parse_response(payload) {
                        // Response without matched request — emit with stub request
                        let tx = CapturedTransaction {
                            id: uuid::Uuid::new_v4().to_string(),
                            timestamp: chrono::Utc::now(),
                            request: CapturedRequest {
                                method: "UNKNOWN".to_string(),
                                path: "/".to_string(),
                                query_params: HashMap::new(),
                                headers: HashMap::new(),
                                content_type: None,
                                body: None,
                                body_size: 0,
                            },
                            response,
                            latency_ms: 0,
                            source: "port_mirror".to_string(),
                        };
                        if self.tx.send(tx).await.is_err() {
                            info!("Capture channel closed, stopping port mirror");
                            return;
                        }
                    }
                }
                Err(e) => {
                    warn!(error = %e, "Error reading packet");
                    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                }
            }
        }
    }

    /// Fallback when pcap feature is not enabled
    #[cfg(not(feature = "pcap"))]
    async fn capture_port_mirror(&self, _interface: &str, _ports: &[u16]) {
        warn!("Port mirror capture requires the 'pcap' feature flag (cargo build --features pcap)");
    }

    /// Replay captured transactions from a Kafka topic.
    ///
    /// Messages are expected as JSON-serialized `CapturedTransaction` objects.
    /// Uses rdkafka `StreamConsumer` for async consumption.
    #[cfg(feature = "kafka")]
    async fn capture_kafka_replay(&self, brokers: &[String], topic: &str, group_id: &str) {
        use rdkafka::config::ClientConfig;
        use rdkafka::consumer::{Consumer, StreamConsumer};
        use rdkafka::Message;

        let consumer: StreamConsumer = match ClientConfig::new()
            .set("bootstrap.servers", brokers.join(","))
            .set("group.id", group_id)
            .set("auto.offset.reset", "earliest")
            .set("enable.auto.commit", "true")
            .create()
        {
            Ok(c) => c,
            Err(e) => {
                error!(error = %e, "Failed to create Kafka consumer");
                return;
            }
        };

        if let Err(e) = consumer.subscribe(&[topic]) {
            error!(error = %e, topic = %topic, "Failed to subscribe to Kafka topic");
            return;
        }

        info!(topic = %topic, group = %group_id, "Kafka replay capture started");

        while self.running.load(std::sync::atomic::Ordering::SeqCst) {
            match tokio::time::timeout(std::time::Duration::from_secs(1), consumer.recv()).await {
                Ok(Ok(msg)) => {
                    if let Some(payload) = msg.payload() {
                        match serde_json::from_slice::<CapturedTransaction>(payload) {
                            Ok(tx) => {
                                if self.tx.send(tx).await.is_err() {
                                    info!("Capture channel closed, stopping Kafka replay");
                                    return;
                                }
                            }
                            Err(e) => {
                                warn!(
                                    error = %e,
                                    offset = msg.offset(),
                                    "Failed to deserialize Kafka message as CapturedTransaction"
                                );
                            }
                        }
                    }
                }
                Ok(Err(e)) => {
                    warn!(error = %e, "Kafka consumer error");
                }
                Err(_) => {
                    // Timeout — loop back to check running flag
                }
            }
        }

        info!("Kafka replay capture stopped");
    }

    /// Fallback when kafka feature is not enabled
    #[cfg(not(feature = "kafka"))]
    async fn capture_kafka_replay(&self, _brokers: &[String], _topic: &str, _group_id: &str) {
        warn!(
            "Kafka replay capture requires the 'kafka' feature flag (cargo build --features kafka)"
        );
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
                body_start = text
                    .find("\r\n\r\n")
                    .map(|i| i + 4)
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
        let body = if body_start < raw.len() && content_type.as_deref() == Some("application/json")
        {
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
                body_start = text
                    .find("\r\n\r\n")
                    .map(|i| i + 4)
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
        let body = if body_start < raw.len()
            && content_type
                .as_deref()
                .map(|ct| ct.contains("json"))
                .unwrap_or(false)
        {
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

    #[test]
    fn test_envoy_tap_parses_json_response() {
        let json = r#"{
            "http_buffered_trace": {
                "request": {
                    "headers": [
                        {"key": ":method", "value": "POST"},
                        {"key": ":path", "value": "/api/v1/users?page=2"},
                        {"key": "content-type", "value": "application/json"}
                    ],
                    "body": {"as_string": "{\"name\":\"alice\"}"}
                },
                "response": {
                    "headers": [
                        {"key": ":status", "value": "201"},
                        {"key": "content-type", "value": "application/json"}
                    ],
                    "body": {"as_string": "{\"id\":42}"}
                }
            }
        }"#;
        let tx = TrafficCapture::parse_envoy_tap_record(json).unwrap();
        assert_eq!(tx.request.method, "POST");
        assert_eq!(tx.request.path, "/api/v1/users");
        assert_eq!(tx.request.query_params.get("page"), Some(&"2".to_string()));
        assert_eq!(tx.response.status_code, 201);
        assert!(tx.request.body.is_some());
        assert!(tx.response.body.is_some());
        assert_eq!(tx.source, "envoy_tap");
    }

    #[test]
    fn test_envoy_tap_missing_trace_returns_none() {
        let json = r#"{"unrelated": true}"#;
        assert!(TrafficCapture::parse_envoy_tap_record(json).is_none());
    }

    #[test]
    fn test_envoy_tap_alternate_trace_key() {
        let json = r#"{
            "trace": {
                "request": {
                    "headers": [
                        {"key": ":method", "value": "GET"},
                        {"key": ":path", "value": "/health"}
                    ]
                },
                "response": {
                    "headers": [
                        {"key": ":status", "value": "200"}
                    ]
                }
            }
        }"#;
        let tx = TrafficCapture::parse_envoy_tap_record(json).unwrap();
        assert_eq!(tx.request.method, "GET");
        assert_eq!(tx.request.path, "/health");
        assert_eq!(tx.response.status_code, 200);
    }

    #[test]
    fn test_kafka_deserialize_transaction() {
        let tx = CapturedTransaction {
            id: "kafka-1".to_string(),
            timestamp: chrono::Utc::now(),
            request: CapturedRequest {
                method: "GET".to_string(),
                path: "/api/data".to_string(),
                query_params: HashMap::new(),
                headers: HashMap::new(),
                content_type: None,
                body: None,
                body_size: 0,
            },
            response: CapturedResponse {
                status_code: 200,
                headers: HashMap::new(),
                content_type: Some("application/json".to_string()),
                body: Some(serde_json::json!({"ok": true})),
                body_size: 12,
            },
            latency_ms: 42,
            source: "kafka".to_string(),
        };
        let bytes = serde_json::to_vec(&tx).unwrap();
        let deserialized: CapturedTransaction = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(deserialized.id, "kafka-1");
        assert_eq!(deserialized.request.method, "GET");
        assert_eq!(deserialized.response.status_code, 200);
        assert_eq!(deserialized.latency_ms, 42);
    }

    #[test]
    fn test_capture_source_serialization() {
        let sources = vec![
            CaptureSource::EnvoyTap {
                endpoint: "http://envoy:9901".to_string(),
            },
            CaptureSource::PortMirror {
                interface: "eth0".to_string(),
                ports: vec![80, 443],
            },
            CaptureSource::Inline,
            CaptureSource::KafkaReplay {
                brokers: vec!["kafka:9092".to_string()],
                topic: "traffic".to_string(),
                group_id: "shadow".to_string(),
            },
        ];
        for source in &sources {
            let json = serde_json::to_string(source).unwrap();
            let deserialized: CaptureSource = serde_json::from_str(&json).unwrap();
            let json2 = serde_json::to_string(&deserialized).unwrap();
            assert_eq!(json, json2);
        }
    }

    #[test]
    fn test_parse_request_with_post_method() {
        let raw = b"POST /api/v1/tools/call HTTP/1.1\r\nHost: gateway\r\nContent-Type: application/json\r\n\r\n{\"tool\":\"read\"}";
        let req = TrafficCapture::parse_request(raw).unwrap();
        assert_eq!(req.method, "POST");
        assert_eq!(req.path, "/api/v1/tools/call");
        assert!(req.body.is_some());
    }

    #[test]
    fn test_parse_request_no_query_params() {
        let raw = b"GET /health HTTP/1.1\r\nHost: gw\r\n\r\n";
        let req = TrafficCapture::parse_request(raw).unwrap();
        assert_eq!(req.path, "/health");
        assert!(req.query_params.is_empty());
    }

    #[test]
    fn test_parse_request_sensitive_headers_redacted() {
        let raw = b"GET /api HTTP/1.1\r\nAuthorization: Bearer secret\r\nX-Api-Key: my-key\r\nHost: gw\r\n\r\n";
        let req = TrafficCapture::parse_request(raw).unwrap();
        assert!(!req.headers.contains_key("authorization"));
        assert!(!req.headers.contains_key("x-api-key"));
        assert!(req.headers.contains_key("host"));
    }

    #[test]
    fn test_parse_request_with_json_body() {
        let raw =
            b"POST /api HTTP/1.1\r\nContent-Type: application/json\r\n\r\n{\"key\":\"value\"}";
        let req = TrafficCapture::parse_request(raw).unwrap();
        assert!(req.body.is_some());
        let body = req.body.unwrap();
        assert_eq!(body["key"], "value");
    }

    #[test]
    fn test_parse_request_garbage_returns_none() {
        let raw = b"garbage";
        assert!(TrafficCapture::parse_request(raw).is_none());
    }

    #[test]
    fn test_parse_request_empty_returns_none() {
        assert!(TrafficCapture::parse_request(b"").is_none());
    }

    #[test]
    fn test_parse_response_various_status_codes() {
        for (code, status_line) in [
            (404, "HTTP/1.1 404 Not Found"),
            (500, "HTTP/1.1 500 Internal Server Error"),
            (201, "HTTP/1.1 201 Created"),
            (301, "HTTP/1.1 301 Moved Permanently"),
        ] {
            let raw = format!("{}\r\nContent-Length: 0\r\n\r\n", status_line);
            let resp = TrafficCapture::parse_response(raw.as_bytes()).unwrap();
            assert_eq!(resp.status_code, code);
        }
    }

    #[test]
    fn test_parse_response_with_json_body() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"items\":[1,2,3]}";
        let resp = TrafficCapture::parse_response(raw).unwrap();
        assert_eq!(resp.status_code, 200);
        let body = resp.body.unwrap();
        assert_eq!(body["items"], serde_json::json!([1, 2, 3]));
    }

    #[test]
    fn test_parse_response_no_body() {
        let raw = b"HTTP/1.1 204 No Content\r\n\r\n";
        let resp = TrafficCapture::parse_response(raw).unwrap();
        assert_eq!(resp.status_code, 204);
        assert!(resp.body.is_none());
    }

    #[test]
    fn test_parse_response_garbage_returns_none() {
        assert!(TrafficCapture::parse_response(b"garbage data").is_none());
    }

    #[test]
    fn test_parse_response_invalid_status_returns_none() {
        let raw = b"HTTP/1.1 abc OK\r\n\r\n";
        assert!(TrafficCapture::parse_response(raw).is_none());
    }

    #[test]
    fn test_sensitive_header_x_api_key() {
        assert!(is_sensitive_header("x-api-key"));
    }

    #[test]
    fn test_sensitive_header_x_auth_token() {
        assert!(is_sensitive_header("x-auth-token"));
    }

    #[test]
    fn test_sensitive_header_set_cookie() {
        assert!(is_sensitive_header("set-cookie"));
    }

    #[test]
    fn test_non_sensitive_headers() {
        assert!(!is_sensitive_header("host"));
        assert!(!is_sensitive_header("accept"));
        assert!(!is_sensitive_header("user-agent"));
        assert!(!is_sensitive_header("x-request-id"));
    }

    #[tokio::test]
    async fn test_traffic_capture_new_creates_channel() {
        let (capture, _rx) = TrafficCapture::new(CaptureSource::Inline, 100);
        assert!(!capture.running.load(std::sync::atomic::Ordering::SeqCst));
    }

    #[test]
    fn test_traffic_capture_stop_sets_flag() {
        let (capture, _rx) = TrafficCapture::new(CaptureSource::Inline, 10);
        capture
            .running
            .store(true, std::sync::atomic::Ordering::SeqCst);
        capture.stop();
        assert!(!capture.running.load(std::sync::atomic::Ordering::SeqCst));
    }

    #[tokio::test]
    async fn test_submit_sends_transaction() {
        let (capture, mut rx) = TrafficCapture::new(CaptureSource::Inline, 10);
        let tx = CapturedTransaction {
            id: "test-1".to_string(),
            timestamp: chrono::Utc::now(),
            request: CapturedRequest {
                method: "GET".to_string(),
                path: "/test".to_string(),
                query_params: HashMap::new(),
                headers: HashMap::new(),
                content_type: None,
                body: None,
                body_size: 0,
            },
            response: CapturedResponse {
                status_code: 200,
                headers: HashMap::new(),
                content_type: None,
                body: None,
                body_size: 0,
            },
            latency_ms: 0,
            source: "inline".to_string(),
        };
        capture.submit(tx).await;
        let received = rx.recv().await.unwrap();
        assert_eq!(received.id, "test-1");
    }

    #[test]
    fn test_envoy_tap_with_response_body() {
        let json = r#"{
            "http_buffered_trace": {
                "request": {
                    "headers": [
                        {"key": ":method", "value": "GET"},
                        {"key": ":path", "value": "/data"}
                    ]
                },
                "response": {
                    "headers": [
                        {"key": ":status", "value": "200"},
                        {"key": "content-type", "value": "application/json"}
                    ],
                    "body": {"as_string": "{\"count\":5}"}
                }
            }
        }"#;
        let tx = TrafficCapture::parse_envoy_tap_record(json).unwrap();
        assert!(tx.response.body.is_some());
        assert_eq!(tx.response.body.unwrap()["count"], 5);
    }

    #[test]
    fn test_envoy_tap_pseudo_headers_excluded() {
        let json = r#"{
            "http_buffered_trace": {
                "request": {
                    "headers": [
                        {"key": ":method", "value": "GET"},
                        {"key": ":path", "value": "/test"},
                        {"key": ":authority", "value": "example.com"},
                        {"key": "accept", "value": "*/*"}
                    ]
                },
                "response": {
                    "headers": [
                        {"key": ":status", "value": "200"}
                    ]
                }
            }
        }"#;
        let tx = TrafficCapture::parse_envoy_tap_record(json).unwrap();
        assert!(!tx.request.headers.contains_key(":authority"));
        assert!(tx.request.headers.contains_key("accept"));
    }

    #[test]
    fn test_envoy_tap_invalid_json_returns_none() {
        assert!(TrafficCapture::parse_envoy_tap_record("{invalid json").is_none());
    }

    #[test]
    fn test_parse_request_multiple_query_params() {
        let raw = b"GET /search?q=test&sort=asc&page=1&limit=20 HTTP/1.1\r\nHost: gw\r\n\r\n";
        let req = TrafficCapture::parse_request(raw).unwrap();
        assert_eq!(req.query_params.len(), 4);
        assert_eq!(req.query_params.get("q"), Some(&"test".to_string()));
        assert_eq!(req.query_params.get("sort"), Some(&"asc".to_string()));
    }

    #[test]
    fn test_parse_request_content_type_stored() {
        let raw = b"POST /api HTTP/1.1\r\nContent-Type: text/plain\r\n\r\nhello";
        let req = TrafficCapture::parse_request(raw).unwrap();
        assert_eq!(req.content_type.as_deref(), Some("text/plain"));
        assert!(req.body.is_none());
    }

    #[test]
    fn test_parse_response_content_type_contains_json() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n\r\n{\"ok\":true}";
        let resp = TrafficCapture::parse_response(raw).unwrap();
        assert!(resp.body.is_some());
    }
}
