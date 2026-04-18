//! Contract tests for STOA Gateway API response shapes.
//!
//! Uses insta snapshots to lock down the exact JSON structure of every endpoint.
//! Dynamic fields (version, uptime) are redacted so snapshots remain stable.
//!
//! Run: `cargo test --test contract`
//! Review: `cargo insta review`

mod a2a;
mod common;
mod discovery;
mod errors;
mod health;
mod initialize_schema;
mod mcp_compliance;
mod mcp_public_methods;
mod oauth;
mod sse_accept;
mod tools;
