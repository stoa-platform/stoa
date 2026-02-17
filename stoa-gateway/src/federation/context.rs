//! Federation sub-account context (CAB-1362)
//!
//! Extracted from JWT claims by federation middleware.
//! Injected as request extension for downstream handlers.

use std::collections::HashSet;

/// Federation sub-account context extracted from JWT claims.
/// Injected as request extension by federation_middleware.
#[derive(Debug, Clone)]
pub struct SubAccountContext {
    /// Sub-account identifier
    pub sub_account_id: String,
    /// Master account that owns this sub-account
    pub master_account_id: String,
    /// Tenant the master account belongs to
    pub tenant_id: String,
    /// Allowed tools for this sub-account (None = not yet loaded)
    pub allowed_tools: Option<HashSet<String>>,
}

impl SubAccountContext {
    /// Check if a tool is allowed for this sub-account.
    ///
    /// - `Some(set)` → tool must be in the set
    /// - `None` → allow-list not loaded (permissive, log warning)
    pub fn is_tool_allowed(&self, tool_name: &str) -> bool {
        match &self.allowed_tools {
            Some(allowed) => allowed.contains(tool_name),
            None => true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx_with_tools(tools: Vec<&str>) -> SubAccountContext {
        SubAccountContext {
            sub_account_id: "sub-1".to_string(),
            master_account_id: "master-1".to_string(),
            tenant_id: "acme".to_string(),
            allowed_tools: Some(tools.into_iter().map(String::from).collect()),
        }
    }

    #[test]
    fn test_tool_allowed() {
        let ctx = ctx_with_tools(vec!["tool_a", "tool_b"]);
        assert!(ctx.is_tool_allowed("tool_a"));
        assert!(ctx.is_tool_allowed("tool_b"));
    }

    #[test]
    fn test_tool_denied() {
        let ctx = ctx_with_tools(vec!["tool_a"]);
        assert!(!ctx.is_tool_allowed("tool_c"));
    }

    #[test]
    fn test_none_is_permissive() {
        let ctx = SubAccountContext {
            sub_account_id: "sub-1".to_string(),
            master_account_id: "master-1".to_string(),
            tenant_id: "acme".to_string(),
            allowed_tools: None,
        };
        assert!(ctx.is_tool_allowed("anything"));
    }
}
