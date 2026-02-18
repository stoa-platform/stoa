//! MCP Notification Formatter (Phase 3: CAB-1179)
//!
//! Converts CnsEvent envelopes into MCP `notifications/send` JSON-RPC format.
//! Includes tool hints that suggest client-side actions based on event type.

use serde::Serialize;
use serde_json::Value;

use super::CnsEvent;

/// Tool hint suggesting a client-side action
#[derive(Debug, Clone, Serialize)]
pub struct ToolHint {
    pub action: String,
    pub reason: String,
}

/// Format a CnsEvent as an MCP `notifications/send` JSON-RPC notification.
pub fn format_notification(event: &CnsEvent) -> Value {
    let mut params = serde_json::json!({
        "type": event_namespace(&event.type_),
        "data": {
            "event": &event.type_,
            "source": &event.source,
            "tenant": &event.tenant_id,
            "timestamp": event.timestamp.to_rfc3339(),
            "payload": &event.payload,
        },
    });

    if let Some(hint) = tool_hint(&event.type_) {
        if let Ok(hint_val) = serde_json::to_value(hint) {
            params["hint"] = hint_val;
        }
    }

    serde_json::json!({
        "jsonrpc": "2.0",
        "method": "notifications/send",
        "params": params,
    })
}

/// Map event type to a namespace
fn event_namespace(event_type: &str) -> &str {
    if event_type.starts_with("api-") {
        "stoa.api.lifecycle"
    } else if event_type.starts_with("deploy") {
        "stoa.deployment.events"
    } else if event_type.starts_with("security") {
        "stoa.security.alerts"
    } else if event_type.starts_with("subscription") {
        "stoa.subscription.events"
    } else {
        "stoa.events"
    }
}

/// Format an MCP `notifications/tools/list_changed` JSON-RPC notification.
///
/// Per MCP spec, this is a parameter-less notification sent when the tool list
/// changes (tools added, removed, or updated). Clients should respond by
/// re-fetching the tool list via `tools/list`.
pub fn format_tools_list_changed() -> String {
    serde_json::json!({
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed"
    })
    .to_string()
}

/// Map event type to a suggested client-side action
fn tool_hint(event_type: &str) -> Option<ToolHint> {
    match event_type {
        "api-created" => Some(ToolHint {
            action: "tools/list".into(),
            reason: "New API available — refresh tool registry".into(),
        }),
        "api-updated" => Some(ToolHint {
            action: "tools/list".into(),
            reason: "API updated — refresh tool definitions".into(),
        }),
        "api-deleted" => Some(ToolHint {
            action: "tools/list".into(),
            reason: "API removed — refresh tool registry".into(),
        }),
        "subscription-changed" => Some(ToolHint {
            action: "resources/list".into(),
            reason: "Subscription updated — check credentials".into(),
        }),
        "deploy-request" => Some(ToolHint {
            action: "resources/list".into(),
            reason: "Deployment started — monitor progress".into(),
        }),
        "deployment-success" => Some(ToolHint {
            action: "tools/list".into(),
            reason: "Deployment complete — new version available".into(),
        }),
        "security-alert" => Some(ToolHint {
            action: "logging".into(),
            reason: "Security event — review alert details".into(),
        }),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    fn make_event(type_: &str) -> CnsEvent {
        CnsEvent {
            id: "evt-test".into(),
            type_: type_.into(),
            source: "control-plane-api".into(),
            tenant_id: "acme".into(),
            timestamp: Utc::now(),
            version: "1.0".into(),
            user_id: Some("user-1".into()),
            payload: serde_json::json!({"api_id": "api-42"}),
        }
    }

    #[test]
    fn test_format_notification_api_created() {
        let event = make_event("api-created");
        let notif = format_notification(&event);

        assert_eq!(notif["jsonrpc"], "2.0");
        assert_eq!(notif["method"], "notifications/send");
        assert_eq!(notif["params"]["type"], "stoa.api.lifecycle");
        assert_eq!(notif["params"]["data"]["event"], "api-created");
        assert_eq!(notif["params"]["data"]["tenant"], "acme");
        assert_eq!(notif["params"]["hint"]["action"], "tools/list");
    }

    #[test]
    fn test_format_notification_deployment_success() {
        let event = make_event("deployment-success");
        let notif = format_notification(&event);

        assert_eq!(notif["params"]["type"], "stoa.deployment.events");
        assert_eq!(notif["params"]["hint"]["action"], "tools/list");
    }

    #[test]
    fn test_format_notification_security_alert() {
        let event = make_event("security-alert");
        let notif = format_notification(&event);

        assert_eq!(notif["params"]["type"], "stoa.security.alerts");
        assert_eq!(notif["params"]["hint"]["action"], "logging");
    }

    #[test]
    fn test_format_notification_unknown_type_no_hint() {
        let event = make_event("custom-event");
        let notif = format_notification(&event);

        assert_eq!(notif["params"]["type"], "stoa.events");
        assert!(notif["params"]["hint"].is_null());
    }

    #[test]
    fn test_event_namespace_mapping() {
        assert_eq!(event_namespace("api-created"), "stoa.api.lifecycle");
        assert_eq!(event_namespace("api-updated"), "stoa.api.lifecycle");
        assert_eq!(event_namespace("deploy-request"), "stoa.deployment.events");
        assert_eq!(
            event_namespace("deployment-success"),
            "stoa.deployment.events"
        );
        assert_eq!(event_namespace("security-alert"), "stoa.security.alerts");
        assert_eq!(
            event_namespace("subscription-changed"),
            "stoa.subscription.events"
        );
        assert_eq!(event_namespace("unknown"), "stoa.events");
    }

    #[test]
    fn test_format_tools_list_changed() {
        let json_str = format_tools_list_changed();
        let val: serde_json::Value = serde_json::from_str(&json_str).unwrap();

        assert_eq!(val["jsonrpc"], "2.0");
        assert_eq!(val["method"], "notifications/tools/list_changed");
        // MCP spec: no params field for list_changed
        assert!(val.get("params").is_none());
    }

    #[test]
    fn test_tool_hint_all_known_types() {
        assert!(tool_hint("api-created").is_some());
        assert!(tool_hint("api-updated").is_some());
        assert!(tool_hint("api-deleted").is_some());
        assert!(tool_hint("subscription-changed").is_some());
        assert!(tool_hint("deploy-request").is_some());
        assert!(tool_hint("deployment-success").is_some());
        assert!(tool_hint("security-alert").is_some());
        assert!(tool_hint("completely-unknown").is_none());
    }
}
