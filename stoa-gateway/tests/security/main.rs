//! Security tests for STOA Gateway (OWASP API Top 10)
//!
//! Tests authentication bypass, tenant isolation, admin RBAC,
//! SSRF protection, security headers, and secret leakage.
//!
//! Run: `cargo test --test security`

mod admin;
mod auth;
mod common;
mod headers;
mod ssrf;
