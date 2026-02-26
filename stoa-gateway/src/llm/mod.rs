//! LLM Provider Router & Cost Tracking (CAB-1487)
//!
//! Multi-provider routing with strategy-based selection and per-provider
//! cost accumulation. Costs use micro-cents (1 cent = 10,000 micro-cents)
//! consistent with the existing metering subsystem.

pub mod config;
pub mod cost_tracker;
pub mod provider;
pub mod router;
