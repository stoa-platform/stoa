//! JWT Claims
//!
//! CAB-912 P2: JWT claims structure for Keycloak OIDC tokens.
//!
//! Expected claims:
//! - sub: Subject (user ID)
//! - preferred_username: User's display name
//! - email: User's email
//! - tenant_id: canonical tenant claim (legacy tenant requires explicit opt-in)
//! - realm_access.roles: Keycloak realm roles
//! - resource_access: Client-specific roles
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Providers emit `scp` as either a space-separated string or a scope array.
fn deserialize_scope_list<'de, D>(deserializer: D) -> Result<Option<Vec<String>>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Scopes {
        Text(String),
        List(Vec<String>),
    }
    Ok(
        Option::<Scopes>::deserialize(deserializer)?.map(|scopes| match scopes {
            Scopes::Text(value) => value.split_whitespace().map(str::to_owned).collect(),
            Scopes::List(values) => values,
        }),
    )
}

/// Reject ambiguous, empty, padded or non-string tenant claims at decoding.
fn deserialize_tenant<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = Option::<serde_json::Value>::deserialize(deserializer)?;
    let Some(value) = value else {
        return Ok(None);
    };
    let tenant = match value {
        serde_json::Value::String(s) => s,
        serde_json::Value::Array(mut items) if items.len() == 1 => match items.remove(0) {
            serde_json::Value::String(s) => s,
            _ => return Err(serde::de::Error::custom("invalid_tenant_claim")),
        },
        _ => return Err(serde::de::Error::custom("invalid_tenant_claim")),
    };
    if tenant.is_empty() || tenant != tenant.trim() {
        return Err(serde::de::Error::custom("invalid_tenant_claim"));
    }
    Ok(Some(tenant))
}

// =============================================================================
// JWT Claims
// =============================================================================

/// Standard JWT claims from Keycloak.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    /// Subject (user ID in Keycloak)
    pub sub: String,

    /// Token expiration time (Unix timestamp)
    pub exp: i64,

    /// Token issued at (Unix timestamp)
    pub iat: i64,

    /// Token issuer (Keycloak realm URL)
    pub iss: String,

    /// Audience (client IDs)
    #[serde(default)]
    pub aud: Audience,

    /// Issuer-assigned authentication assurance (validated by admin gates).
    #[serde(default)]
    pub acr: Option<String>,
    #[serde(default)]
    pub amr: Option<Vec<String>>,

    /// Authorized party (the client that requested the token)
    #[serde(default)]
    pub azp: Option<String>,

    /// Preferred username
    #[serde(default)]
    pub preferred_username: Option<String>,

    /// Email address
    #[serde(default)]
    pub email: Option<String>,

    /// Whether email is verified
    #[serde(default)]
    pub email_verified: Option<bool>,

    /// Full name
    #[serde(default)]
    pub name: Option<String>,

    /// Given name (first name)
    #[serde(default)]
    pub given_name: Option<String>,

    /// Family name (last name)
    #[serde(default)]
    pub family_name: Option<String>,

    /// Canonical tenant_id claim. Singleton arrays support Keycloak group mappers.
    #[serde(default, rename = "tenant_id", deserialize_with = "deserialize_tenant")]
    pub tenant: Option<String>,

    /// Migration-only legacy claim; normalized by JwtValidator after verification.
    #[serde(
        default,
        rename = "tenant",
        deserialize_with = "deserialize_tenant",
        skip_serializing
    )]
    pub legacy_tenant: Option<String>,

    /// Realm-level roles
    #[serde(default)]
    pub realm_access: Option<RealmAccess>,

    /// Client-specific roles
    #[serde(default)]
    pub resource_access: Option<HashMap<String, ResourceAccess>>,

    /// Session ID
    #[serde(default)]
    pub sid: Option<String>,

    /// Token type (typically "Bearer")
    #[serde(default)]
    pub typ: Option<String>,

    /// Scope
    #[serde(default)]
    pub scope: Option<String>,

    /// Validated OAuth scope array used by providers that emit `scp`.
    #[serde(
        default,
        deserialize_with = "deserialize_scope_list",
        skip_serializing_if = "Option::is_none"
    )]
    pub scp: Option<Vec<String>>,

    /// RFC 8705 Confirmation claim (certificate-bound tokens)
    /// Contains x5t#S256 (base64url-encoded SHA-256 thumbprint)
    #[serde(default)]
    pub cnf: Option<CnfClaim>,

    /// Federation: sub-account ID (set by Token Exchange protocol mapper)
    #[serde(default)]
    pub sub_account_id: Option<String>,

    /// Federation: master account ID (set by Token Exchange protocol mapper)
    #[serde(default)]
    pub master_account_id: Option<String>,

    // === HEGEMON Agent Claims (CAB-1710) ===
    /// HEGEMON worker name (e.g., "hegemon-worker-backend").
    /// Set by Keycloak protocol mapper on worker service accounts.
    #[serde(default)]
    pub worker_name: Option<String>,

    /// HEGEMON worker roles (e.g., ["backend", "hegemon:execute"]).
    /// Set by Keycloak protocol mapper on worker service accounts.
    #[serde(default)]
    pub worker_roles: Option<Vec<String>>,

    /// HEGEMON supervision tier override from JWT claim.
    /// Values: "autopilot", "copilot", "command".
    /// Can be overridden per-request via `X-Hegemon-Supervision` header.
    #[serde(default)]
    pub supervision_tier: Option<String>,
}

