// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
pub mod config;
pub mod engine;
pub mod rule;
pub mod violation;

pub use config::{PolicyConfig, PolicyDefinition};
pub use engine::{Policy, PolicyConfigError, PolicyEngine};
pub use rule::{Operator, Rule};
pub use violation::PolicyViolation;
