// Included inside jwt::tests. Reuse the signing fixture without duplicating its key.
pub(crate) fn test_signing_pem() -> &'static str {
    TEST_PEM
}

pub(crate) fn test_modulus() -> &'static str {
    TEST_N
}

pub(crate) fn mcp_test_jwks() -> serde_json::Value {
    serde_json::json!({"keys": [{
        "kty": "RSA", "kid": "test-key", "use": "sig", "alg": "RS256",
        "n": TEST_N, "e": "AQAB"
    }]})
}

pub(crate) fn mcp_test_mint(issuer: &str, overrides: serde_json::Value) -> String {
    let now = chrono::Utc::now().timestamp();
    let mut claims = serde_json::json!({
        "sub": "test-user", "exp": now + 300, "iat": now, "iss": issuer,
        "aud": "control-plane-api", "azp": "test-client", "tenant_id": "tenant-a",
        "scope": "stoa:read stoa:write"
    });
    for (key, value) in overrides.as_object().expect("claim overrides") {
        if value.is_null() {
            claims.as_object_mut().unwrap().remove(key);
        } else {
            claims[key] = value.clone();
        }
    }
    let mut header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
    header.kid = Some("test-key".into());
    jsonwebtoken::encode(
        &header,
        &claims,
        &jsonwebtoken::EncodingKey::from_rsa_pem(TEST_PEM.as_bytes()).unwrap(),
    )
    .unwrap()
}
