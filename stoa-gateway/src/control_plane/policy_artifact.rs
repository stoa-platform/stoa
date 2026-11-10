//! Verification of signed tool-policy artifacts (compact JWS) issued by the
//! Control Plane.
//!
//! An artifact is accepted only when every rule below holds. Any refusal
//! leaves the caller's previous decision state untouched (ADR-070):
//! - the protected header is exactly `alg=EdDSA`, `typ=stoa-tool-policy+jws`
//!   and a `kid` in the `cp-policy-YYYYMM-N` format present in the pinned
//!   trust set; any other header parameter (`jku`, `jwk`, `x5c`, `crit`...)
//!   refuses the artifact;
//! - the Ed25519 signature verifies against that pinned key;
//! - `iss` and `aud` equal `STOA_POLICY_EXPECTED_ISSUER` and
//!   `STOA_POLICY_AUDIENCE` exactly (a string, never a list);
//! - `tenant_id` equals the requested tenant and `tenant_uuid` is a UUID.
//!
//! `expires_at` must be an RFC 3339 timestamp strictly in the future.
//! Cache age, version floors and tenant UUID pinning belong to the caller.

use super::policy_trust::PolicyTrustSet;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Utc};
use jsonwebtoken::Validation;
use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::{Map, Value};
use thiserror::Error;
use uuid::Uuid;

/// `typ` header emitted by the Control Plane signer.
pub const POLICY_ARTIFACT_TYP: &str = "stoa-tool-policy+jws";

/// `kid` format emitted by the Control Plane signer: `cp-policy-YYYYMM-N`.
static KID_FORMAT: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^cp-policy-[0-9]{4}(0[1-9]|1[0-2])-[1-9][0-9]*$").expect("kid regex")
});

/// Why an artifact was refused. Carries neither key material nor artifact content.
#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum PolicyArtifactError {
    #[error("artifact is not a compact JWS with a JSON object header")]
    Malformed,
    #[error("artifact header must contain exactly alg, typ and kid")]
    HeaderParams,
    #[error("artifact alg is not EdDSA")]
    Algorithm,
    #[error("artifact typ is not {POLICY_ARTIFACT_TYP}")]
    Type,
    #[error("artifact kid is not in the cp-policy-YYYYMM-N format")]
    KidFormat,
    #[error("artifact kid is not in the pinned trust set")]
    UnknownKid,
    #[error("artifact signature does not verify")]
    Signature,
    #[error("artifact iss does not match the expected issuer")]
    Issuer,
    #[error("artifact aud does not match the expected audience")]
    Audience,
    #[error("artifact tenant_id does not match the requested tenant")]
    Tenant,
    #[error("artifact tenant_uuid is missing or not a UUID")]
    TenantUuid,
    #[error("artifact expires_at is missing, invalid or no longer in the future")]
    Expiration,
}

/// Expected `iss` and `aud` of every artifact, taken from the configuration.
#[derive(Debug, Clone)]
pub struct PolicyArtifactVerifier {
    issuer: String,
    audience: String,
}

/// An artifact that passed every verification rule.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedPolicyArtifact {
    pub kid: String,
    pub tenant_id: String,
    pub tenant_uuid: Uuid,
    pub expires_at: DateTime<Utc>,
    /// Whole verified payload; the caller reads version, validity and entries.
    pub claims: Map<String, Value>,
}

impl PolicyArtifactVerifier {
    pub fn new(issuer: impl Into<String>, audience: impl Into<String>) -> Self {
        Self {
            issuer: issuer.into(),
            audience: audience.into(),
        }
    }

