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
use crate::uac::schema::{UacContractSpec, UacEndpoint};

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

/// Refuse a contract with an endpoint the binders cannot serve.
///
/// Both binders call it before any registry change, so a refused contract
/// leaves the routes and tools already published as they were. The error
/// starts with [`CONTRACT_REJECTED`] and names the endpoint by index and
/// path. Refused:
/// - a `backend_url` with `{` or `}`: it is the upstream URL of the static
///   part of the path, not a template;
/// - a `backend_url` with `?` or `#`: the rest of the path is appended to
///   it, and would land in the query or the fragment;
/// - a path that does not start with `/`;
/// - an empty segment (`/a//b`) or a dot segment (`/a/./b`, `/a/../b`); a
///   final `/` (`/customers/`) is kept;
/// - unmatched braces (`/customers/{id`) or an empty parameter (`/a/{}`);
/// - a parameter that is not a whole segment (`/a{id}`, `/files/f-{id}`);
/// - a parameter name used twice (`/a/{id}/b/{id}`).
pub fn check_endpoint_templates(contract: &UacContractSpec) -> Result<(), String> {
    for (index, endpoint) in contract.endpoints.iter().enumerate() {
        if let Err(reason) = check_endpoint_template(endpoint) {
            return Err(format!(
                "{CONTRACT_REJECTED}endpoints[{index}] ({:?}): {reason}",
                endpoint.path
            ));
        }
    }
    Ok(())
}

fn check_endpoint_template(endpoint: &UacEndpoint) -> Result<(), String> {
    if endpoint.backend_url.contains(['{', '}']) {
        return Err(
            "backend_url must not contain { or }: it is the upstream URL of the static part of the path, not a template"
                .to_string(),
        );
    }
    if endpoint.backend_url.contains(['?', '#']) {
        return Err(
            "backend_url must not contain ? or #: the rest of the path is appended to it, and would land in the query or the fragment"
                .to_string(),
        );
    }
    let Some(segments) = endpoint.path.strip_prefix('/') else {
        return Err("path must start with /".to_string());
    };
    let segments: Vec<&str> = segments.split('/').collect();
    let last = segments.len() - 1;
    let mut names: Vec<&str> = Vec::new();
    for (position, segment) in segments.iter().enumerate() {
        match *segment {
            "" if position == last => {}
            "" => return Err("path must not have an empty segment (//)".to_string()),
            "." | ".." => return Err(format!("path must not have a dot segment ({segment:?})")),
            _ => {}
        }
        if let Some(name) = check_path_segment(segment)? {
            if names.contains(&name) {
                return Err(format!("parameter {{{name}}} is used twice in the path"));
            }
            names.push(name);
        }
    }
    Ok(())
}

/// A segment is static (no brace) or exactly one `{name}` parameter.
/// Returns the parameter name, if the segment is one.
fn check_path_segment(segment: &str) -> Result<Option<&str>, String> {
    if !segment.contains(['{', '}']) {
        return Ok(None);
    }
    let mut open = false;
    for c in segment.chars() {
        match c {
            '{' if open => return Err(format!("segment {segment:?} has unbalanced braces")),
            '}' if !open => return Err(format!("segment {segment:?} has unbalanced braces")),
            '{' => open = true,
            '}' => open = false,
            _ => {}
        }
    }
    if open {
        return Err(format!("segment {segment:?} has unbalanced braces"));
    }
    match segment
        .strip_prefix('{')
        .and_then(|rest| rest.strip_suffix('}'))
    {
        Some("") => Err(format!("segment {segment:?} has an empty parameter name")),
        Some(name) if !name.contains(['{', '}']) => Ok(Some(name)),
        _ => Err(format!(
            "segment {segment:?}: a parameter must be the whole segment, as in /{{id}}"
        )),
    }
}

