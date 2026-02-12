//! Shared helpers for contract tests — reuses TestApp from integration tests.

#[allow(dead_code)]
#[path = "../integration/common.rs"]
mod integration_common;

pub use integration_common::{config_with_admin_token, TestApp};
