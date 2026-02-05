//! Route and policy registries for Control Plane managed APIs.
//!
//! In-memory registries — the Control Plane is the source of truth.
//! On gateway restart, the sync engine's drift detection re-syncs everything.

pub mod policy;
pub mod registry;

pub use policy::{PolicyEntry, PolicyRegistry};
pub use registry::{ApiRoute, RouteRegistry};
