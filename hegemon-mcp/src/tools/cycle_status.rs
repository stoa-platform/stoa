//! hegemon_cycle_status — Get current Linear sprint cycle status.
//!
//! Queries Linear GraphQL API for the active cycle on the HEGEMON team.
//! Returns cycle name, dates, ticket counts by status, and completion percentage.

use crate::AppConfig;
use serde::{Deserialize, Serialize};
use tracing::warn;

const LINEAR_API_URL: &str = "https://api.linear.app/graphql";

#[derive(Debug, Deserialize)]
struct LinearGraphQLResponse {
    data: Option<LinearData>,
    errors: Option<Vec<LinearError>>,
}

#[derive(Debug, Deserialize)]
struct LinearError {
    message: String,
}

#[derive(Debug, Deserialize)]
struct LinearData {
    team: Option<LinearTeam>,
}

#[derive(Debug, Deserialize)]
struct LinearTeam {
    #[serde(rename = "activeCycle")]
    active_cycle: Option<LinearCycle>,
}

#[derive(Debug, Deserialize)]
struct LinearCycle {
    name: Option<String>,
    number: Option<u32>,
    #[serde(rename = "startsAt")]
    starts_at: Option<String>,
    #[serde(rename = "endsAt")]
    ends_at: Option<String>,
    #[serde(rename = "completedScopeSize")]
    completed_scope: Option<f64>,
    #[serde(rename = "scopeSize")]
    scope_size: Option<f64>,
    issues: Option<LinearIssueConnection>,
}

#[derive(Debug, Deserialize)]
struct LinearIssueConnection {
    nodes: Vec<LinearIssue>,
}

#[derive(Debug, Deserialize)]
struct LinearIssue {
    identifier: String,
    title: String,
    state: LinearState,
    estimate: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct LinearState {
    name: String,
    #[serde(rename = "type")]
    state_type: String,
}

#[derive(Debug, Serialize)]
struct CycleResponse {
    cycle_name: String,
    cycle_number: u32,
    starts_at: String,
    ends_at: String,
    completion_percent: f64,
    scope_points: f64,
    completed_points: f64,
    tickets: TicketCounts,
    issues: Vec<CycleIssue>,
}

#[derive(Debug, Serialize)]
struct TicketCounts {
    todo: u32,
    in_progress: u32,
    done: u32,
    total: u32,
}

#[derive(Debug, Serialize)]
struct CycleIssue {
    id: String,
    title: String,
    status: String,
    estimate: Option<f64>,
}

pub async fn execute(
    client: &reqwest::Client,
    config: &AppConfig,
) -> Result<String, String> {
    let api_key = config
        .linear_api_key
        .as_deref()
        .ok_or("LINEAR_API_KEY not configured")?;

    let team_id = config
        .linear_team_id
        .as_deref()
        .unwrap_or("CAB");

    let query = format!(
        r#"{{
            team(id: "{team_id}") {{
                activeCycle {{
                    name
                    number
                    startsAt
                    endsAt
                    completedScopeSize
                    scopeSize
                    issues {{
                        nodes {{
                            identifier
                            title
                            state {{ name type }}
                            estimate
                        }}
                    }}
                }}
            }}
        }}"#
    );

    let response = client
        .post(LINEAR_API_URL)
        .header("Authorization", api_key)
        .header("Content-Type", "application/json")
        .json(&serde_json::json!({ "query": query }))
        .send()
        .await
        .map_err(|e| format!("Linear API request failed: {e}"))?;

    if !response.status().is_success() {
        let status = response.status();
        warn!(status = %status, "Linear API returned non-success");
        return Err(format!("Linear API returned {status}"));
    }

    let gql: LinearGraphQLResponse = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse Linear response: {e}"))?;

    if let Some(errors) = gql.errors {
        let msgs: Vec<&str> = errors.iter().map(|e| e.message.as_str()).collect();
        return Err(format!("Linear GraphQL errors: {}", msgs.join(", ")));
    }

    let cycle = gql
        .data
        .and_then(|d| d.team)
        .and_then(|t| t.active_cycle)
        .ok_or("No active cycle found")?;

    let issues = cycle.issues.map(|c| c.nodes).unwrap_or_default();

    let mut todo = 0u32;
    let mut in_progress = 0u32;
    let mut done = 0u32;

    let cycle_issues: Vec<CycleIssue> = issues
        .into_iter()
        .map(|i| {
            match i.state.state_type.as_str() {
                "completed" | "canceled" => done += 1,
                "started" => in_progress += 1,
                _ => todo += 1,
            }
            CycleIssue {
                id: i.identifier,
                title: i.title,
                status: i.state.name,
                estimate: i.estimate,
            }
        })
        .collect();

    let total = todo + in_progress + done;
    let scope = cycle.scope_size.unwrap_or(0.0);
    let completed = cycle.completed_scope.unwrap_or(0.0);
    let pct = if scope > 0.0 {
        (completed / scope * 100.0).round()
    } else {
        0.0
    };

    let resp = CycleResponse {
        cycle_name: cycle.name.unwrap_or_else(|| format!("Cycle {}", cycle.number.unwrap_or(0))),
        cycle_number: cycle.number.unwrap_or(0),
        starts_at: cycle.starts_at.unwrap_or_default(),
        ends_at: cycle.ends_at.unwrap_or_default(),
        completion_percent: pct,
        scope_points: scope,
        completed_points: completed,
        tickets: TicketCounts {
            todo,
            in_progress,
            done,
            total,
        },
        issues: cycle_issues,
    };

    serde_json::to_string_pretty(&resp)
        .map_err(|e| format!("JSON serialization failed: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_linear_response() {
        let json = r#"{
            "data": {
                "team": {
                    "activeCycle": {
                        "name": "C12",
                        "number": 12,
                        "startsAt": "2026-02-24",
                        "endsAt": "2026-03-07",
                        "completedScopeSize": 15.0,
                        "scopeSize": 40.0,
                        "issues": {
                            "nodes": [
                                {
                                    "identifier": "CAB-1636",
                                    "title": "HEGEMON Gateway",
                                    "state": {"name": "In Progress", "type": "started"},
                                    "estimate": 28
                                }
                            ]
                        }
                    }
                }
            }
        }"#;

        let resp: LinearGraphQLResponse = serde_json::from_str(json).unwrap();
        let cycle = resp.data.unwrap().team.unwrap().active_cycle.unwrap();
        assert_eq!(cycle.name.unwrap(), "C12");
        assert_eq!(cycle.number.unwrap(), 12);
        assert_eq!(cycle.issues.unwrap().nodes.len(), 1);
    }

    #[test]
    fn test_deserialize_no_active_cycle() {
        let json = r#"{"data": {"team": {"activeCycle": null}}}"#;
        let resp: LinearGraphQLResponse = serde_json::from_str(json).unwrap();
        let cycle = resp.data.unwrap().team.unwrap().active_cycle;
        assert!(cycle.is_none());
    }

    #[test]
    fn test_deserialize_graphql_error() {
        let json = r#"{"errors": [{"message": "Not found"}]}"#;
        let resp: LinearGraphQLResponse = serde_json::from_str(json).unwrap();
        assert!(resp.errors.is_some());
        assert_eq!(resp.errors.unwrap()[0].message, "Not found");
    }
}
