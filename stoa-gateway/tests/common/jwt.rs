//! Test-only JWTs signed at runtime with a generated RSA key.
//! No deployment credentials and no committed token strings.

use std::sync::OnceLock;

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use jsonwebtoken::{encode, EncodingKey, Header};
use rsa::pkcs8::{EncodePrivateKey, LineEnding};
use rsa::traits::PublicKeyParts;
use rsa::RsaPrivateKey;
use serde::Serialize;
use serde_json::json;
use stoa_gateway::config::Config;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

const ISSUER: &str = "https://issuer.test/realms/stoa";
const AUDIENCE: &str = "stoa-mcp-gateway";
const KEY_ID: &str = "auth-regression";

struct TestKey {
    pem: String,
    n: String,
    e: String,
}

fn generate_key() -> TestKey {
    let mut rng = rsa::rand_core::OsRng;
    let key = RsaPrivateKey::new(&mut rng, 2048).expect("generate test RSA key");
    let pem = key
        .to_pkcs8_pem(LineEnding::LF)
        .expect("encode test RSA key")
        .to_string();
    let n = URL_SAFE_NO_PAD.encode(key.n().to_bytes_be());
    let e = URL_SAFE_NO_PAD.encode(key.e().to_bytes_be());
    TestKey { pem, n, e }
}

/// Key published by the mock JWKS.
fn test_key() -> &'static TestKey {
    static KEY: OnceLock<TestKey> = OnceLock::new();
    KEY.get_or_init(generate_key)
}

/// Second key, never published, used under the same `kid`.
fn other_key() -> &'static TestKey {
    static KEY: OnceLock<TestKey> = OnceLock::new();
    KEY.get_or_init(generate_key)
}

#[derive(Serialize)]
struct FixtureClaims {
    sub: &'static str,
    tenant_id: &'static str,
    iss: &'static str,
    aud: &'static str,
    iat: i64,
    exp: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    cnf: Option<serde_json::Value>,
}

fn sign(exp: i64) -> String {
    sign_with(test_key(), exp)
}

fn sign_with(key: &TestKey, exp: i64) -> String {
    sign_with_cnf(key, exp, None)
}

fn sign_with_cnf(key: &TestKey, exp: i64, cnf: Option<serde_json::Value>) -> String {
    let mut header = Header::new(jsonwebtoken::Algorithm::RS256);
    header.kid = Some(KEY_ID.to_string());
    encode(
        &header,
        &FixtureClaims {
            sub: "auth-regression-user",
            tenant_id: "tenant-a",
            iss: ISSUER,
            aud: AUDIENCE,
            iat: 1,
            exp,
            cnf,
        },
        &EncodingKey::from_rsa_pem(key.pem.as_bytes()).expect("jwt encoding key"),
    )
    .expect("sign test JWT")
}

pub fn valid_token() -> &'static str {
    static TOKEN: OnceLock<String> = OnceLock::new();
    TOKEN.get_or_init(|| sign(4_102_444_800)).as_str()
}

pub fn expired_token() -> &'static str {
    static TOKEN: OnceLock<String> = OnceLock::new();
    TOKEN.get_or_init(|| sign(1)).as_str()
}

/// Same header and claims as [`valid_token`], signed with a key that the
/// mock JWKS does not publish. The signature is well-formed, so a rejection
/// comes from signature verification on every run.
pub fn bad_signature_token() -> &'static str {
    static TOKEN: OnceLock<String> = OnceLock::new();
    TOKEN
        .get_or_init(|| sign_with(other_key(), 4_102_444_800))
        .as_str()
}

pub async fn oidc_server() -> MockServer {
    let server = MockServer::start().await;
    let key = test_key();
    Mock::given(method("GET"))
        .and(path("/realms/stoa/.well-known/openid-configuration"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "issuer": ISSUER,
            "authorization_endpoint": "https://issuer.test/authorize",
            "token_endpoint": "https://issuer.test/token",
            "jwks_uri": "https://issuer.test/jwks"
        })))
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/jwks"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "keys": [{
                "kty": "RSA",
                "kid": KEY_ID,
                "alg": "RS256",
                "use": "sig",
                "e": key.e,
                "n": key.n
            }]
        })))
        .mount(&server)
        .await;
    server
}

pub fn config(server: &MockServer) -> Config {
    Config {
        a2a_enabled: true,
        auto_register: false,
        keycloak_url: Some("https://issuer.test".to_string()),
        keycloak_internal_url: Some(server.uri()),
        keycloak_realm: Some("stoa".to_string()),
        mcp_audience: Some(AUDIENCE.to_string()),
        ..Config::default()
    }
}

#[allow(dead_code)]
pub fn mtls_token() -> String {
    sign_with_cnf(
        test_key(),
        4_102_444_800,
        Some(json!({"x5t#S256": URL_SAFE_NO_PAD.encode([0x11; 32])})),
    )
}
