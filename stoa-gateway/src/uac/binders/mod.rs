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

/// Start of a binder error that the publisher caused (bad contract, name
/// taken). The admin handler answers `400` with the message, not `500`.
pub const CONTRACT_REJECTED: &str = "contract rejected: ";

/// Split an endpoint path at its first parameter segment.
///
/// Returns the static part, trailing `/` included, and the rest:
/// `/customers/{id}/segment` → (`/customers/`, `{id}/segment`),
/// `/{id}` → (`/`, `{id}`). A path with no `{` segment is all static:
/// `/customers` → (`/customers`, ``).
pub fn split_path_template(path: &str) -> (&str, &str) {
    let mut start = 0;
    for segment in path.split('/') {
        if segment.contains('{') {
            return path.split_at(start);
        }
        start += segment.len() + 1;
    }
    (path, "")
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

#[cfg(test)]
mod tests {
    use super::split_path_template;

    #[test]
    fn path_template_splits_at_the_first_parameter_segment() {
        assert_eq!(
            split_path_template("/customers/{id}"),
            ("/customers/", "{id}")
        );
        assert_eq!(
            split_path_template("/customers/{id}/segment"),
            ("/customers/", "{id}/segment")
        );
        assert_eq!(
            split_path_template("/a/b/{x}/c/{y}"),
            ("/a/b/", "{x}/c/{y}")
        );
        assert_eq!(split_path_template("/{id}"), ("/", "{id}"));
        assert_eq!(
            split_path_template("/files/{name}.json"),
            ("/files/", "{name}.json")
        );
    }

    #[test]
    fn path_template_without_parameter_is_all_static() {
        assert_eq!(split_path_template("/customers"), ("/customers", ""));
        assert_eq!(split_path_template("/customers/"), ("/customers/", ""));
        assert_eq!(split_path_template("/"), ("/", ""));
    }
}
