// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
mod failover;
mod shadow;

// P0 failover router - kept for non-shadow mode deployments
#[allow(unused_imports)]
pub use failover::{route_request, FailoverRouter};
pub use shadow::{shadow_route_request, ShadowRouter};
