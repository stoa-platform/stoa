//! Token Optimization Module (Phase 4: CAB-1105)
//!
//! 80%+ token reduction for AI clients. The killer differentiator.
//! Reference: ADR-015
//!
//! # Pipeline Stages
//!
//! 1. **Null Removal**: Remove null, "", [], {} recursively
//! 2. **Schema Pruning**: Remove description, example, x-* from OpenAPI schemas
//! 3. **Key Shortening**: Reversible mapping (description→desc, properties→props)
//! 4. **Pagination Injection**: Truncate large arrays with "...and N more"
//!
//! # Client Capability Negotiation
//!
//! During `initialize`, clients can declare preferences:
//! ```json
//! {
//!   "capabilities": {
//!     "tokenOptimization": {
//!       "level": "aggressive",
//!       "maxResponseTokens": 4096
//!     }
//!   }
//! }
//! ```

mod token;

pub use token::OptimizationLevel;
pub use token::{OptimizationSettings, TokenOptimizer};

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_optimization_level_default() {
        let settings = OptimizationSettings::default();
        assert_eq!(settings.level, OptimizationLevel::None);
    }

    #[test]
    fn test_parse_from_capabilities() {
        let caps = json!({
            "tokenOptimization": {
                "level": "aggressive",
                "maxResponseTokens": 4096
            }
        });

        let settings = OptimizationSettings::from_capabilities(&caps);
        assert_eq!(settings.level, OptimizationLevel::Aggressive);
        assert_eq!(settings.max_response_tokens, Some(4096));
    }

    #[test]
    fn test_parse_moderate_level() {
        let caps = json!({
            "tokenOptimization": {
                "level": "moderate"
            }
        });

        let settings = OptimizationSettings::from_capabilities(&caps);
        assert_eq!(settings.level, OptimizationLevel::Moderate);
    }

    #[test]
    fn test_parse_missing_capabilities() {
        let caps = json!({});
        let settings = OptimizationSettings::from_capabilities(&caps);
        assert_eq!(settings.level, OptimizationLevel::None);
    }
}
