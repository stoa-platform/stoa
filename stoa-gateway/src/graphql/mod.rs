//! GraphQL Protocol Support Module (CAB-1756)
//!
//! Provides GraphQL support for the STOA Gateway:
//! - GraphQL proxy: passthrough HTTP POST with application/json
//! - Schema introspection: parse introspection results to extract types/queries
//! - GraphQL→MCP bridge: expose queries/mutations as MCP tools

pub mod bridge;
pub mod introspection;
pub mod proxy;