/// RFC 8705 / RFC 9449 Confirmation claim for sender-constrained tokens.
///
/// Supports two binding methods:
/// - `x5t#S256`: mTLS certificate thumbprint (RFC 8705)
/// - `jkt`: DPoP JWK thumbprint (RFC 9449 Section 6.1)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CnfClaim {
    /// Base64url-encoded SHA-256 certificate thumbprint (mTLS binding)
    #[serde(rename = "x5t#S256", default)]
    pub x5t_s256: Option<String>,

    /// JWK thumbprint for DPoP binding (RFC 9449)
    #[serde(default)]
    pub jkt: Option<String>,
}

/// Audience can be a single string or array of strings.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(untagged)]
pub enum Audience {
    #[default]
    None,
    Single(String),
    Multiple(Vec<String>),
}

impl Audience {
    /// Check if the audience contains a specific value.
    pub fn contains(&self, aud: &str) -> bool {
        match self {
            Audience::None => false,
            Audience::Single(s) => s == aud,
            Audience::Multiple(v) => v.iter().any(|a| a == aud),
        }
    }

    /// Get all audience values.
    pub fn values(&self) -> Vec<&str> {
        match self {
            Audience::None => vec![],
            Audience::Single(s) => vec![s.as_str()],
            Audience::Multiple(v) => v.iter().map(|s| s.as_str()).collect(),
        }
    }
}

/// Realm-level access roles.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RealmAccess {
    /// List of realm roles
    #[serde(default)]
    pub roles: Vec<String>,
}

/// Client-specific resource access.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ResourceAccess {
    /// List of client roles
    #[serde(default)]
    pub roles: Vec<String>,
}

impl Claims {
    /// Get the user ID (subject).
    pub fn user_id(&self) -> &str {
        &self.sub
    }

    /// Get the username.
    pub fn username(&self) -> Option<&str> {
        self.preferred_username.as_deref()
    }

    /// Canonical, validated identity only. Roles never identify a tenant.
    pub fn tenant_id(&self) -> Option<&str> {
        self.tenant
            .as_deref()
            .filter(|t| !t.is_empty() && *t == t.trim())
    }

    /// Resolve signed claims after signature/issuer verification, before use.
    pub fn validate_tenant(&mut self, allow_legacy: bool) -> Result<(), super::jwt::JwtError> {
        if let (Some(canonical), Some(legacy)) = (&self.tenant, &self.legacy_tenant) {
            if canonical != legacy {
                return Err(super::jwt::JwtError::DecodeError(
                    "conflicting_tenant_claims".into(),
                ));
            }
        }
        if self.tenant.is_none() && allow_legacy {
            self.tenant = self.legacy_tenant.clone();
        }
        if self.tenant_id().is_none() && !self.has_realm_role("cpi-admin") {
            return Err(super::jwt::JwtError::TenantRequired);
        }
        Ok(())
    }

