//! Access requirement decision for routes that forward to a backend.
//!
//! Pure decision function, with no I/O. Rules:
//! - a token that was presented but rejected by validation is refused,
//!   even on a public backend;
//! - a presented token must carry the body claim `typ` equal to "Bearer"
//!   (case-insensitive), even on a public backend;
//! - a backend marked `public: true` is the only one served without identity;
//! - otherwise at least one exact `scope` value or realm role from the
//!   configured lists is required (`scp` and `resource_access` are ignored);
//! - empty lists on a non-public backend mean refusal.

use super::middleware::AuthenticatedUser;
use crate::config::ProxyBackendConfig;

/// Identity state as seen by the handler after the auth middleware.
#[derive(Debug, Clone, Copy)]
pub enum Identity<'a> {
    /// No token presented.
    Absent,
    /// A token was presented and validation rejected it.
    Rejected,
    /// A validated token.
    Present(&'a AuthenticatedUser),
}

/// What a backend (or route family) requires.
#[derive(Debug, Clone, Copy)]
pub struct AccessRequirement<'a> {
    pub public: bool,
    pub required_scopes: &'a [String],
    pub required_roles: &'a [String],
}

impl<'a> From<&'a ProxyBackendConfig> for AccessRequirement<'a> {
    fn from(c: &'a ProxyBackendConfig) -> Self {
        Self {
            public: c.public,
            required_scopes: &c.required_scopes,
            required_roles: &c.required_roles,
        }
    }
}

/// Reason for a refusal (all map to 403 in callers, except where noted there).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Denial {
    NoIdentity,
    RejectedToken,
    TokenType,
    NoRequirementDeclared,
    MissingRoleOrScope,
}

// --- `typ` claim policy (isolated: can be removed or changed on its own) ---

/// Per-provider policy for the body claim `typ`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TypClaimPolicy {
    /// Refuse a token without `typ`. Strict by default.
    pub require_present: bool,
}

impl Default for TypClaimPolicy {
    fn default() -> Self {
        Self {
            require_present: true,
        }
    }
}

impl TypClaimPolicy {
    fn accepts(&self, typ: Option<&str>) -> bool {
        match typ {
            Some(t) => t.eq_ignore_ascii_case("Bearer"),
            None => !self.require_present,
        }
    }
}

// --- end of `typ` claim policy ---

