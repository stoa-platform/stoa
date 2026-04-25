//! Catalog tool expansion mode (CAB-2113 Phase 0).
//!
//! `per-op` is the canonical kebab-case value; `per_operation` is accepted as
//! a deprecated alias so existing docs / manifests keep parsing (PR3 doc drift
//! fix: `control-plane-api/src/routers/portal.py` pre-2026-04-19 used the
//! snake form). Prefer the canonical form in new configs.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum ExpansionMode {
    /// One `{action, params}` tool per API (legacy `/apis`).
    #[default]
    Coarse,
    /// One tool per OpenAPI operation via `/apis/expanded`.
    // TODO(GW-3): drop the `per_operation` snake_case alias after the
    // post-2026-05-15 doc-drift window closes. Only `per-op` should remain.
    #[serde(alias = "per_operation")]
    PerOp,
}

#[cfg(test)]
mod tests {
    use super::ExpansionMode;

    #[test]
    fn expansion_mode_accepts_kebab_and_snake_alias() {
        // Canonical kebab-case value (CAB-2113 Phase 0).
        let kebab: ExpansionMode = serde_json::from_str("\"per-op\"").unwrap();
        assert_eq!(kebab, ExpansionMode::PerOp);

        // Deprecated snake-case alias — kept only for the PR3 doc-drift window
        // on `control-plane-api/src/routers/portal.py`. Drop with Release N+1.
        let snake: ExpansionMode = serde_json::from_str("\"per_operation\"").unwrap();
        assert_eq!(snake, ExpansionMode::PerOp);

        // Default stays coarse — flipping to per-op must be explicit.
        assert_eq!(ExpansionMode::default(), ExpansionMode::Coarse);
    }
}
