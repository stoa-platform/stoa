//! Shadow Mode Traffic Analysis
//!
//! This module provides additional utilities for the Shadow mode defined in
//! `mode/shadow.rs`. The main ShadowService handles traffic capture, analysis,
//! and UAC generation.
//!
//! # Modules
//!
//! - `capture`: Traffic capture utilities for various sources
//!
//! # Main Functionality
//!
//! The core shadow mode functionality is in `crate::mode::shadow::ShadowService`.
//! This module provides supplementary utilities:
//!
//! - HTTP request/response parsing from raw bytes
//! - Traffic capture from Envoy tap, port mirror, Kafka replay

#![allow(dead_code)]

pub mod capture;

// Re-export capture utilities

// Re-export types from mode::shadow for convenience
