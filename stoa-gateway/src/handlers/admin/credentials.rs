//! Backend + consumer credentials admin endpoints.
//!
//! - Backend credentials (CAB-1250: BYOK): one credential per route, used
//!   when all consumers hit the same backend with the same secret.
//! - Consumer credentials (CAB-1432): per-consumer backend credential,
//!   used when different consumers authenticate separately on the backend.

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Deserialize;

use crate::proxy::consumer_credentials::ConsumerCredential;
use crate::proxy::credentials::{AuthType, BackendCredential};
use crate::proxy::dynamic::is_blocked_url;
use crate::state::AppState;

// -----------------------------------------------------------------------------
// Backend credentials CRUD (CAB-1250: BYOK)
// -----------------------------------------------------------------------------

/// POST /admin/backend-credentials — upsert a backend credential
pub async fn upsert_backend_credential(
    State(state): State<AppState>,
    Json(cred): Json<BackendCredential>,
) -> impl IntoResponse {
    // GW-1 P1-6 + P1-9: require identifier fields + parse OAuth2 URL so
    // the HTTPS check is case-insensitive and rejects CRLF-injection.
    let mut errors: Vec<String> = Vec::new();
    super::validation::require_non_empty("route_id", &cred.route_id, &mut errors);
    super::validation::require_non_empty("header_name", &cred.header_name, &mut errors);
    super::validation::require_non_empty("header_value", &cred.header_value, &mut errors);

    if cred.auth_type == AuthType::OAuth2ClientCredentials {
        match &cred.oauth2 {
            None => {
                errors.push(
                    "oauth2 config required for auth_type oauth2_client_credentials".to_string(),
                );
            }
            Some(oauth2) => {
                super::validation::require_https_url(
                    "oauth2.token_url",
                    &oauth2.token_url,
                    &mut errors,
                );
                if errors.iter().all(|e| !e.starts_with("oauth2.token_url"))
                    && is_blocked_url(&oauth2.token_url)
                {
                    errors.push("oauth2.token_url is blocked (SSRF protection)".to_string());
                }
            }
        }
    }

    if !errors.is_empty() {
        return super::validation::validation_error_response(errors);
    }

    let route_id = cred.route_id.clone();
    let existed = state.credential_store.upsert(cred).is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({"route_id": route_id, "status": "ok"})),
    )
        .into_response()
}

/// GET /admin/backend-credentials — list all backend credentials
pub async fn list_backend_credentials(
    State(state): State<AppState>,
) -> Json<Vec<BackendCredential>> {
    Json(state.credential_store.list())
}

/// DELETE /admin/backend-credentials/:route_id — remove a credential
pub async fn delete_backend_credential(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
) -> impl IntoResponse {
    match state.credential_store.remove(&route_id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "Credential not found").into_response(),
    }
}

// -----------------------------------------------------------------------------
// Consumer credentials CRUD (CAB-1432)
// -----------------------------------------------------------------------------

/// POST /admin/consumer-credentials — upsert a per-consumer backend credential.
///
/// Consumers authenticate via OAuth2 (JWT), but the backend API may require
/// its own credential (API key, Bearer token, Basic Auth). This endpoint
/// stores the mapping so the gateway can inject the correct header.
pub async fn upsert_consumer_credential(
    State(state): State<AppState>,
    Json(cred): Json<ConsumerCredential>,
) -> impl IntoResponse {
    // GW-1 P1-6: consumer credentials had zero validation — any empty
    // field collided at key `("", "")` in the store and injected an
    // empty header at proxy time.
    let mut errors: Vec<String> = Vec::new();
    super::validation::require_non_empty("route_id", &cred.route_id, &mut errors);
    super::validation::require_non_empty("consumer_id", &cred.consumer_id, &mut errors);
    super::validation::require_non_empty("header_name", &cred.header_name, &mut errors);
    super::validation::require_non_empty("header_value", &cred.header_value, &mut errors);
    if !errors.is_empty() {
        return super::validation::validation_error_response(errors);
    }

    let route_id = cred.route_id.clone();
    let consumer_id = cred.consumer_id.clone();
    let existed = state.consumer_credential_store.upsert(cred).is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({"route_id": route_id, "consumer_id": consumer_id, "status": "ok"})),
    )
        .into_response()
}

/// GET /admin/consumer-credentials — list all per-consumer credentials.
pub async fn list_consumer_credentials(
    State(state): State<AppState>,
) -> Json<Vec<ConsumerCredential>> {
    Json(state.consumer_credential_store.list())
}

/// Path parameters for consumer credential deletion.
#[derive(Deserialize)]
pub struct ConsumerCredentialPath {
    pub route_id: String,
    pub consumer_id: String,
}