/// Decide whether the request may proceed. Pure and side-effect free.
pub fn authorize(
    identity: Identity<'_>,
    req: AccessRequirement<'_>,
    typ_policy: TypClaimPolicy,
) -> Result<(), Denial> {
    let user = match identity {
        Identity::Rejected => return Err(Denial::RejectedToken),
        Identity::Absent if req.public => return Ok(()),
        Identity::Absent => return Err(Denial::NoIdentity),
        Identity::Present(user) => user,
    };
    if !typ_policy.accepts(user.claims.typ.as_deref()) {
        return Err(Denial::TokenType);
    }
    if req.public {
        return Ok(());
    }
    if req.required_scopes.is_empty() && req.required_roles.is_empty() {
        return Err(Denial::NoRequirementDeclared);
    }
    let by_scope = req.required_scopes.iter().any(|s| user.claims.has_scope(s));
    let by_role = req
        .required_roles
        .iter()
        .any(|r| user.claims.has_realm_role(r));
    if by_scope || by_role {
        Ok(())
    } else {
        Err(Denial::MissingRoleOrScope)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::Claims;
    use serde_json::json;
    use Denial::*;

    const STRICT: TypClaimPolicy = TypClaimPolicy {
        require_present: true,
    };
    const LAX: TypClaimPolicy = TypClaimPolicy {
        require_present: false,
    };

    // Every token also carries scp=["proxy:read"] and a client role
    // "svc-reader": neither may widen access.
    fn user(typ: Option<&str>, scope: &str, roles: &[&str]) -> AuthenticatedUser {
        let mut v = json!({
            "sub": "user-1", "exp": 4_102_444_800i64, "iat": 0,
            "iss": "https://issuer.example", "aud": "stoa", "scope": scope,
            "realm_access": { "roles": roles }, "scp": ["proxy:read"],
            "resource_access": { "client-a": { "roles": ["svc-reader"] } }
        });
        if let Some(t) = typ {
            v["typ"] = json!(t);
        }
        let claims: Claims = serde_json::from_value(v).expect("claims");
        AuthenticatedUser {
            user_id: "user-1".into(),
            username: None,
            email: None,
            tenant_id: None,
            claims,
            raw_token: String::new(),
        }
    }

    fn backend(extra: serde_json::Value) -> ProxyBackendConfig {
        let mut v = json!({ "base_url": "http://upstream.invalid" });
        v.as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        serde_json::from_value(v).expect("backend")
    }

    fn check(id: Identity<'_>, b: &ProxyBackendConfig, p: TypClaimPolicy) -> Result<(), Denial> {
        authorize(id, b.into(), p)
    }

    #[test]
    fn regression_defaults_are_closed() {
        let b = backend(json!({}));
        assert!(!b.public && b.required_scopes.is_empty() && b.required_roles.is_empty());
        let u = user(Some("Bearer"), "proxy:read", &["proxy-user"]);
        assert_eq!(
            check(Identity::Present(&u), &b, STRICT),
            Err(NoRequirementDeclared)
        );
        assert_eq!(check(Identity::Absent, &b, STRICT), Err(NoIdentity));
        assert_eq!(TypClaimPolicy::default(), STRICT);
    }

    #[test]
    fn identity_states() {
        let public = backend(json!({ "public": true }));
        let guarded = backend(json!({ "required_scopes": ["proxy:read"] }));
        assert_eq!(check(Identity::Absent, &public, STRICT), Ok(()));
        assert_eq!(check(Identity::Absent, &guarded, STRICT), Err(NoIdentity));
        assert_eq!(
            check(Identity::Rejected, &public, STRICT),
            Err(RejectedToken)
        );
        assert_eq!(
            check(Identity::Rejected, &guarded, STRICT),
            Err(RejectedToken)
        );
        let id_token = user(Some("ID"), "", &[]);
        assert_eq!(
            check(Identity::Present(&id_token), &public, STRICT),
            Err(TokenType)
        );
    }

    #[test]
    fn regression_any_one_exact_scope_or_realm_role() {
        let b = backend(json!({
            "required_scopes": ["proxy:read", "proxy:admin"],
            "required_roles": ["proxy-user"]
        }));
        let cases: [(&str, &[&str], Result<(), Denial>); 6] = [
            ("openid proxy:admin", &[], Ok(())),
            ("openid", &["proxy-user"], Ok(())),
            ("openid other", &["other"], Err(MissingRoleOrScope)),
            ("Proxy:Read", &["Proxy-User"], Err(MissingRoleOrScope)),
            (
                "proxy:read:extra proxy",
                &["proxy-user-x"],
                Err(MissingRoleOrScope),
            ),
            ("", &["svc-reader"], Err(MissingRoleOrScope)),
        ];
        for (scope, roles, want) in cases {
            let u = user(Some("Bearer"), scope, roles);
            assert_eq!(
                check(Identity::Present(&u), &b, STRICT),
                want,
                "{scope} {roles:?}"
            );
        }
    }

    #[test]
    fn typ_claim_policy() {
        let b = backend(json!({ "required_scopes": ["proxy:read"] }));
        let cases: [(Option<&str>, TypClaimPolicy, Result<(), Denial>); 9] = [
            (Some("Bearer"), STRICT, Ok(())),
            (Some("bearer"), STRICT, Ok(())),
            (Some("BEARER"), STRICT, Ok(())),
            (Some("ID"), STRICT, Err(TokenType)),
            (Some("Refresh"), STRICT, Err(TokenType)),
            (Some(""), STRICT, Err(TokenType)),
            (None, STRICT, Err(TokenType)),
            (None, LAX, Ok(())),
            (Some("ID"), LAX, Err(TokenType)),
        ];
        for (typ, policy, want) in cases {
            let u = user(typ, "proxy:read", &[]);
            assert_eq!(check(Identity::Present(&u), &b, policy), want, "{typ:?}");
        }
    }
}
