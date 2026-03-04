//! hegemon_workers_status — List active HEGEMON worker sessions from PocketBase.
//!
//! Queries PocketBase `sessions` collection for active sessions (status != "done").
//! Returns worker role, branch, ticket, step, and last activity.

use crate::AppConfig;
use serde::{Deserialize, Serialize};
use tracing::warn;

#[derive(Debug, Deserialize)]
struct PocketBaseResponse {
    #[serde(default)]
    items: Vec<PocketBaseSession>,
    #[serde(rename = "totalItems", default)]
    total_items: u32,
}

#[derive(Debug, Deserialize)]
struct PocketBaseSession {
    #[serde(default)]
    role: String,
    #[serde(default)]
    ticket: String,
    #[serde(default)]
    branch: String,
    #[serde(default)]
    step: String,
    #[serde(default)]
    status: String,
    #[serde(default)]
    hostname: String,
    #[serde(default)]
    updated: String,
}

#[derive(Debug, Serialize)]
struct WorkerStatus {
    role: String,
    ticket: String,
    branch: String,
    step: String,
    status: String,
    hostname: String,
    last_activity: String,
}

#[derive(Debug, Serialize)]
struct WorkersResponse {
    workers: Vec<WorkerStatus>,
    total: u32,
}

pub async fn execute(
    client: &reqwest::Client,
    config: &AppConfig,
) -> Result<String, String> {
    let url = format!(
        "{}/api/collections/sessions/records?filter=(status!='done')&sort=-updated&perPage=20",
        config.pocketbase_url
    );

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("PocketBase request failed: {e}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        warn!(status = %status, "PocketBase returned non-success");
        return Err(format!("PocketBase returned {status}: {body}"));
    }

    let pb_response: PocketBaseResponse = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse PocketBase response: {e}"))?;

    let workers: Vec<WorkerStatus> = pb_response
        .items
        .into_iter()
        .map(|s| WorkerStatus {
            role: s.role,
            ticket: s.ticket,
            branch: s.branch,
            step: s.step,
            status: s.status,
            hostname: s.hostname,
            last_activity: s.updated,
        })
        .collect();

    let resp = WorkersResponse {
        total: pb_response.total_items,
        workers,
    };

    serde_json::to_string_pretty(&resp)
        .map_err(|e| format!("JSON serialization failed: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_pocketbase_response() {
        let json = r#"{
            "items": [
                {
                    "role": "backend",
                    "ticket": "CAB-1350",
                    "branch": "feat/cab-1350",
                    "step": "pr-created",
                    "status": "in_progress",
                    "hostname": "worker-1",
                    "updated": "2026-03-01T12:00:00Z"
                }
            ],
            "totalItems": 1
        }"#;

        let resp: PocketBaseResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.total_items, 1);
        assert_eq!(resp.items.len(), 1);
        assert_eq!(resp.items[0].role, "backend");
        assert_eq!(resp.items[0].ticket, "CAB-1350");
    }

    #[test]
    fn test_deserialize_empty_response() {
        let json = r#"{"items": [], "totalItems": 0}"#;
        let resp: PocketBaseResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.total_items, 0);
        assert!(resp.items.is_empty());
    }
}
