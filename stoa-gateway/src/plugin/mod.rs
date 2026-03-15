//! Plugin SDK — Extensibility Framework (CAB-1759)
//!
//! Allows third-party developers to write, compile, and load custom plugins
//! that intercept request/response at defined execution phases.
//!
//! # Architecture
//!
//! Inspired by Kong PDK phases and Envoy filter chains:
//!
//! ```text
//! Request → [pre_auth] → Auth → [post_auth] → [pre_upstream] → Backend
//!                                                                 ↓
//! Response ← [on_error] ←──────────────────── [post_upstream] ← Backend
//! ```
//!
//! # Usage
//!
//! ```rust,ignore
//! use stoa_gateway::plugin::{Plugin, PluginContext, PluginResult, Phase};
//!
//! struct MyPlugin;
//!
//! #[async_trait::async_trait]
//! impl Plugin for MyPlugin {
//!     fn metadata(&self) -> PluginMetadata {
//!         PluginMetadata {
//!             name: "my-plugin".into(),
//!             version: "1.0.0".into(),
//!             description: "My custom plugin".into(),
//!             phases: vec![Phase::PreUpstream],
//!         }
//!     }
//!
//!     async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
//!         ctx.set_request_header("X-My-Plugin", "active");
//!         PluginResult::Continue
//!     }
//! }
//! ```

pub mod builtin;
pub mod registry;
pub mod sdk;

pub use registry::PluginRegistry;
pub use sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};
