//! Sender-Constraint Configuration (CAB-1607).
//!
//! Unified sender-constraint configuration for mTLS + DPoP pipeline.
//!
//! When enabled, validates that tokens are bound to the sender via:
//! - mTLS: cnf.x5t#S256 matches client certificate thumbprint (RFC 8705)
//! - DPoP: cnf.jkt matches DPoP proof JWK thumbprint (RFC 9449)
//!
//! Per-tenant policy: tenants can require DPoP, mTLS, or both.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SenderConstraintConfig {
    /// Enable the unified sender-constraint middleware.
    /// Env: STOA_SENDER_CONSTRAINT_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require DPoP proof when cnf.jkt is present in the token.
    /// Env: STOA_SENDER_CONSTRAINT_DPOP_REQUIRED
    #[serde(default)]
    pub dpop_required: bool,

    /// Require mTLS binding when cnf.x5t#S256 is present in the token.
    /// Env: STOA_SENDER_CONSTRAINT_MTLS_REQUIRED
    #[serde(default)]
    pub mtls_required: bool,
}
