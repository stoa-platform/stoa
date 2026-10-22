//! Test-only signed JWTs (expire in 2100) and local OIDC/JWKS fixtures.
//! Generated with a disposable RSA key; no deployment credentials are used.

use serde_json::json;
use stoa_gateway::config::Config;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

pub const VALID_TOKEN: &str = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImF1dGgtcmVncmVzc2lvbiJ9.eyJzdWIiOiJhdXRoLXJlZ3Jlc3Npb24tdXNlciIsImlzcyI6Imh0dHBzOi8vaXNzdWVyLnRlc3QvcmVhbG1zL3N0b2EiLCJhdWQiOiJzdG9hLW1jcC1nYXRld2F5IiwiaWF0IjoxLCJleHAiOjQxMDI0NDQ4MDB9.dr4oBeLrR60D76XYMu_rNrqW9F6KvAVaKOcVAly6OoRaFA4bVQV06oYlHTo9aJQnCAv1fKDOOLiPFU9J9PdLH6LY2gqVpu-rqb0EXBxmVJVm7QH9lnMua1hzyy9VtlEBNXrzjw6C3ijUTJHW8i9by5tmn9rDTnI9FXRlq1qXowxcECaI4nXkw2f87AW62s_tzAeCOgMAT3j14GLvR8tjJH8PY1ZE4eqUoXe-Hc3hwEuBrpE2HWHRH3Agc-ZVxk_f1oYJN8KjDnSxP39nUDwkoVBbuO90MMz-ru4Gw9itOK29m3BUA5Nm5dQCJv43Ne_auv5DzJp6RmO_JedbZ9l2Kg";
pub const EXPIRED_TOKEN: &str = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImF1dGgtcmVncmVzc2lvbiJ9.eyJzdWIiOiJhdXRoLXJlZ3Jlc3Npb24tdXNlciIsImlzcyI6Imh0dHBzOi8vaXNzdWVyLnRlc3QvcmVhbG1zL3N0b2EiLCJhdWQiOiJzdG9hLW1jcC1nYXRld2F5IiwiaWF0IjoxLCJleHAiOjF9.YbHE0va2P7zYm7MwQhMAqRpVZpnBA7x1GT_CE8RX6RKNm_lNbIFdG073NoleOZDCF3KhrfREM4Z1ktdTlYeaewYDT9QrDbDODbMLOWQ3Eox1f5coxLXaVdOfLJJj3sluckJny_KlQHt60-jNE9--jSWTP7oElhOJaVZyR2MwvooJ0i-gqa6ltV-dC7W2esuLz7K8rcS-YkZRVX7-syGT6g8igV8JJcSJRpr963A6UKNZsSsesoT27r_dJtB3zmCCXefhQETjPoracdQECStitA6zz0eJ7-p_t_EgBdZ7z-YkFFTwDXx916un0vS3SuwJEG6EpLeg7wIhYvyM3rQDNQ";
pub const BAD_SIGNATURE_TOKEN: &str = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImF1dGgtcmVncmVzc2lvbiJ9.eyJzdWIiOiJhdXRoLXJlZ3Jlc3Npb24tdXNlciIsImlzcyI6Imh0dHBzOi8vaXNzdWVyLnRlc3QvcmVhbG1zL3N0b2EiLCJhdWQiOiJzdG9hLW1jcC1nYXRld2F5IiwiaWF0IjoxLCJleHAiOjQxMDI0NDQ4MDB9.Ar4oBeLrR60D76XYMu_rNrqW9F6KvAVaKOcVAly6OoRaFA4bVQV06oYlHTo9aJQnCAv1fKDOOLiPFU9J9PdLH6LY2gqVpu-rqb0EXBxmVJVm7QH9lnMua1hzyy9VtlEBNXrzjw6C3ijUTJHW8i9by5tmn9rDTnI9FXRlq1qXowxcECaI4nXkw2f87AW62s_tzAeCOgMAT3j14GLvR8tjJH8PY1ZE4eqUoXe-Hc3hwEuBrpE2HWHRH3Agc-ZVxk_f1oYJN8KjDnSxP39nUDwkoVBbuO90MMz-ru4Gw9itOK29m3BUA5Nm5dQCJv43Ne_auv5DzJp6RmO_JedbZ9l2Kg";

pub async fn oidc_server() -> MockServer {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/realms/stoa/.well-known/openid-configuration"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "issuer": "https://issuer.test/realms/stoa",
            "authorization_endpoint": "https://issuer.test/authorize",
            "token_endpoint": "https://issuer.test/token",
            "jwks_uri": "https://issuer.test/jwks"
        })))
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/jwks"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "keys": [{"kty": "RSA", "kid": "auth-regression", "alg": "RS256",
                "use": "sig", "e": "AQAB",
                "n": "z6_z7s71fKYAaad8mHC7llWMOm2FASVIE8ubZzYk4KcGXIFTxQ74G3Ik4AorIN4LzC2VwyaXwCfe9B7X7h5sT8lEPybM-OvHdYiSO7Q7uPrfPaOYVjCrsYLK1FaVnVJYujzJ41UV2wEz0FBBRTzXSf1kK7yp1Z04XckPHPgECMmoJGFV61TNTu4wkYaNTBUycqga--Az4xMrtJM0uouKuR_p1yOqiUiODmtxs_dBdX4XJjRQtkQ5e3_mkZBWBzYaGiAu1QS11mdj19lQigZ2xOudW8kaMZ55f27657dnssq4zV55eX-czVsO6-G2bLupmShVeAsesOCAl6rPPXCeCw"}]
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
        ..Config::default()
    }
}
