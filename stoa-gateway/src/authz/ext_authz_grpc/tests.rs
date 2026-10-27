use super::*;
use crate::auth::oidc::{OidcProvider, OidcProviderConfig};
use envoy::service::auth::v3::{attribute_context, AttributeContext};
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use serde_json::{json, Value};

// Public, repository-owned test signing material; never production credentials.
include!("../../../tests/fixtures/signing.rs");

async fn fixture() -> (ExtAuthzService, wiremock::MockServer, String) {
    use wiremock::{matchers::path, Mock, MockServer, ResponseTemplate};
    let server = MockServer::start().await;
    let issuer = server.uri();
    Mock::given(path("/.well-known/openid-configuration"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "issuer": issuer, "authorization_endpoint": format!("{issuer}/auth"),
            "token_endpoint": format!("{issuer}/token"), "jwks_uri": format!("{issuer}/jwks")
        })))
        .mount(&server)
        .await;
    Mock::given(path("/jwks"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"keys":[{
            "kty":"RSA", "kid":"test-key", "use":"sig", "alg":"RS256", "n":TEST_N,"e":"AQAB"
        }]})))
        .mount(&server)
        .await;
    let jwt = Arc::new(JwtValidator::new(Arc::new(OidcProvider::new(
        OidcProviderConfig {
            issuer_url: issuer.clone(),
            audience: "provider-audience".into(),
            ..Default::default()
        },
    ))));
    let engine =
        DecisionEngine::new().with_required_scopes(vec!["stoa:invoke".into(), "read".into()]);
    (
        ExtAuthzService::new(
            jwt,
            Some("stoa-api".into()),
            vec!["stoa:invoke".into(), "read".into()],
            engine,
        ),
        server,
        issuer,
    )
}

fn claims(issuer: &str) -> Value {
    let now = chrono::Utc::now().timestamp();
    json!({"sub":"alice", "tenant_id":"acme", "scope":"stoa:invoke read", "iss":issuer,
        "aud":"stoa-api", "iat":now,"exp":now+300})
}

fn request(claims: &Value) -> CheckRequest {
    let mut header = Header::new(Algorithm::RS256);
    header.kid = Some("test-key".into());
    let token = encode(
        &header,
        claims,
        &EncodingKey::from_rsa_pem(TEST_PEM.as_bytes()).unwrap(),
    )
    .unwrap();
    CheckRequest {
        attributes: Some(AttributeContext {
            context_extensions: HashMap::from([
                ("tenant_id".into(), "acme".into()),
                ("api_id".into(), "orders".into()),
            ]),
            request: Some(attribute_context::Request {
                http: Some(attribute_context::HttpRequest {
                    method: "GET".into(),
                    path: "/orders?q=1".into(),
                    headers: HashMap::from([("authorization".into(), format!("Bearer {token}"))]),
                    ..Default::default()
                }),
                ..Default::default()
            }),
            ..Default::default()
        }),
    }
}
fn http_mut(r: &mut CheckRequest) -> &mut attribute_context::HttpRequest {
    r.attributes
        .as_mut()
        .unwrap()
        .request
        .as_mut()
        .unwrap()
        .http
        .as_mut()
        .unwrap()
}
fn assert_denied(response: CheckResponse, status: i32) {
    assert_eq!(
        response.status.unwrap().code,
        if status == 401 { 16 } else { 7 }
    );
    let Some(HttpResponse::DeniedResponse(deny)) = response.http_response else {
        panic!("expected denial")
    };
    assert_eq!(deny.status.unwrap().code, status);
    assert!(deny.body.is_empty());
}

#[tokio::test]
async fn valid_token_overwrites_identity_headers() {
    let (service, _server, issuer) = fixture().await;
    let mut req = request(&claims(&issuer));
    for (k, v) in [
        ("X-Stoa-Tenant-Id", "acme"),
        ("x-stoa-api-id", "forged"),
        ("x-stoa-admin", "true"),
        ("x-ext-authz-user", "root"),
        ("x-user-id", "root"),
        ("x-user-roles", "cpi-admin"),
    ] {
        http_mut(&mut req).headers.insert(k.into(), v.into());
    }
    let response = service.check(Request::new(req)).await.unwrap().into_inner();
    assert_eq!(response.status.unwrap().code, 0);
    let Some(HttpResponse::OkResponse(ok)) = response.http_response else {
        panic!("expected allow")
    };
    let headers: HashMap<_, _> = ok
        .headers
        .iter()
        .map(|h| {
            assert_eq!(
                h.append_action,
                HeaderAppendAction::OverwriteIfExistsOrAdd as i32
            );
            let h = h.header.as_ref().unwrap();
            (h.key.as_str(), h.value.as_str())
        })
        .collect();
    assert_eq!(headers["x-user-id"], "alice");
    assert_eq!(headers["x-tenant-id"], "acme");
    assert_eq!(headers["x-stoa-tenant-id"], "acme");
    assert_eq!(headers["x-stoa-api-id"], "orders");
    for k in ["x-stoa-admin", "x-ext-authz-user", "x-user-roles"] {
        assert!(ok.headers_to_remove.contains(&k.to_string()));
    }
    assert!(!ok.headers_to_remove.contains(&"authorization".into()));
}

