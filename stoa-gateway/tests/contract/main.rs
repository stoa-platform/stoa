//! Contract tests for STOA Gateway API response shapes.
//!
//! Uses insta snapshots to lock down the exact JSON structure of every endpoint.
//! Dynamic fields (version, uptime) are redacted so snapshots remain stable.
//!
//! Run: `cargo test --test contract`
//! Review: `cargo insta review`

mod common;
mod discovery;
mod errors;
mod health;
mod mcp_compliance;
mod oauth;
mod tools;
