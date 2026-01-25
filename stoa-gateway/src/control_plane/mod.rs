//! Control Plane Module
//!
//! CAB-912: HTTP client for the FastAPI control plane.

pub mod client;

pub use client::{
    ApiRecord, ControlPlaneClient, ControlPlaneConfig, ControlPlaneError, CreateApiRequest,
    CreateApiResponse, UpdateStateRequest,
};
