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
        self.authorize_with_reason(request, &mut DenyReason::Request)
            .await
    }

    /// Same decision as `authorize`; `reason` only classifies a denial for the trace.
    async fn authorize_with_reason(
        &self,
        request: CheckRequest,
        reason: &mut DenyReason,
    ) -> CheckResponse {
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
            *reason = DenyReason::MissingToken;
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
            Ok(Err(JwtError::TenantRequired)) => {
                *reason = DenyReason::Tenant;
                return denied(403);
            }
            Ok(Err(error)) => {
                *reason = DenyReason::from_jwt(&error);
                return denied(401);
            }
            Err(_) => {
                *reason = DenyReason::Timeout;
                return denied(401);
            }
        };
        *reason = DenyReason::Tenant;
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
        let scopes: Vec<String> = claims
            .scopes_ext_authz()
            .into_iter()
            .map(str::to_owned)
            .collect();
        *reason = DenyReason::Scope;
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
        *reason = DenyReason::Policy;
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

// Correlation only: this value may be chosen by the client and never authorizes.
fn trace_uuid(value: &str) -> Option<uuid::Uuid> {
    if value.len() != 36 || [8, 13, 18, 23].iter().any(|&i| value.as_bytes()[i] != b'-') {
        return None;
    }
    let id = uuid::Uuid::parse_str(value).ok()?;
    (id.as_u128() != 0 && id.as_u128() != u128::MAX).then_some(id)
}

fn client_request_id(request: &CheckRequest) -> Option<uuid::Uuid> {
    request
        .attributes
        .as_ref()
        .and_then(|a| a.request.as_ref())
        .and_then(|r| r.http.as_ref())
        .and_then(|h| h.headers.get("x-request-id"))
        .and_then(|id| trace_uuid(id))
}

fn check_trace_ids(request: &CheckRequest) -> (Option<uuid::Uuid>, uuid::Uuid) {
    (client_request_id(request), uuid::Uuid::new_v4())
}

/// Closed denial classification for `ext_authz_decision`. It never carries a
/// token, a claim, the expected audience or a free-form error string.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum DenyReason {
    None,
    Request,
    MissingToken,
    Audience,
    Signature,
    Issuer,
    Expired,
    Timeout,
    Token,
    Tenant,
    Scope,
    Policy,
}

impl DenyReason {
    fn from_jwt(error: &JwtError) -> Self {
        match error {
            JwtError::InvalidAudience { .. } => Self::Audience,
            JwtError::InvalidSignature => Self::Signature,
            JwtError::InvalidIssuer { .. } => Self::Issuer,
            JwtError::Expired => Self::Expired,
            JwtError::TenantRequired => Self::Tenant,
            _ => Self::Token,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Request => "request",
            Self::MissingToken => "missing_token",
            Self::Audience => "audience",
            Self::Signature => "signature",
            Self::Issuer => "issuer",
            Self::Expired => "expired",
            Self::Timeout => "timeout",
            Self::Token => "token",
            Self::Tenant => "tenant",
            Self::Scope => "scope",
            Self::Policy => "policy",
        }
    }
}

fn final_deny_reason(rpc_code: i32, reason: DenyReason) -> DenyReason {
    if rpc_code == 0 {
        DenyReason::None
    } else {
        reason
    }
}

#[derive(Debug, PartialEq, Eq)]
struct DecisionTrace {
    client_request_id: Option<uuid::Uuid>,
    server_check_id: uuid::Uuid,
    decision_id: Option<uuid::Uuid>,
    rpc_code: i32,
}

fn decision_trace(
    client_request_id: Option<uuid::Uuid>,
    server_check_id: uuid::Uuid,
    response: &CheckResponse,
) -> DecisionTrace {
    let decision_id = response.http_response.as_ref().and_then(|r| match r {
        HttpResponse::OkResponse(ok) => ok
            .headers
            .iter()
            .filter_map(|h| h.header.as_ref())
            .find(|h| h.key.eq_ignore_ascii_case("x-request-id"))
            .and_then(|h| trace_uuid(&h.value)),
        _ => None,
    });
    DecisionTrace {
        client_request_id,
        server_check_id,
        decision_id,
        rpc_code: response.status.as_ref().map(|s| s.code).unwrap_or(7),
    }
}

#[tonic::async_trait]
impl Authorization for ExtAuthzService {
    async fn check(
        &self,
        request: Request<CheckRequest>,
    ) -> Result<Response<CheckResponse>, Status> {
        let request = request.into_inner();
        let (client_request_id, server_check_id) = check_trace_ids(&request);
        let started = std::time::Instant::now();
        let mut reason = DenyReason::Request;
        let response = self.authorize_with_reason(request, &mut reason).await;
        let trace = decision_trace(client_request_id, server_check_id, &response);
        let deny_reason = final_deny_reason(trace.rpc_code, reason);
        tracing::info!(event = "ext_authz_decision",
            client_request_id = %trace.client_request_id.map(|id| id.to_string()).unwrap_or_default(),
            client_request_id_trusted = false,
            server_check_id = %trace.server_check_id,
            decision_id = %trace.decision_id.map(|id| id.to_string()).unwrap_or_default(),
            rpc_code = trace.rpc_code,
            deny_reason = deny_reason.as_str(),
            duration_us = started.elapsed().as_micros() as u64);
        Ok(Response::new(response))
    }
}

#[cfg(test)]
mod tests;
