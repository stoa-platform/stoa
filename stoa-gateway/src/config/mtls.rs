//! mTLS configuration (CAB-864).
//!
//! All fields are configurable via STOA_MTLS_* environment variables.
//! Default: disabled (zero overhead when not enabled).

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MtlsConfig {
    /// Enable mTLS header extraction and validation
    /// Env: STOA_MTLS_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require certificate-token binding (cnf claim)
    /// Env: STOA_MTLS_REQUIRE_BINDING
    #[serde(default = "default_require_binding")]
    pub require_binding: bool,

    /// Trusted proxy CIDRs (F5 IPs). If empty, all sources accepted.
    /// Env: STOA_MTLS_TRUSTED_PROXIES (comma-separated CIDRs)
    #[serde(default)]
    pub trusted_proxies: Vec<String>,

    /// Allowed certificate issuers (DN strings). If empty, all issuers accepted.
    /// Env: STOA_MTLS_ALLOWED_ISSUERS (comma-separated DNs)
    #[serde(default)]
    pub allowed_issuers: Vec<String>,

    /// Routes that require mTLS (glob patterns). If empty, mTLS is optional on all routes.
    /// Env: STOA_MTLS_REQUIRED_ROUTES (comma-separated patterns)
    #[serde(default)]
    pub required_routes: Vec<String>,

    /// Extract tenant from certificate Subject DN (OU field)
    /// Env: STOA_MTLS_TENANT_FROM_DN
    #[serde(default = "default_tenant_from_dn")]
    pub tenant_from_dn: bool,

    // Header name overrides (for different TLS terminators)
    #[serde(default = "default_mtls_header_verify")]
    pub header_verify: String,

    #[serde(default = "default_mtls_header_fingerprint")]
    pub header_fingerprint: String,

    #[serde(default = "default_mtls_header_subject_dn")]
    pub header_subject_dn: String,

    #[serde(default = "default_mtls_header_issuer_dn")]
    pub header_issuer_dn: String,

    #[serde(default = "default_mtls_header_serial")]
    pub header_serial: String,

    #[serde(default = "default_mtls_header_not_before")]
    pub header_not_before: String,

    #[serde(default = "default_mtls_header_not_after")]
    pub header_not_after: String,

    #[serde(default = "default_mtls_header_cert")]
    pub header_cert: String,
}

impl Default for MtlsConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            require_binding: true,
            trusted_proxies: Vec::new(),
            allowed_issuers: Vec::new(),
            required_routes: Vec::new(),
            tenant_from_dn: true,
            header_verify: default_mtls_header_verify(),
            header_fingerprint: default_mtls_header_fingerprint(),
            header_subject_dn: default_mtls_header_subject_dn(),
            header_issuer_dn: default_mtls_header_issuer_dn(),
            header_serial: default_mtls_header_serial(),
            header_not_before: default_mtls_header_not_before(),
            header_not_after: default_mtls_header_not_after(),
            header_cert: default_mtls_header_cert(),
        }
    }
}

fn default_require_binding() -> bool {
    true
}

fn default_tenant_from_dn() -> bool {
    true
}

fn default_mtls_header_verify() -> String {
    "X-SSL-Client-Verify".to_string()
}

fn default_mtls_header_fingerprint() -> String {
    "X-SSL-Client-Fingerprint".to_string()
}

fn default_mtls_header_subject_dn() -> String {
    "X-SSL-Client-S-DN".to_string()
}

fn default_mtls_header_issuer_dn() -> String {
    "X-SSL-Client-I-DN".to_string()
}

fn default_mtls_header_serial() -> String {
    "X-SSL-Client-Serial".to_string()
}

fn default_mtls_header_not_before() -> String {
    "X-SSL-Client-NotBefore".to_string()
}

fn default_mtls_header_not_after() -> String {
    "X-SSL-Client-NotAfter".to_string()
}

fn default_mtls_header_cert() -> String {
    "X-SSL-Client-Cert".to_string()
}

#[cfg(test)]
mod tests {
    use super::MtlsConfig;

    #[test]
    fn test_default_mtls_disabled() {
        let mtls = MtlsConfig::default();
        assert!(!mtls.enabled);
        assert!(mtls.require_binding);
        assert!(mtls.trusted_proxies.is_empty());
        assert!(mtls.allowed_issuers.is_empty());
    }

    #[test]
    fn test_default_mtls_headers() {
        let mtls = MtlsConfig::default();
        assert_eq!(mtls.header_verify, "X-SSL-Client-Verify");
        assert_eq!(mtls.header_fingerprint, "X-SSL-Client-Fingerprint");
        assert_eq!(mtls.header_subject_dn, "X-SSL-Client-S-DN");
        assert_eq!(mtls.header_issuer_dn, "X-SSL-Client-I-DN");
        assert_eq!(mtls.header_serial, "X-SSL-Client-Serial");
        assert_eq!(mtls.header_not_before, "X-SSL-Client-NotBefore");
        assert_eq!(mtls.header_not_after, "X-SSL-Client-NotAfter");
        assert_eq!(mtls.header_cert, "X-SSL-Client-Cert");
    }
}
