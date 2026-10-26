//! Administrative assurance, evaluated only after JWT verification.

use crate::auth::claims::Claims;
use crate::config::{Config, Environment};
use crate::state::AppState;
use crate::uac::Action;

pub fn enabled(config: &Config) -> bool {
    config
        .admin_require_strong_auth
        .unwrap_or(config.environment == Environment::Prod)
}

pub fn has_strong_auth(
    acr: Option<&str>,
    amr: Option<&[String]>,
    required_acr: &str,
    accepted_amr: &[String],
) -> bool {
    !required_acr.is_empty()
        && acr == Some(required_acr)
        && amr
            .map(|methods| methods.iter().any(|method| accepted_amr.contains(method)))
            .unwrap_or(true)
}

/// JWT scopes never confer administrative authority without the canonical role.
pub fn filter_admin_scope(roles: &[String], scopes: &mut Vec<String>) {
    if !roles.iter().any(|role| role == "cpi-admin") {
        scopes.retain(|scope| scope != "stoa:admin");
    }
}

pub fn validate_privileged_claims(config: &Config, claims: &Claims) -> Result<(), &'static str> {
    // Require the explicit signed tenant, never a header/default or role inference.
    let explicit_tenant = claims
        .tenant
        .as_deref()
        .filter(|tenant| !tenant.is_empty() && *tenant == tenant.trim());
    if !claims.has_realm_role("cpi-admin")
        || !claims.has_scope("stoa:admin")
        || explicit_tenant.is_none()
    {
        return Err("Administrative access requires cpi-admin, stoa:admin and an explicit tenant");
    }
    if enabled(config)
        && !has_strong_auth(
            claims.acr.as_deref(),
            claims.amr.as_deref(),
            &config.admin_required_acr,
            &config.admin_accepted_amr,
        )
    {
        return Err("insufficient_user_authentication");
    }
    Ok(())
}

/// Shared by REST and JSON-RPC (including batch/WebSocket dispatch).
/// This gate runs even when the OPA engine is disabled.
pub async fn require_admin_action(
    state: &AppState,
    action: Action,
    raw_token: Option<&str>,
) -> Result<(), &'static str> {
    if !matches!(
        action,
        Action::ManageTenants | Action::ManageUsers | Action::ManageContracts
    ) {
        return Ok(());
    }
    let validator = state
        .jwt_validator
        .as_ref()
        .ok_or("Administrative JWT validation unavailable")?;
    let token = raw_token.ok_or("Administrative JWT required")?;
    let claims = validator
        .validate_mcp(
            token,
            state.config.mcp_audience.as_deref().unwrap_or_default(),
        )
        .await
        .map_err(|_| "Invalid administrative JWT")?;
    validate_privileged_claims(&state.config, &claims)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn regression_privileged_acr_amr() {
        let methods = vec!["otp".to_string()];
        assert!(!has_strong_auth(None, None, "2", &methods));
        assert!(!has_strong_auth(Some("1"), None, "2", &methods));
        assert!(has_strong_auth(Some("2"), None, "2", &methods));
        assert!(!has_strong_auth(Some("2"), Some(&[]), "2", &methods));
        assert!(!has_strong_auth(
            Some("2"),
            Some(&["pwd".to_string()]),
            "2",
            &methods
        ));
        assert!(has_strong_auth(Some("2"), Some(&methods), "2", &methods));
    }

    #[test]
    fn regression_privileged_claims_require_all_authorities() {
        let config = Config {
            environment: Environment::Prod,
            ..Config::default()
        };
        let data = serde_json::json!({
            "sub": "synthetic-admin", "exp": 9999999999_i64, "iat": 1,
            "iss": "https://issuer.example/realms/test", "tenant_id": "alpha",
            "scope": "stoa:admin", "realm_access": {"roles": ["cpi-admin"]}, "acr": "2"
        });
        let claims: Claims = serde_json::from_value(data.clone()).unwrap();
        assert!(validate_privileged_claims(&config, &claims).is_ok());
        for key in ["acr", "scope", "realm_access", "tenant_id"] {
            let mut invalid = data.clone();
            invalid.as_object_mut().unwrap().remove(key);
            let claims: Claims = serde_json::from_value(invalid).unwrap();
            assert!(
                validate_privileged_claims(&config, &claims).is_err(),
                "missing {}",
                key
            );
        }
    }

    #[test]
    fn regression_privileged_production_default() {
        let mut config = Config {
            environment: Environment::Prod,
            ..Config::default()
        };
        assert!(enabled(&config));
        config.admin_require_strong_auth = Some(false);
        assert!(!enabled(&config));
        assert!(!enabled(&Config::default()));
    }

    #[test]
    fn regression_privileged_scope_filter() {
        for role in ["viewer", "admin", "cpi_admin"] {
            let mut scopes = vec!["stoa:admin".to_string(), "stoa:read".to_string()];
            filter_admin_scope(&[role.to_string()], &mut scopes);
            assert_eq!(scopes, vec!["stoa:read".to_string()]);
        }
        let mut scopes = vec!["stoa:admin".to_string()];
        filter_admin_scope(&["cpi-admin".to_string()], &mut scopes);
        assert_eq!(scopes, vec!["stoa:admin".to_string()]);
    }
}
