//! Fail-closed Envoy authorization. Only verified JWT claims identify a caller;
//! context_extensions identify the route installed by the trusted xDS server.
use super::proto::{envoy, google};
use crate::auth::jwt::{JwtError, JwtValidator};
use crate::mode::decision::{Decision, DecisionEngine, DecisionInput, DecisionPrincipal};
use axum::http;
use envoy::config::core::v3::{
    header_value_option::HeaderAppendAction, HeaderValue, HeaderValueOption,
};
use envoy::service::auth::v3::{
    authorization_server::Authorization, check_response::HttpResponse, CheckRequest, CheckResponse,
    DeniedHttpResponse, OkHttpResponse,
};
use std::{collections::HashMap, sync::Arc, time::Duration};
use tonic::{Request, Response, Status};

pub struct ExtAuthzService {
    jwt: Arc<JwtValidator>,
    audience: Option<String>,
    scopes: Vec<String>,
    engine: DecisionEngine,
}

impl ExtAuthzService {
    pub fn new(
        jwt: Arc<JwtValidator>,
        audience: Option<String>,
        scopes: Vec<String>,
        engine: DecisionEngine,
    ) -> Self {
        Self {
            jwt,
            audience,
            scopes,
            engine,
        }
    }

    async fn authorize(&self, request: CheckRequest) -> CheckResponse {
        // Missing configuration never falls back to the provider/MCP audience.
        let Some(audience) = self.audience.as_deref().filter(|a| !a.trim().is_empty()) else {
            return denied(403);
        };
        let Some(attributes) = request.attributes else {
            return denied(403);
        };
        let Some(http) = attributes.request.and_then(|r| r.http) else {
            return denied(403);
        };
        if http::Method::from_bytes(http.method.as_bytes()).is_err()
            || !http.path.starts_with('/')
            || http.path.parse::<http::Uri>().is_err()
        {
            return denied(403);
        }
        // Normalize case, reject duplicates (including Authorization) and CRLF.
        // Raw header maps and the legacy map may not be mixed.
        let mut headers = HashMap::new();
        let mut insert = |name: &str, value: &str| -> Result<(), ()> {
            let key = name.to_ascii_lowercase();
            if key.len() > 256
                || value.len() > 16384
                || http::header::HeaderName::from_bytes(key.as_bytes()).is_err()
                    && !key.starts_with(':')
                || value.contains(['\r', '\n', '\0'])
                || headers.insert(key, value.to_string()).is_some()
            {
                return Err(());
            }
            Ok(())
        };
        if let Some(raw) = http.header_map {
            if !http.headers.is_empty() {
                return denied(403);
            }
            for header in raw.headers {
                let Ok(value) = std::str::from_utf8(&header.raw_value) else {
                    return denied(403);
                };
                if !header.value.is_empty() || insert(&header.key, value).is_err() {
                    return denied(403);
                }
            }
        } else {
            for (key, value) in &http.headers {
                if insert(key, value).is_err() {
                    return denied(403);
                }
            }
        }
        let Some(token) = headers
            .get("authorization")
            .and_then(|h| JwtValidator::extract_token(h).ok())
        else {
            return denied(401);
        };
        let claims = match tokio::time::timeout(
            Duration::from_millis(800),
            self.jwt.validate_with_audience(token, audience),
        )
        .await
        {
            Ok(Ok(claims)) => claims,
            // TenantRequired is emitted only after the existing validator's trust
            // checks (or strict claim decoding); it never supplies an identity.
            Ok(Err(JwtError::TenantRequired)) => return denied(403),
            _ => return denied(401),
        };
        let Some(tenant) = claims.tenant_id() else {
            return denied(403);
        };
        if claims.sub.trim().is_empty()
            || attributes
                .context_extensions
                .get("tenant_id")
                .map(String::as_str)
                != Some(tenant)
            || [
                "x-stoa-tenant",
                "x-stoa-tenant-id",
                "x-tenant-id",
                "x-tenant",
            ]
            .iter()
            .any(|key| headers.get(*key).is_some_and(|value| value != tenant))
        {
            return denied(403);
        }
        let scopes: Vec<String> = claims.scopes().into_iter().map(str::to_owned).collect();
        // DecisionEngine currently uses OR. SA-1 requires AND: enforce the
        // complete profile here before delegating policy/quota/enrichment.
        if self
            .scopes
            .iter()
            .any(|scope| scope.trim().is_empty() || !scopes.contains(scope))
        {
            return denied(403);
        }
        let mut remove: Vec<String> = headers
            .keys()
            .filter(|key| identity_header(key))
            .cloned()
            .collect();
        // Always overwrite optional identities too, even when the JWT has no roles/scopes.
        remove.extend(
            ["x-user-id", "x-user-roles", "x-user-scopes", "x-tenant-id"].map(str::to_owned),
        );
        headers.retain(|key, _| {
            !identity_header(key)
                && !matches!(
                    key.as_str(),
                    "authorization" | "cookie" | "proxy-authorization"
                )
        });
        let principal = DecisionPrincipal {
            id: claims.sub.clone(),
            email: claims.email.clone(),
            roles: claims
                .realm_roles()
                .into_iter()
                .map(str::to_owned)
                .collect(),
            scopes,
            claims: HashMap::new(),
        };
        let input = DecisionInput {
            method: http.method,
            path: http.path,
            headers,
            source_ip: attributes
                .source
                .and_then(|p| p.address)
                .and_then(|a| match a.address {
                    Some(envoy::config::core::v3::address::Address::SocketAddress(a)) => {
                        Some(a.address)
                    }
                    _ => None,
                }),
            tenant_id: Some(tenant.to_owned()),
            principal: Some(principal),
            context: serde_json::json!({"tenant_id": tenant, "api_id": attributes.context_extensions.get("api_id")}),
        };
        let mut decision = self.engine.decide(input);
        if decision.allowed {
            decision
                .headers_to_add
                .insert("x-stoa-tenant-id".into(), tenant.into());
            if let Some(api) = attributes.context_extensions.get("api_id") {
                decision
                    .headers_to_add
                    .insert("x-stoa-api-id".into(), api.clone());
            }
        }
        decision.headers_to_remove.extend(remove);
        response_from(decision)
    }
}

