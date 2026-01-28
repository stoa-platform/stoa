// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! UAC (Unified Access Control) Module
//!
//! CAB-912: Policy enforcement with versioned caching and safe mode.
//!
//! This module provides:
//! - Classification definitions (H/VH/VVH)
//! - Versioned policy cache with Git validation
//! - Policy enforcement with audit trail
//! - Safe mode fallback for high availability

pub mod cache;
pub mod classifications;
pub mod enforcer;
pub mod safe_mode;

pub use cache::{CacheStats, PolicyDefinition, VersionedPolicyCache};
pub use classifications::{Classification, ClassificationConfig};
pub use enforcer::{EnforcementContext, EnforcementDecision, UacEnforcer};
pub use safe_mode::{SafeMode, SafeModeConfig, SafeModeTrigger};
