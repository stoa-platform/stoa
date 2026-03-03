//! hegemon_metrics — Query key HEGEMON runtime metrics from Prometheus.
//!
//! Queries Prometheus instant query API for pre-defined PromQL expressions.
//! Returns request rates, error rates, token usage, and circuit breaker state.

use crate::AppConfig;
use serde::{Deserialize, Serialize};
use tracing::warn;

#[derive(Debug, Deserialize)]
struct PromResponse {
    status: String,
    data: Option<PromData>,
}

#[derive(Debug, Deserialize)]
struct PromData {
    #[serde(rename = "resultType")]
    result_type: String,
    result: Vec<PromResult>,
}

#[derive(Debug, Deserialize)]
struct PromResult {
    metric: serde_json::Value,
    value: (f64, String),
}

#[derive(Debug, Serialize)]
struct MetricsResponse {
    #[serde(skip_serializing_if = "Option::is_none")]
    requests: Option<Vec<MetricEntry>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    errors: Option<Vec<MetricEntry>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tokens: Option<Vec<MetricEntry>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    circuit_breaker: Option<Vec<MetricEntry>>,
}

#[derive(Debug, Serialize)]
struct MetricEntry {
    labels: serde_json::Value,
    value: String,
}

struct MetricQuery {
    name: &'static str,
    promql: &'static str,
}

const QUERIES: &[MetricQuery] = &[
    MetricQuery {
        name: "requests",
        promql: r#"sum(rate(stoa_http_requests_total{tenant="hegemon"}[5m])) by (consumer)"#,
    },
    MetricQuery {
        name: "errors",
        promql: r#"sum(rate(stoa_http_requests_total{tenant="hegemon",status=~"[45].."}[5m])) by (consumer, status)"#,
    },
    MetricQuery {
        name: "tokens",
        promql: r#"sum(rate(stoa_llm_tokens_total{tenant="hegemon"}[5m])) by (consumer, direction)"#,
    },
    MetricQuery {
        name: "circuit_breaker",
        promql: r#"stoa_circuit_breaker_state{tenant="hegemon"}"#,
    },
];

async fn query_prometheus(
    client: &reqwest::Client,
    base_url: &str,
    promql: &str,
) -> Result<Vec<MetricEntry>, String> {
    let url = format!("{base_url}/api/v1/query");

    let response = client
        .get(&url)
        .query(&[("query", promql)])
        .send()
        .await
        .map_err(|e| format!("Prometheus request failed: {e}"))?;

    if !response.status().is_success() {
        let status = response.status();
        warn!(status = %status, promql = %promql, "Prometheus returned non-success");
        return Err(format!("Prometheus returned {status}"));
    }

    let prom: PromResponse = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse Prometheus response: {e}"))?;

    if prom.status != "success" {
        return Err(format!("Prometheus query status: {}", prom.status));
    }

    let data = prom.data.ok_or("No data in Prometheus response")?;

    Ok(data
        .result
        .into_iter()
        .map(|r| MetricEntry {
            labels: r.metric,
            value: r.value.1,
        })
        .collect())
}

pub async fn execute(
    client: &reqwest::Client,
    config: &AppConfig,
    metric_filter: Option<String>,
) -> Result<String, String> {
    let queries: Vec<&MetricQuery> = match metric_filter.as_deref() {
        Some(name) => QUERIES
            .iter()
            .filter(|q| q.name == name)
            .collect(),
        None => QUERIES.iter().collect(),
    };

    if queries.is_empty() {
        return Err("Unknown metric filter. Valid: requests, errors, tokens, circuit_breaker".to_string());
    }

    let mut resp = MetricsResponse {
        requests: None,
        errors: None,
        tokens: None,
        circuit_breaker: None,
    };

    for q in queries {
        match query_prometheus(client, &config.prometheus_url, q.promql).await {
            Ok(entries) => match q.name {
                "requests" => resp.requests = Some(entries),
                "errors" => resp.errors = Some(entries),
                "tokens" => resp.tokens = Some(entries),
                "circuit_breaker" => resp.circuit_breaker = Some(entries),
                _ => {}
            },
            Err(e) => {
                warn!(metric = %q.name, error = %e, "Failed to query metric");
                // Graceful degradation: include error as a single entry
                let error_entry = vec![MetricEntry {
                    labels: serde_json::json!({"error": true}),
                    value: e,
                }];
                match q.name {
                    "requests" => resp.requests = Some(error_entry),
                    "errors" => resp.errors = Some(error_entry),
                    "tokens" => resp.tokens = Some(error_entry),
                    "circuit_breaker" => resp.circuit_breaker = Some(error_entry),
                    _ => {}
                }
            }
        }
    }

    serde_json::to_string_pretty(&resp)
        .map_err(|e| format!("JSON serialization failed: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_prometheus_response() {
        let json = r#"{
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"consumer": "worker-1"},
                        "value": [1709312345.0, "0.5"]
                    }
                ]
            }
        }"#;

        let resp: PromResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.status, "success");
        let data = resp.data.unwrap();
        assert_eq!(data.result_type, "vector");
        assert_eq!(data.result.len(), 1);
        assert_eq!(data.result[0].value.1, "0.5");
    }

    #[test]
    fn test_deserialize_empty_result() {
        let json = r#"{
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": []
            }
        }"#;

        let resp: PromResponse = serde_json::from_str(json).unwrap();
        assert!(resp.data.unwrap().result.is_empty());
    }

    #[test]
    fn test_queries_count() {
        assert_eq!(QUERIES.len(), 4);
        let names: Vec<&str> = QUERIES.iter().map(|q| q.name).collect();
        assert!(names.contains(&"requests"));
        assert!(names.contains(&"errors"));
        assert!(names.contains(&"tokens"));
        assert!(names.contains(&"circuit_breaker"));
    }

    #[test]
    fn test_metrics_response_serialization_skips_none() {
        let resp = MetricsResponse {
            requests: Some(vec![MetricEntry {
                labels: serde_json::json!({"consumer": "worker-1"}),
                value: "0.5".to_string(),
            }]),
            errors: None,
            tokens: None,
            circuit_breaker: None,
        };

        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("requests"));
        assert!(!json.contains("errors"));
        assert!(!json.contains("tokens"));
        assert!(!json.contains("circuit_breaker"));
    }
}
