//! Integration tests for STOA Gateway
//!
//! Tests multiple modules working together via the full Axum router.
//! Uses tower::ServiceExt::oneshot to test without starting a TCP server.

mod a2a_proxy_auth;
mod api_bridge;
mod auth;
mod common;
mod guardrails_metrics;
#[path = "../common/jwt.rs"]
mod jwt;
mod llm_proxy;
mod mcp;
mod mcp_policy_order;
mod quota;
mod sync_boundary;
mod tool_lifecycle;
