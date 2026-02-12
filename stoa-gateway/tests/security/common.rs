//! Shared helpers for security tests — reuses TestApp from integration tests.

#[allow(dead_code)]
#[path = "../integration/common.rs"]
mod integration_common;

#[allow(unused_imports)]
pub use integration_common::{config_with_admin_token, TestApp};
