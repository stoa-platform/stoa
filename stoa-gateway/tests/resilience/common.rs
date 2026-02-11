//! Shared helpers for resilience tests — reuses TestApp from integration tests.

#[allow(dead_code)]
#[path = "../integration/common.rs"]
mod integration_common;

pub use integration_common::TestApp;
