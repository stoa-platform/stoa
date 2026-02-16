//! Semantic Cache Module (Phase 6: CAB-1105)
//!
//! Caches tool responses for read-only operations.
//! Uses tool annotations (read_only_hint) to determine cacheability.
//!
//! # Cacheability Rules
//!
//! - `read_only_hint: true` → cacheable (Read, List, Search actions)
//! - `read_only_hint: false` → not cacheable (Create, Update, Delete)
//!
//! # Cache Key Format
//!
//! `{tenant}:{tool_name}:{hash(args)}`
//!
//! Note: Infrastructure prepared for tool response caching.
//! Actual integration in SSE handler is a Phase 7 enhancement.

mod semantic;

pub use semantic::SemanticCacheStats;
pub use semantic::{SemanticCache, SemanticCacheConfig};
