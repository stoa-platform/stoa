//! Protocol Binders — Contract-to-Protocol transformers
//!
//! Protocol binders transform a UAC contract spec into protocol-specific
//! artifacts (REST routes, MCP tools, etc.). Each binder implements the
//! `ProtocolBinder` trait.
//!
//! "Define Once, Expose Everywhere."

pub mod mcp;
pub mod rest;

use crate::mcp::tools::ToolDefinition;
use crate::routes::ApiRoute;
use crate::uac::schema::UacContractSpec;

/// Output from a protocol binder.
#[derive(Debug)]
pub enum BindingOutput {
    /// REST routes generated from a contract.
    Routes(Vec<ApiRoute>),
    /// MCP tool definitions generated from a contract.
    Tools(Vec<ToolDefinition>),
}

/// Protocol binder trait — transforms contracts into protocol artifacts.
///
/// Async from day 1 (Council adjustment #3) to support binders that
/// need external lookups (e.g., schema validation, CP API calls).
#[allow(async_fn_in_trait)]
pub trait ProtocolBinder {
    /// Bind a contract spec to protocol-specific artifacts.
    async fn bind(&self, contract: &UacContractSpec) -> Result<BindingOutput, String>;

    /// Remove all artifacts generated from a specific contract.
    async fn unbind(&self, contract_key: &str) -> Result<usize, String>;
}