    /// Get all realm roles.
    pub fn realm_roles(&self) -> Vec<&str> {
        self.realm_access
            .as_ref()
            .map(|r| r.roles.iter().map(|s| s.as_str()).collect())
            .unwrap_or_default()
    }

    /// Get roles for a specific client.
    pub fn client_roles(&self, client_id: &str) -> Vec<&str> {
        self.resource_access
            .as_ref()
            .and_then(|r| r.get(client_id))
            .map(|a| a.roles.iter().map(|s| s.as_str()).collect())
            .unwrap_or_default()
    }

    /// Check if the user has a specific realm role.
    pub fn has_realm_role(&self, role: &str) -> bool {
        self.realm_access
            .as_ref()
            .map(|r| r.roles.iter().any(|r| r == role))
            .unwrap_or(false)
    }

    /// Check if the user has a specific client role.
    pub fn has_client_role(&self, client_id: &str, role: &str) -> bool {
        self.resource_access
            .as_ref()
            .and_then(|r| r.get(client_id))
            .map(|a| a.roles.iter().any(|r| r == role))
            .unwrap_or(false)
    }

    /// Check if the token is expired.
    pub fn is_expired(&self) -> bool {
        let now = chrono::Utc::now().timestamp();
        self.exp < now
    }

    /// Get scopes as a vector.
    pub fn scopes(&self) -> Vec<&str> {
        self.scope
            .iter()
            .flat_map(|s| s.split_whitespace())
            .chain(self.scp.iter().flatten().map(String::as_str))
            .collect()
    }

    /// Check if the token has a specific scope.
    pub fn has_scope(&self, scope: &str) -> bool {
        self.scopes().contains(&scope)
    }
}

// =============================================================================
// STOA-Specific Role Mapping
// =============================================================================

/// STOA platform roles.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StoaRole {
    /// Platform administrator (full access)
    CpiAdmin,
    /// Tenant administrator
    TenantAdmin,
    /// DevOps role (deploy, promote)
    DevOps,
    /// Read-only viewer
    Viewer,
}

impl StoaRole {
    /// Parse a role string into a StoaRole.
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "cpi-admin" | "cpi_admin" | "admin" => Some(StoaRole::CpiAdmin),
            "tenant-admin" | "tenant_admin" => Some(StoaRole::TenantAdmin),
            "devops" | "dev-ops" => Some(StoaRole::DevOps),
            "viewer" | "read-only" | "readonly" => Some(StoaRole::Viewer),
            _ => None,
        }
    }

    /// Get the role name.
    pub fn as_str(&self) -> &'static str {
        match self {
            StoaRole::CpiAdmin => "cpi-admin",
            StoaRole::TenantAdmin => "tenant-admin",
            StoaRole::DevOps => "devops",
            StoaRole::Viewer => "viewer",
        }
    }

    /// Check if this role can write (create/update APIs).
    pub fn can_write(&self) -> bool {
        matches!(
            self,
            StoaRole::CpiAdmin | StoaRole::TenantAdmin | StoaRole::DevOps
        )
    }

    /// Check if this role is admin.
    pub fn is_admin(&self) -> bool {
        matches!(self, StoaRole::CpiAdmin | StoaRole::TenantAdmin)
    }
}