/// DELETE /admin/consumer-credentials/:route_id/:consumer_id — remove a mapping.
pub async fn delete_consumer_credential(
    State(state): State<AppState>,
    Path(path): Path<ConsumerCredentialPath>,
) -> impl IntoResponse {
    match state
        .consumer_credential_store
        .remove(&path.route_id, &path.consumer_id)
    {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "Consumer credential not found").into_response(),
    }
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_json_req, auth_req, build_full_admin_router, create_test_state,
    };

    #[tokio::test]
    async fn test_upsert_and_list_backend_credentials() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let cred = serde_json::json!({
            "route_id": "r1",
            "auth_type": "bearer",
            "header_name": "Authorization",
            "header_value": "Bearer test-token"
        });

        let response = app
            .clone()
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);

        let response = app
            .oneshot(auth_req("GET", "/backend-credentials"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["route_id"], "r1");
    }

    #[tokio::test]
    async fn test_upsert_backend_credential_update() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let cred = serde_json::json!({
            "route_id": "r1", "auth_type": "bearer",
            "header_name": "Authorization", "header_value": "Bearer v1"
        });
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();

        let cred2 = serde_json::json!({
            "route_id": "r1", "auth_type": "api_key",
            "header_name": "X-API-Key", "header_value": "key-v2"
        });
        let response = app
            .oneshot(auth_json_req("POST", "/backend-credentials", cred2))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK); // update, not create
    }

    #[tokio::test]
    async fn test_delete_backend_credential() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let cred = serde_json::json!({
            "route_id": "r1", "auth_type": "bearer",
            "header_name": "Authorization", "header_value": "Bearer t"
        });
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();

        let response = app
            .clone()
            .oneshot(auth_req("DELETE", "/backend-credentials/r1"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NO_CONTENT);
    }

    #[tokio::test]
    async fn test_delete_backend_credential_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/backend-credentials/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    // ─── GW-1 P1-6 / P1-9 regression: credential validation ───────────

    async fn post_errors(
        app: axum::Router,
        path: &str,
        body: serde_json::Value,
    ) -> (StatusCode, Vec<String>) {
        let response = app
            .oneshot(auth_json_req("POST", path, body))
            .await
            .unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), 64 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        let errors = json["errors"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        (status, errors)
    }

    #[tokio::test]
    async fn test_backend_credential_rejects_empty_identifier_fields() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let cred = serde_json::json!({
            "route_id": "",
            "auth_type": "bearer",
            "header_name": "",
            "header_value": ""
        });
        let (status, errors) = post_errors(app, "/backend-credentials", cred).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        for field in ["route_id", "header_name", "header_value"] {
            assert!(
                errors.iter().any(|e| e.contains(field)),
                "missing error for {} in {:?}",
                field,
                errors
            );
        }
    }

    // GW-1 P1-9: uppercase `HTTPS://` was rejected by the old prefix
    // check but is a valid URL; `url::Url::parse` lowercases the scheme
    // so the credential now persists.
    #[tokio::test]
    async fn test_backend_credential_oauth2_accepts_uppercase_https_scheme() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let cred = serde_json::json!({
            "route_id": "r1",
            "auth_type": "oauth2_client_credentials",
            "header_name": "Authorization",
            "header_value": "",
            "oauth2": {
                "token_url": "HTTPS://oauth.example.com/token",
                "client_id": "cid",
                "client_secret": "sec"
            }
        });
        let response = app
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();
        // `header_value` is empty → still BAD_REQUEST, but we want to see
        // the URL validation does NOT complain about scheme case.
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), 64 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        let err_strs: Vec<String> = json["errors"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(
            !err_strs.iter().any(|e| e.starts_with("oauth2.token_url")),
            "uppercase HTTPS should parse cleanly, but got token_url errors: {:?}",
            err_strs
        );
    }

    // GW-1 P1-9: CRLF-injection in the token_url is rejected at parse
    // time, whereas the old `starts_with` check accepted the leading
    // `https://` prefix and let the rest through to reqwest.
    #[tokio::test]
    async fn test_backend_credential_oauth2_rejects_crlf_injection_in_token_url() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let cred = serde_json::json!({
            "route_id": "r1",
            "auth_type": "oauth2_client_credentials",
            "header_name": "Authorization",
            "header_value": "placeholder",
            "oauth2": {
                "token_url": "https://foo\r\nHost: evil",
                "client_id": "cid",
                "client_secret": "sec"
            }
        });
        let (status, errors) = post_errors(app, "/backend-credentials", cred).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(
            errors.iter().any(|e| e.contains("oauth2.token_url")),
            "expected CRLF to trip token_url validator, got {:?}",
            errors
        );
    }

    #[tokio::test]
    async fn test_backend_credential_oauth2_rejects_http_scheme() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let cred = serde_json::json!({
            "route_id": "r1",
            "auth_type": "oauth2_client_credentials",
            "header_name": "Authorization",
            "header_value": "placeholder",
            "oauth2": {
                "token_url": "http://plain.example.com/token",
                "client_id": "cid",
                "client_secret": "sec"
            }
        });
        let (status, errors) = post_errors(app, "/backend-credentials", cred).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(errors.iter().any(|e| e.contains("oauth2.token_url")));
    }

    #[tokio::test]
    async fn test_consumer_credential_rejects_empty_identifier_fields() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let cred = serde_json::json!({
            "route_id": "",
            "consumer_id": "",
            "auth_type": "bearer",
            "header_name": "",
            "header_value": ""
        });
        let (status, errors) = post_errors(app, "/consumer-credentials", cred).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        for field in ["route_id", "consumer_id", "header_name", "header_value"] {
            assert!(
                errors.iter().any(|e| e.contains(field)),
                "missing error for {} in {:?}",
                field,
                errors
            );
        }
    }
}
