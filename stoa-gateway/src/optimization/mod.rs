//! Token Optimization Module
//!
//! Reduces token consumption for AI clients by 80%+.
//! This is STOA's killer differentiator.
//!
//! ## Optimization Strategies
//!
//! 1. **Schema Pruning**: Strip `description`, `example`, `x-*` extensions from OpenAPI schemas
//! 2. **Null Removal**: Remove null/empty fields from JSON responses
//! 3. **Key Shortening**: `description` -> `desc`, `properties` -> `props` (reversible)
//! 4. **Pagination Injection**: Large arrays -> first N items + "...and N more"
//!
//! ## Usage
//!
//! ```rust,ignore
//! use stoa_gateway::optimization::{TokenOptimizer, OptimizationLevel};
//!
//! let optimizer = TokenOptimizer::new(OptimizationLevel::Moderate);
//! let optimized = optimizer.optimize_json(&input)?;
//! ```

mod token;

#[allow(unused_imports)]
pub use token::{OptimizationLevel, OptimizationPrefs, TokenOptimizer};

// Re-export for future use (key expansion API)
#[allow(unused_imports)]
pub use token::{expand_keys, OptimizationResult, KEY_EXPANSION_MAP, KEY_SHORTENING_MAP};
