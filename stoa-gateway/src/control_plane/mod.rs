// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! Control Plane Module
//!
//! CAB-912: HTTP client for the FastAPI control plane.

pub mod client;

pub use client::{
    ApiRecord, ControlPlaneClient, ControlPlaneConfig, ControlPlaneError, CreateApiRequest,
    CreateApiResponse, UpdateStateRequest,
};