#[tokio::test]
async fn trust_and_tenant_failures_are_closed() {
    let (service, _server, issuer) = fixture().await;
    for (key, value, status) in [
        ("aud", json!("wrong"), 401),
        ("iss", json!("https://wrong.invalid"), 401),
        ("exp", json!(0), 401),
        ("scope", json!("stoa:invoke"), 403),
        ("tenant_id", Value::Null, 403),
        ("tenant_id", json!("other"), 403),
        ("sub", json!(""), 403),
    ] {
        let mut c = claims(&issuer);
        c[key] = value;
        assert_denied(service.authorize(request(&c)).await, status);
    }
    // Even cpi-admin has no cross-tenant or missing-tenant exception.
    let mut c = claims(&issuer);
    c["tenant_id"] = Value::Null;
    c["realm_access"] = json!({"roles":["cpi-admin"]});
    assert_denied(service.authorize(request(&c)).await, 403);
    for key in [
        "x-stoa-tenant",
        "x-stoa-tenant-id",
        "x-tenant-id",
        "x-tenant",
    ] {
        let mut req = request(&claims(&issuer));
        http_mut(&mut req)
            .headers
            .insert(key.into(), "other".into());
        assert_denied(service.authorize(req).await, 403);
    }
    for tenant in [None, Some(""), Some("other")] {
        let mut req = request(&claims(&issuer));
        let context = &mut req.attributes.as_mut().unwrap().context_extensions;
        context.remove("tenant_id");
        if let Some(t) = tenant {
            context.insert("tenant_id".into(), t.into());
        }
        assert_denied(service.authorize(req).await, 403);
    }
}

#[tokio::test]
async fn missing_audience_and_malformed_requests_never_allow() {
    let (mut service, _server, issuer) = fixture().await;
    let mut req = request(&claims(&issuer));
    http_mut(&mut req).headers.clear();
    assert_denied(service.authorize(req).await, 401);
    let mut req = request(&claims(&issuer));
    http_mut(&mut req).method.clear();
    assert_denied(service.authorize(req).await, 403);
    let mut req = request(&claims(&issuer));
    http_mut(&mut req)
        .headers
        .insert("Authorization".into(), "Bearer forged".into());
    assert_denied(service.authorize(req).await, 403);
    service.audience = None;
    assert_denied(service.authorize(request(&claims(&issuer))).await, 403);
    service.audience = Some(" ".into());
    assert_denied(service.authorize(request(&claims(&issuer))).await, 403);
}

#[tokio::test]
async fn scopes_only_come_from_validated_claims() {
    let (service, _server, issuer) = fixture().await;
    let mut c = claims(&issuer);
    c["scope"] = Value::Null;
    c["scp"] = json!(["stoa:invoke", "read"]);
    assert_eq!(service.authorize(request(&c)).await.status.unwrap().code, 0);
    c["scp"] = json!("stoa:invoke read");
    assert_eq!(service.authorize(request(&c)).await.status.unwrap().code, 0);
    c["scp"] = json!(["stoa:invoke"]);
    let mut req = request(&c);
    http_mut(&mut req)
        .headers
        .insert("x-user-scopes".into(), "stoa:invoke read".into());
    assert_denied(service.authorize(req).await, 403);
}

#[test]
fn conversion_never_turns_deny_or_bad_headers_into_allow() {
    assert_denied(response_from(Decision::deny("private reason")), 403);
    assert_denied(response_from(Decision::unauthorized("private reason")), 401);
    assert_denied(
        response_from(Decision::allow().with_header("x-user-id", "bad\r\nvalue")),
        403,
    );
    let mut decision = Decision::deny("override");
    decision.status_code = Some(451);
    assert_denied(response_from(decision), 451);
}

#[tokio::test]
async fn tonic_roundtrip_preserves_allow_and_business_denials() {
    use envoy::service::auth::v3::{
        authorization_client::AuthorizationClient, authorization_server::AuthorizationServer,
    };
    let (service, _oidc, issuer) = fixture().await;
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (stop, stopped) = tokio::sync::oneshot::channel();
    let server = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(AuthorizationServer::new(service))
            .serve_with_incoming_shutdown(
                tokio_stream::wrappers::TcpListenerStream::new(listener),
                async {
                    let _ = stopped.await;
                },
            )
            .await
            .unwrap();
    });
    let mut client = AuthorizationClient::connect(format!("http://{address}"))
        .await
        .unwrap();
    let response = client
        .check(request(&claims(&issuer)))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(response.status.unwrap().code, 0);
    let mut req = request(&claims(&issuer));
    http_mut(&mut req).headers.clear();
    assert_denied(client.check(req).await.unwrap().into_inner(), 401);
    let mut c = claims(&issuer);
    c["aud"] = json!("wrong");
    assert_denied(client.check(request(&c)).await.unwrap().into_inner(), 401);
    c["aud"] = json!("stoa-api");
    c["scope"] = json!("read");
    assert_denied(client.check(request(&c)).await.unwrap().into_inner(), 403);
    stop.send(()).unwrap();
    server.await.unwrap();
}

#[test]
fn production_requires_explicit_authorization_profile() {
    use crate::config::{Config, Environment};
    let mut config = Config {
        environment: Environment::Prod,
        mcp_audience: Some("stoa-mcp".into()),
        ext_authz_grpc_addr: Some("127.0.0.1:9191".parse().unwrap()),
        ..Default::default()
    };
    assert!(config.validate().is_err());
    config.ext_authz_audience = Some("stoa-api".into());
    assert!(config.validate().is_err());
    config.ext_authz_required_scopes = vec!["stoa:invoke".into()];
    assert!(config.validate().is_ok());
    config.ext_authz_audience = Some(" ".into());
    assert!(config.validate().is_err());
    config.environment = Environment::Dev;
    config.ext_authz_required_scopes.clear();
    assert!(config.validate().is_ok());
}
