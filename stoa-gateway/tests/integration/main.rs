//! Integration tests for STOA Gateway
//!
//! Tests multiple modules working together via the full Axum router.
//! Uses tower::ServiceExt::oneshot to test without starting a TCP server.

mod auth;
mod common;
mod mcp;
mod quota;
