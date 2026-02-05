//! Cache Module
//!
//! Semantic caching for MCP tool responses:
//! - Cache key: (tool_name, args_hash, tenant_id)
//! - Per-tool TTL configuration
//! - Automatic cache invalidation
//! - Only caches read-only tools (based on annotations)

pub mod semantic;

pub use semantic::{SemanticCache, SemanticCacheConfig};

// Re-export for future use
#[allow(unused_imports)]
pub use semantic::{CacheKey, CacheEntry};
