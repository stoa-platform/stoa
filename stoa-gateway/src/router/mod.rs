mod failover;
mod shadow;

// P0 failover router - kept for non-shadow mode deployments
pub use failover::{route_request, FailoverRouter};
pub use shadow::{shadow_route_request, ShadowRouter};