    /// Verify `jws` for `tenant_id` against the pinned `trust` set.
    pub fn verify(
        &self,
        trust: &PolicyTrustSet,
        tenant_id: &str,
        jws: &str,
    ) -> Result<VerifiedPolicyArtifact, PolicyArtifactError> {
        use PolicyArtifactError::*;

        let header = jws
            .split('.')
            .next()
            .filter(|_| jws.matches('.').count() == 2)
            .and_then(|segment| URL_SAFE_NO_PAD.decode(segment).ok())
            .and_then(|bytes| serde_json::from_slice::<Map<String, Value>>(&bytes).ok())
            .ok_or(Malformed)?;
        let param = |name: &str| header.get(name).and_then(Value::as_str);
        if header.len() != 3
            || ["alg", "typ", "kid"]
                .iter()
                .any(|k| !header.contains_key(*k))
        {
            return Err(HeaderParams);
        }
        if param("alg") != Some("EdDSA") {
            return Err(Algorithm);
        }
        if param("typ") != Some(POLICY_ARTIFACT_TYP) {
            return Err(Type);
        }
        let kid = param("kid")
            .filter(|kid| KID_FORMAT.is_match(kid))
            .ok_or(KidFormat)?;
        let key = trust.key(kid).ok_or(UnknownKid)?;

        // Expiry and audience are checked by this module, not by the library:
        // the artifact carries `expires_at`, not `exp`, and `aud` must be exact.
        let mut validation = Validation::new(jsonwebtoken::Algorithm::EdDSA);
        validation.validate_exp = false;
        validation.validate_aud = false;
        validation.required_spec_claims.clear();
        let claims = jsonwebtoken::decode::<Map<String, Value>>(jws, key, &validation)
            .map_err(|_| Signature)?
            .claims;

        let claim = |name: &str| claims.get(name).and_then(Value::as_str);
        if claim("iss") != Some(self.issuer.as_str()) {
            return Err(Issuer);
        }
        if claim("aud") != Some(self.audience.as_str()) {
            return Err(Audience);
        }
        if claim("tenant_id") != Some(tenant_id) {
            return Err(Tenant);
        }
        let tenant_uuid = claim("tenant_uuid")
            .and_then(|raw| Uuid::parse_str(raw).ok())
            .ok_or(TenantUuid)?;
        let expires_at = claim("expires_at")
            .and_then(|raw| DateTime::parse_from_rfc3339(raw).ok())
            .map(|at| at.with_timezone(&Utc))
            .filter(|at| *at > Utc::now())
            .ok_or(Expiration)?;
        Ok(VerifiedPolicyArtifact {
            kid: kid.to_owned(),
            tenant_id: tenant_id.to_owned(),
            tenant_uuid,
            expires_at,
            claims,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::PolicyArtifactError::*;
    use super::*;
    use jsonwebtoken::EncodingKey;
    use serde_json::json;

    /// RFC 8032 §7.1 test vector (PKCS#8 DER and public `x`, base64url).
    /// Published and deterministic: it is not a real signing key.
    const DER: &str = "MC4CAQAwBQYDK2VwBCIEIJ1hsZ3v_VpguoRK9JLsLMREScVpezJpGXA7rAMcrn9g";
    const X: &str = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
    const KID: &str = "cp-policy-202611-1";
    const TENANT_UUID: &str = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";

    fn trust() -> PolicyTrustSet {
        let key = json!({"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "kid": KID, "x": X});
        PolicyTrustSet::parse(json!({ "keys": [key] }).to_string().as_bytes()).unwrap()
    }

    fn header() -> Value {
        json!({"alg": "EdDSA", "typ": POLICY_ARTIFACT_TYP, "kid": KID})
    }

    fn claims() -> Value {
        json!({"iss": "stoa-control-plane", "aud": "stoa-gateway", "tenant_id": "acme",
               "tenant_uuid": TENANT_UUID, "version": 3, "permissions": [],
               "expires_at": (Utc::now() + chrono::Duration::minutes(15)).to_rfc3339()})
    }

    /// Sign raw segments exactly like the Control Plane signer does.
    fn sign(header: &Value, claims: &Value) -> String {
        let key = EncodingKey::from_ed_der(&URL_SAFE_NO_PAD.decode(DER).unwrap());
        let input = format!(
            "{}.{}",
            URL_SAFE_NO_PAD.encode(header.to_string()),
            URL_SAFE_NO_PAD.encode(claims.to_string())
        );
        let alg = jsonwebtoken::Algorithm::EdDSA;
        let signature = jsonwebtoken::crypto::sign(input.as_bytes(), &key, alg).unwrap();
        format!("{input}.{signature}")
    }

    fn verify(jws: &str) -> Result<VerifiedPolicyArtifact, PolicyArtifactError> {
        PolicyArtifactVerifier::new("stoa-control-plane", "stoa-gateway").verify(
            &trust(),
            "acme",
            jws,
        )
    }

    #[test]
    fn a_control_plane_artifact_for_the_requested_tenant_is_accepted() {
        let artifact = verify(&sign(&header(), &claims())).unwrap();
        assert_eq!(artifact.kid, KID);
        assert_eq!(artifact.tenant_id, "acme");
        assert_eq!(artifact.tenant_uuid.to_string(), TENANT_UUID);
        assert_eq!(artifact.claims["version"], json!(3));
    }

    #[test]
    fn each_claim_rule_refuses_the_artifact() {
        let cases = [
            ("iss", json!("other-issuer"), Issuer),
            ("aud", json!("other-gateway"), Audience),
            ("aud", json!(["stoa-gateway"]), Audience),
            ("tenant_id", json!("other-tenant"), Tenant),
            ("tenant_uuid", json!("not-a-uuid"), TenantUuid),
            ("tenant_uuid", Value::Null, TenantUuid),
        ];
        for (claim, value, expected) in cases {
            let mut claims = claims();
            match value {
                Value::Null => claims.as_object_mut().unwrap().remove(claim),
                value => claims.as_object_mut().unwrap().insert(claim.into(), value),
            };
            assert_eq!(verify(&sign(&header(), &claims)), Err(expected), "{claim}");
        }
    }

    #[test]
    fn expires_at_is_required_and_strictly_future() {
        for expiry in [
            Value::Null,
            json!("invalid"),
            json!("2099-01-01"),
            json!(42),
            json!(Utc::now().to_rfc3339()),
            json!((Utc::now() - chrono::Duration::seconds(1)).to_rfc3339()),
        ] {
            let mut payload = claims();
            payload["expires_at"] = expiry;
            assert_eq!(verify(&sign(&header(), &payload)), Err(Expiration));
        }
        let mut payload = claims();
        payload.as_object_mut().unwrap().remove("expires_at");
        assert_eq!(verify(&sign(&header(), &payload)), Err(Expiration));
    }

    #[test]
    fn each_header_rule_refuses_the_artifact() {
        let cases = [
            ("alg", json!("HS256"), Algorithm),
            ("typ", json!("JWT"), Type),
            ("kid", json!("k0"), KidFormat),
            ("kid", json!("cp-policy-202613-1"), KidFormat),
            ("kid", json!("cp-policy-202611-01"), KidFormat),
            ("kid", json!("cp-policy-202611-2"), UnknownKid),
            ("jku", json!("https://jwks.example/keys"), HeaderParams),
            ("crit", json!(["b64"]), HeaderParams),
        ];
        for (param, value, expected) in cases {
            let mut header = header();
            header[param] = value;
            assert_eq!(verify(&sign(&header, &claims())), Err(expected), "{param}");
        }
    }

    #[test]
    fn tampered_or_malformed_artifacts_are_refused() {
        let signed = sign(&header(), &claims());
        let mut forged = claims();
        forged["version"] = json!(4);
        let mut parts: Vec<&str> = signed.split('.').collect();
        let payload = URL_SAFE_NO_PAD.encode(forged.to_string());
        parts[1] = &payload;
        assert_eq!(verify(&parts.join(".")), Err(Signature));
        assert_eq!(
            verify(&signed[..signed.rfind('.').unwrap()]),
            Err(Malformed)
        );
        // "W10" is base64url for "[]": a JSON header that is not an object.
        assert_eq!(verify("W10.e30.c2ln"), Err(Malformed));
    }
}