fn identity_header(key: &str) -> bool {
    key.starts_with("x-stoa-")
        || key.starts_with("x-ext-authz-")
        || key.starts_with("x-user-")
        || matches!(key, "x-tenant-id" | "x-tenant")
}

fn header(key: &str, value: &str) -> Option<HeaderValueOption> {
    let key = http::header::HeaderName::from_bytes(key.as_bytes()).ok()?;
    http::header::HeaderValue::from_str(value).ok()?;
    Some(HeaderValueOption {
        header: Some(HeaderValue {
            key: key.to_string(),
            value: value.to_owned(),
            ..Default::default()
        }),
        append_action: HeaderAppendAction::OverwriteIfExistsOrAdd as i32,
        ..Default::default()
    })
}

fn denied(status: u16) -> CheckResponse {
    CheckResponse {
        status: Some(google::rpc::Status {
            code: if status == 401 { 16 } else { 7 },
            ..Default::default()
        }),
        http_response: Some(HttpResponse::DeniedResponse(DeniedHttpResponse {
            status: Some(envoy::r#type::v3::HttpStatus {
                code: i32::from(status),
            }),
            headers: if status == 401 {
                header("www-authenticate", "Bearer realm=\"stoa\"")
                    .into_iter()
                    .collect()
            } else {
                vec![]
            },
            body: String::new(),
        })),
        ..Default::default()
    }
}

fn response_from(decision: Decision) -> CheckResponse {
    let Some(headers) = decision
        .headers_to_add
        .iter()
        .map(|(k, v)| header(k, v))
        .collect::<Option<Vec<_>>>()
    else {
        return denied(403);
    };
    // The only OK path is guarded by the engine's explicit allow.
    if decision.allowed {
        let added: Vec<_> = headers
            .iter()
            .filter_map(|h| h.header.as_ref().map(|h| h.key.as_str()))
            .collect();
        let mut remove: Vec<_> = decision
            .headers_to_remove
            .into_iter()
            .map(|k| k.to_ascii_lowercase())
            .filter(|k| !added.contains(&k.as_str()))
            .collect();
        remove.sort();
        remove.dedup();
        CheckResponse {
            status: Some(google::rpc::Status {
                code: 0,
                ..Default::default()
            }),
            http_response: Some(HttpResponse::OkResponse(OkHttpResponse {
                headers,
                headers_to_remove: remove,
                ..Default::default()
            })),
            ..Default::default()
        }
    } else {
        let mut response = denied(decision.status_code.unwrap_or(403));
        if let Some(HttpResponse::DeniedResponse(ref mut deny)) = response.http_response {
            deny.headers.extend(headers);
            if let Some(rate) = decision.metadata.and_then(|m| m.rate_limit) {
                let delay = rate
                    .reset_at
                    .saturating_sub(chrono::Utc::now().timestamp().max(0) as u64)
                    .max(1);
                deny.headers
                    .extend(header("retry-after", &delay.to_string()));
            }
        }
        response
    }
}

#[tonic::async_trait]
impl Authorization for ExtAuthzService {
    async fn check(
        &self,
        request: Request<CheckRequest>,
    ) -> Result<Response<CheckResponse>, Status> {
        Ok(Response::new(self.authorize(request.into_inner()).await))
    }
}