impl Claims {
    /// Get the highest STOA role from the claims.
    pub fn stoa_role(&self) -> Option<StoaRole> {
        let roles = self.realm_roles();

        // Check in priority order
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::CpiAdmin))
        {
            return Some(StoaRole::CpiAdmin);
        }
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::TenantAdmin))
        {
            return Some(StoaRole::TenantAdmin);
        }
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::DevOps))
        {
            return Some(StoaRole::DevOps);
        }
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::Viewer))
        {
            return Some(StoaRole::Viewer);
        }

        None
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_claims() -> Claims {
        Claims {
            acr: None,
            amr: None,
            sub: "user-123".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: Some("stoa-mcp".to_string()),
            preferred_username: Some("john.doe".to_string()),
            email: Some("john.doe@acme.com".to_string()),
            email_verified: Some(true),
            name: Some("John Doe".to_string()),
            given_name: Some("John".to_string()),
            family_name: Some("Doe".to_string()),
            legacy_tenant: None,
            tenant: Some("acme".to_string()),
            realm_access: Some(RealmAccess {
                roles: vec!["tenant-admin".to_string(), "offline_access".to_string()],
            }),
            resource_access: Some(HashMap::from([(
                "stoa-mcp".to_string(),
                ResourceAccess {
                    roles: vec!["api-creator".to_string()],
                },
            )])),
            sid: Some("session-456".to_string()),
            typ: Some("Bearer".to_string()),
            scope: Some("openid profile email stoa:write".to_string()),
            scp: None,
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
            worker_name: None,
            worker_roles: None,
            supervision_tier: None,
        }
    }

    #[test]
    fn test_claims_user_id() {
        let claims = sample_claims();
        assert_eq!(claims.user_id(), "user-123");
    }

    #[test]
    fn test_claims_tenant_from_claim() {
        let claims = sample_claims();
        assert_eq!(claims.tenant_id(), Some("acme"));
    }

    #[test]
    fn canonical_tenant_claim_is_accepted_and_conflicts_are_rejected() {
        let mut value = serde_json::to_value(sample_claims()).unwrap();
        value.as_object_mut().unwrap().remove("tenant");
        value["tenant_id"] = serde_json::json!("tenant-a");
        let claims: Claims = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(claims.tenant.as_deref(), Some("tenant-a"));
        value["tenant"] = serde_json::json!("tenant-b");
        assert!(serde_json::from_value::<Claims>(value)
            .unwrap()
            .validate_tenant(false)
            .is_err());
    }

    #[test]
    fn test_claims_does_not_derive_tenant_from_role() {
        let mut claims = sample_claims();
        claims.tenant = None;
        claims.realm_access = Some(RealmAccess {
            roles: vec!["tenant-demo".to_string()],
        });
        assert_eq!(claims.tenant_id(), None);
    }

    #[test]
    fn test_tenant_claim_wire_contract() {
        let base = serde_json::to_value(sample_claims()).unwrap();
        assert_eq!(base["tenant_id"], "acme");
        let mut legacy = base.clone();
        legacy.as_object_mut().unwrap().remove("tenant_id");
        legacy["tenant"] = serde_json::json!("acme");
        let mut claims: Claims = serde_json::from_value(legacy).unwrap();
        assert_eq!(claims.tenant_id(), None);
        claims.validate_tenant(true).unwrap();
        assert_eq!(claims.tenant_id(), Some("acme"));

        let mut duplicate = base.clone();
        duplicate["tenant"] = serde_json::json!("beta");
        assert!(serde_json::from_value::<Claims>(duplicate)
            .unwrap()
            .validate_tenant(false)
            .is_err());
        let mut array = base;
        array["tenant_id"] = serde_json::json!(["acme", "beta"]);
        assert!(serde_json::from_value::<Claims>(array).is_err());
    }

    #[test]
    fn test_empty_tenant_and_role_are_not_context() {
        let mut claims = sample_claims();
        for tenant in [None, Some("".to_string()), Some(" ".to_string())] {
            claims.tenant = tenant;
            assert_eq!(claims.tenant_id(), None);
        }
    }

    #[test]
    fn test_claims_realm_roles() {
        let claims = sample_claims();
        let roles = claims.realm_roles();
        assert!(roles.contains(&"tenant-admin"));
    }

    #[test]
    fn test_claims_client_roles() {
        let claims = sample_claims();
        let roles = claims.client_roles("stoa-mcp");
        assert!(roles.contains(&"api-creator"));
    }

    #[test]
    fn test_claims_has_realm_role() {
        let claims = sample_claims();
        assert!(claims.has_realm_role("tenant-admin"));
        assert!(!claims.has_realm_role("cpi-admin"));
    }

    #[test]
    fn test_claims_scopes() {
        let claims = sample_claims();
        assert!(claims.has_scope("openid"));
        assert!(claims.has_scope("stoa:write"));
        assert!(!claims.has_scope("stoa:admin"));
    }

    #[test]
    fn test_audience_single() {
        let aud = Audience::Single("stoa-mcp".to_string());
        assert!(aud.contains("stoa-mcp"));
        assert!(!aud.contains("other"));
    }

    #[test]
    fn test_audience_multiple() {
        let aud = Audience::Multiple(vec!["stoa-mcp".to_string(), "stoa-api".to_string()]);
        assert!(aud.contains("stoa-mcp"));
        assert!(aud.contains("stoa-api"));
        assert!(!aud.contains("other"));
    }

    #[test]
    fn test_stoa_role_parsing() {
        assert_eq!(StoaRole::from_str("cpi-admin"), Some(StoaRole::CpiAdmin));
        assert_eq!(
            StoaRole::from_str("tenant-admin"),
            Some(StoaRole::TenantAdmin)
        );
        assert_eq!(StoaRole::from_str("devops"), Some(StoaRole::DevOps));
        assert_eq!(StoaRole::from_str("viewer"), Some(StoaRole::Viewer));
        assert_eq!(StoaRole::from_str("unknown"), None);
    }

    #[test]
    fn test_stoa_role_from_claims() {
        let claims = sample_claims();
        assert_eq!(claims.stoa_role(), Some(StoaRole::TenantAdmin));
    }

    #[test]
    fn test_cnf_claim_deserialization() {
        let json = r#"{
            "sub": "user-1",
            "exp": 9999999999,
            "iat": 1000000000,
            "iss": "https://auth.gostoa.dev/realms/stoa",
            "cnf": {
                "x5t#S256": "obsz1234567890abcdefghijklmnopqrstuvwxyz_-A"
            }
        }"#;
        let claims: Claims = serde_json::from_str(json).unwrap();
        assert!(claims.cnf.is_some());
        let cnf = claims.cnf.unwrap();
        assert_eq!(
            cnf.x5t_s256.as_deref(),
            Some("obsz1234567890abcdefghijklmnopqrstuvwxyz_-A")
        );
        assert!(cnf.jkt.is_none());
    }

    #[test]
    fn test_cnf_claim_jkt_deserialization() {
        let json = r#"{
            "sub": "user-1",
            "exp": 9999999999,
            "iat": 1000000000,
            "iss": "https://auth.gostoa.dev/realms/stoa",
            "cnf": {
                "jkt": "0ZcOCORZNYy-DWpqq30jZyJGHTN0d2HglBV3uiguA4I"
            }
        }"#;
        let claims: Claims = serde_json::from_str(json).unwrap();
        assert!(claims.cnf.is_some());
        let cnf = claims.cnf.unwrap();
        assert!(cnf.x5t_s256.is_none());
        assert_eq!(
            cnf.jkt.as_deref(),
            Some("0ZcOCORZNYy-DWpqq30jZyJGHTN0d2HglBV3uiguA4I")
        );
    }

    #[test]
    fn test_cnf_claim_both_fields() {
        let json = r#"{
            "sub": "user-1",
            "exp": 9999999999,
            "iat": 1000000000,
            "iss": "https://auth.gostoa.dev/realms/stoa",
            "cnf": {
                "x5t#S256": "cert-thumbprint-abc",
                "jkt": "dpop-thumbprint-xyz"
            }
        }"#;
        let claims: Claims = serde_json::from_str(json).unwrap();
        let cnf = claims.cnf.unwrap();
        assert_eq!(cnf.x5t_s256.as_deref(), Some("cert-thumbprint-abc"));
        assert_eq!(cnf.jkt.as_deref(), Some("dpop-thumbprint-xyz"));
    }

    #[test]
    fn test_cnf_claim_absent() {
        let json = r#"{
            "sub": "user-1",
            "exp": 9999999999,
            "iat": 1000000000,
            "iss": "https://auth.gostoa.dev/realms/stoa"
        }"#;
        let claims: Claims = serde_json::from_str(json).unwrap();
        assert!(claims.cnf.is_none());
    }

    #[test]
    fn test_stoa_role_permissions() {
        assert!(StoaRole::CpiAdmin.can_write());
        assert!(StoaRole::TenantAdmin.can_write());
        assert!(StoaRole::DevOps.can_write());
        assert!(!StoaRole::Viewer.can_write());
    }

    #[test]
    fn test_federation_claims_present() {
        let json = r#"{
            "sub": "user-1",
            "exp": 9999999999,
            "iat": 1000000000,
            "iss": "https://auth.gostoa.dev/realms/stoa",
            "sub_account_id": "sub-acct-123",
            "master_account_id": "master-456"
        }"#;
        let claims: Claims = serde_json::from_str(json).unwrap();
        assert_eq!(claims.sub_account_id.as_deref(), Some("sub-acct-123"));
        assert_eq!(claims.master_account_id.as_deref(), Some("master-456"));
    }

    #[test]
    fn test_federation_claims_absent() {
        let json = r#"{
            "sub": "user-1",
            "exp": 9999999999,
            "iat": 1000000000,
            "iss": "https://auth.gostoa.dev/realms/stoa"
        }"#;
        let claims: Claims = serde_json::from_str(json).unwrap();
        assert!(claims.sub_account_id.is_none());
        assert!(claims.master_account_id.is_none());
    }
    fn tenant_claims(extra: serde_json::Value) -> Claims {
        let mut payload = serde_json::json!({"sub":"user", "iss":"https://issuer.example.invalid", "iat":1, "exp":9999999999_i64});
        payload
            .as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        serde_json::from_value(payload).unwrap()
    }

    #[test]
    fn regression_tenant_canonical_and_singleton_array() {
        for value in [
            serde_json::json!("tenant-a"),
            serde_json::json!(["tenant-a"]),
        ] {
            let mut claims = tenant_claims(serde_json::json!({"tenant_id":value}));
            claims.validate_tenant(false).unwrap();
            assert_eq!(claims.tenant_id(), Some("tenant-a"));
            let wire = serde_json::to_value(&claims).unwrap();
            assert_eq!(wire["tenant_id"], "tenant-a");
            assert!(wire.get("tenant").is_none());
        }
    }

    #[test]
    fn regression_tenant_missing_never_uses_role() {
        for role in ["viewer", "tenant-admin", "tenant-other", "devops"] {
            let mut claims = tenant_claims(serde_json::json!({"realm_access":{"roles":[role]}}));
            assert!(matches!(
                claims.validate_tenant(false),
                Err(super::super::jwt::JwtError::TenantRequired)
            ));
            assert_eq!(claims.tenant_id(), None);
        }
    }

    #[test]
    fn regression_tenant_legacy_requires_explicit_opt_in() {
        let mut claims = tenant_claims(serde_json::json!({"tenant":"tenant-a"}));
        assert!(claims.validate_tenant(false).is_err());
        assert_eq!(claims.tenant_id(), None);
        claims.validate_tenant(true).unwrap();
        assert_eq!(claims.tenant_id(), Some("tenant-a"));
    }

    #[test]
    fn regression_tenant_conflicts_are_invalid_even_during_migration() {
        for allow in [false, true] {
            let mut claims =
                tenant_claims(serde_json::json!({"tenant_id":"tenant-a", "tenant":"tenant-b"}));
            assert!(claims.validate_tenant(allow).is_err());
        }
    }

    #[test]
    fn regression_tenant_invalid_shapes_are_not_coerced() {
        for claim in ["tenant_id", "tenant"] {
            for value in [
                serde_json::json!(""),
                serde_json::json!(" "),
                serde_json::json!(" tenant-a"),
                serde_json::json!(42),
                serde_json::json!(true),
                serde_json::json!({}),
                serde_json::json!([]),
                serde_json::json!(["tenant-a", "tenant-b"]),
                serde_json::json!([null]),
            ] {
                let payload = serde_json::json!({"sub":"user", "iss":"issuer", "iat":1, "exp":9999999999_i64, (claim):value});
                assert!(serde_json::from_value::<Claims>(payload).is_err());
            }
        }
    }

    #[test]
    fn regression_tenant_only_platform_admin_can_be_unscoped() {
        let mut claims = tenant_claims(serde_json::json!({"realm_access":{"roles":["cpi-admin"]}}));
        claims.validate_tenant(false).unwrap();
        assert!(crate::auth::tenant::require_tenant(&claims).is_err());
        assert_eq!(claims.tenant_id(), None);
    }
}