/// Split an endpoint path at its first parameter segment.
///
/// Returns the static part, trailing `/` included, and the rest:
/// `/customers/{id}/segment` → (`/customers/`, `{id}/segment`),
/// `/{id}` → (`/`, `{id}`). A path with no `{` segment is all static:
/// `/customers` → (`/customers`, ``). The path is expected to have passed
/// [`check_endpoint_templates`].
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
    use super::{check_endpoint_templates, split_path_template, CONTRACT_REJECTED};
    use crate::uac::schema::{UacContractSpec, UacEndpoint};

    fn contract_with(path: &str, backend_url: &str) -> UacContractSpec {
        let endpoint = |path: &str, backend_url: &str| UacEndpoint {
            path: path.to_string(),
            methods: vec!["GET".to_string()],
            backend_url: backend_url.to_string(),
            method: None,
            description: None,
            operation_id: None,
            input_schema: None,
            output_schema: None,
            llm: None,
        };
        let mut contract = UacContractSpec::new("api", "demo");
        contract.endpoints = vec![
            endpoint("/health", "http://b/health"),
            endpoint(path, backend_url),
        ];
        contract
    }

    #[test]
    fn endpoint_templates_the_binders_can_serve_pass() {
        for path in [
            "/",
            "/customers",
            "/customers/",
            "/customers/{id}",
            "/customers/{id}/",
            "/customers/{id}/segment",
            "/{id}",
            "/a/{x}/c/{y}",
            "/v1.2/.well-known/...",
            "/a/{id}/b/{other}",
        ] {
            check_endpoint_templates(&contract_with(path, "http://b/customers/"))
                .unwrap_or_else(|e| panic!("{path}: {e}"));
        }
    }

    #[test]
    fn query_fragment_empty_or_dot_segment_and_repeated_parameter_are_rejected() {
        let backend = "http://b/customers/";
        for (path, backend_url, reason) in [
            ("/customers/{id}", "http://b/customers?v=1", "? or #"),
            ("/customers", "http://b/customers/?", "? or #"),
            ("/customers/{id}", "http://b/customers#top", "? or #"),
            ("/a//b", backend, "empty segment"),
            ("//", backend, "empty segment"),
            ("/a/{id}//", backend, "empty segment"),
            ("/a/../b", backend, "dot segment"),
            ("/a/./b", backend, "dot segment"),
            ("/a/{id}/..", backend, "dot segment"),
            ("/.", backend, "dot segment"),
            ("/a/{id}/b/{id}", backend, "{id} is used twice"),
            ("/{id}/{id}", backend, "{id} is used twice"),
        ] {
            let error = check_endpoint_templates(&contract_with(path, backend_url))
                .expect_err(&format!("{path} {backend_url}"));
            assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
            assert!(
                error.contains(&format!("endpoints[1] ({path:?})")),
                "{error}"
            );
            assert!(error.contains(reason), "{reason}: {error}");
        }
    }

    #[test]
    fn endpoint_templates_the_binders_cannot_serve_are_rejected() {
        let backend = "http://b/customers/";
        for (path, backend_url, reason) in [
            ("/customers/{id}", "http://b/customers/{id}", "backend_url"),
            ("/customers/{id}", "http://b/customers/}", "backend_url"),
            ("customers/{id}", backend, "must start with /"),
            ("", backend, "must start with /"),
            ("/customers/{id", backend, "unbalanced"),
            ("/customers/id}", backend, "unbalanced"),
            ("/a/{b/c}", backend, "unbalanced"),
            ("/a/{{b}}", backend, "unbalanced"),
            ("/a/{}", backend, "empty parameter"),
            ("/a{id}", backend, "whole segment"),
            ("/files/f-{id}", backend, "whole segment"),
            ("/files/{name}.json", backend, "whole segment"),
            ("/a/{b}{c}", backend, "whole segment"),
        ] {
            let error = check_endpoint_templates(&contract_with(path, backend_url))
                .expect_err(&format!("{path} {backend_url}"));
            assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
            assert!(
                error.contains(&format!("endpoints[1] ({path:?})")),
                "{error}"
            );
            assert!(error.contains(reason), "{reason}: {error}");
        }
    }

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
    }

    #[test]
    fn path_template_without_parameter_is_all_static() {
        assert_eq!(split_path_template("/customers"), ("/customers", ""));
        assert_eq!(split_path_template("/customers/"), ("/customers/", ""));
        assert_eq!(split_path_template("/"), ("/", ""));
    }
}
