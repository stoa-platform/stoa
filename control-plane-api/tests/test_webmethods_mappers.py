"""Tests for webMethods mappers (CAB-1388)."""
import pytest

from src.adapters.webmethods.mappers import (
    _map_policy_config,
    map_alias_to_webmethods,
    map_application_to_webmethods,
    map_auth_server_to_webmethods,
    map_config_to_webmethods,
    map_policy_to_webmethods,
)


# ── map_policy_to_webmethods ──


class TestMapPolicyToWebmethods:
    def test_cors_policy_type_mapping(self):
        spec = {"name": "my-cors", "type": "cors", "config": {"allowedOrigins": ["https://example.com"]}}
        result = map_policy_to_webmethods(spec)
        action = result["policyAction"]
        assert action["type"] == "corsPolicy"
        assert action["policyActionName"] == "my-cors"

    def test_rate_limit_policy_type_mapping(self):
        spec = {"name": "rl", "type": "rate_limit", "config": {"maxRequests": 50, "intervalSeconds": 30}}
        result = map_policy_to_webmethods(spec)
        assert result["policyAction"]["type"] == "throttlingPolicy"

    def test_logging_policy_type_mapping(self):
        spec = {"name": "log", "type": "logging", "config": {}}
        result = map_policy_to_webmethods(spec)
        assert result["policyAction"]["type"] == "logInvocationPolicy"

    def test_jwt_policy_type_mapping(self):
        spec = {"name": "jwt", "type": "jwt", "config": {}}
        result = map_policy_to_webmethods(spec)
        assert result["policyAction"]["type"] == "jwtPolicy"

    def test_ip_filter_policy_type_mapping(self):
        spec = {"name": "ip", "type": "ip_filter", "config": {}}
        result = map_policy_to_webmethods(spec)
        assert result["policyAction"]["type"] == "ipFilterPolicy"

    def test_unknown_type_passes_through(self):
        spec = {"name": "custom", "type": "customPolicy", "config": {"key": "value"}}
        result = map_policy_to_webmethods(spec)
        assert result["policyAction"]["type"] == "customPolicy"

    def test_empty_spec_uses_defaults(self):
        result = map_policy_to_webmethods({})
        action = result["policyAction"]
        assert action["policyActionName"] == ""
        assert action["type"] == ""

    def test_result_has_policy_action_key(self):
        spec = {"name": "x", "type": "cors", "config": {}}
        result = map_policy_to_webmethods(spec)
        assert "policyAction" in result


# ── _map_policy_config ──


class TestMapPolicyConfig:
    def test_cors_policy_defaults(self):
        result = _map_policy_config("corsPolicy", {})
        assert result["allowedOrigins"] == ["*"]
        assert result["allowedMethods"] == ["GET"]
        assert result["allowedHeaders"] == []
        assert result["exposeHeaders"] == []
        assert result["maxAge"] == 3600
        assert result["allowCredentials"] is False

    def test_cors_policy_custom_values(self):
        config = {
            "allowedOrigins": ["https://a.com"],
            "allowedMethods": ["GET", "POST"],
            "allowedHeaders": ["Authorization"],
            "exposeHeaders": ["X-Rate-Limit"],
            "maxAge": 600,
            "allowCredentials": True,
        }
        result = _map_policy_config("corsPolicy", config)
        assert result["allowedOrigins"] == ["https://a.com"]
        assert result["allowedMethods"] == ["GET", "POST"]
        assert result["allowedHeaders"] == ["Authorization"]
        assert result["exposeHeaders"] == ["X-Rate-Limit"]
        assert result["maxAge"] == 600
        assert result["allowCredentials"] is True

    def test_throttling_policy_defaults(self):
        result = _map_policy_config("throttlingPolicy", {})
        assert result["maxRequestCount"] == 100
        assert result["intervalInSeconds"] == 60

    def test_throttling_policy_custom_values(self):
        config = {"maxRequests": 200, "intervalSeconds": 120}
        result = _map_policy_config("throttlingPolicy", config)
        assert result["maxRequestCount"] == 200
        assert result["intervalInSeconds"] == 120

    def test_log_invocation_policy_defaults(self):
        result = _map_policy_config("logInvocationPolicy", {})
        assert result["logRequestPayload"] is True
        assert result["logResponsePayload"] is True

    def test_log_invocation_policy_custom_values(self):
        config = {"logRequest": False, "logResponse": False}
        result = _map_policy_config("logInvocationPolicy", config)
        assert result["logRequestPayload"] is False
        assert result["logResponsePayload"] is False

    def test_unknown_type_returns_config_passthrough(self):
        config = {"custom": "value", "other": 42}
        result = _map_policy_config("jwtPolicy", config)
        assert result == config

    def test_empty_unknown_type_returns_empty(self):
        result = _map_policy_config("ipFilterPolicy", {})
        assert result == {}


# ── map_alias_to_webmethods ──


class TestMapAliasToWebmethods:
    def test_required_fields(self):
        spec = {"name": "my-alias", "endpointUri": "https://api.example.com"}
        result = map_alias_to_webmethods(spec)
        assert result["name"] == "my-alias"
        assert result["endPointURI"] == "https://api.example.com"

    def test_defaults_applied(self):
        spec = {"name": "alias", "endpointUri": "https://api.example.com"}
        result = map_alias_to_webmethods(spec)
        assert result["description"] == ""
        assert result["type"] == "endpoint"
        assert result["connectionTimeout"] == 30
        assert result["readTimeout"] == 60
        assert result["optimizationTechnique"] == "None"
        assert result["passSecurityHeaders"] is True

    def test_custom_values_override_defaults(self):
        spec = {
            "name": "alias",
            "description": "My alias",
            "type": "rest",
            "endpointUri": "https://api.example.com",
            "connectionTimeout": 10,
            "readTimeout": 20,
            "optimization": "mtom",
            "passSecurityHeaders": False,
        }
        result = map_alias_to_webmethods(spec)
        assert result["description"] == "My alias"
        assert result["type"] == "rest"
        assert result["connectionTimeout"] == 10
        assert result["readTimeout"] == 20
        assert result["optimizationTechnique"] == "mtom"
        assert result["passSecurityHeaders"] is False


# ── map_auth_server_to_webmethods ──


class TestMapAuthServerToWebmethods:
    def test_required_fields(self):
        spec = {
            "name": "keycloak",
            "discoveryURL": "https://auth.example.com/.well-known/openid-configuration",
            "clientId": "my-client",
        }
        result = map_auth_server_to_webmethods(spec)
        assert result["name"] == "keycloak"
        assert result["discoveryURL"] == "https://auth.example.com/.well-known/openid-configuration"
        assert result["clientId"] == "my-client"
        assert result["type"] == "authServerAlias"

    def test_defaults_applied(self):
        spec = {
            "name": "auth",
            "discoveryURL": "https://auth.example.com/.well-known/openid-configuration",
            "clientId": "cid",
        }
        result = map_auth_server_to_webmethods(spec)
        assert result["description"] == ""
        assert result["introspectionURL"] == ""
        assert result["clientSecret"] == ""
        assert result["scopes"] == ["openid"]

    def test_custom_values(self):
        spec = {
            "name": "auth",
            "description": "My auth",
            "discoveryURL": "https://auth.example.com/.well-known/openid-configuration",
            "introspectionURL": "https://auth.example.com/introspect",
            "clientId": "cid",
            "clientSecret": "secret",
            "scopes": ["openid", "profile"],
        }
        result = map_auth_server_to_webmethods(spec)
        assert result["description"] == "My auth"
        assert result["introspectionURL"] == "https://auth.example.com/introspect"
        assert result["clientSecret"] == "secret"
        assert result["scopes"] == ["openid", "profile"]


# ── map_application_to_webmethods ──


class TestMapApplicationToWebmethods:
    def test_required_fields(self):
        spec = {"name": "my-app"}
        result = map_application_to_webmethods(spec)
        assert result["name"] == "my-app"

    def test_defaults_applied(self):
        spec = {"name": "app"}
        result = map_application_to_webmethods(spec)
        assert result["description"] == ""
        assert result["contactEmails"] == []

    def test_custom_values(self):
        spec = {
            "name": "my-app",
            "description": "Test application",
            "contactEmails": ["admin@example.com"],
        }
        result = map_application_to_webmethods(spec)
        assert result["description"] == "Test application"
        assert result["contactEmails"] == ["admin@example.com"]


# ── map_config_to_webmethods ──


class TestMapConfigToWebmethods:
    def test_empty_config_returns_empty(self):
        result = map_config_to_webmethods({})
        assert result == {}

    def test_error_processing_included(self):
        spec = {"errorProcessing": {"mode": "strict"}}
        result = map_config_to_webmethods(spec)
        assert result["errorProcessing"] == {"mode": "strict"}

    def test_callback_settings_remapped(self):
        spec = {"callbackSettings": {"timeout": 30}}
        result = map_config_to_webmethods(spec)
        assert result["apiCallBackSettings"] == {"timeout": 30}
        assert "callbackSettings" not in result

    def test_keystore_included(self):
        spec = {"keystore": {"alias": "my-cert"}}
        result = map_config_to_webmethods(spec)
        assert result["keystore"] == {"alias": "my-cert"}

    def test_jwt_remapped(self):
        spec = {"jwt": {"issuer": "https://auth.example.com"}}
        result = map_config_to_webmethods(spec)
        assert result["jsonWebToken"] == {"issuer": "https://auth.example.com"}
        assert "jwt" not in result

    def test_all_sections_combined(self):
        spec = {
            "errorProcessing": {"mode": "lenient"},
            "callbackSettings": {"timeout": 60},
            "keystore": {"alias": "cert"},
            "jwt": {"issuer": "https://auth.example.com"},
        }
        result = map_config_to_webmethods(spec)
        assert "errorProcessing" in result
        assert "apiCallBackSettings" in result
        assert "keystore" in result
        assert "jsonWebToken" in result
        assert len(result) == 4

    def test_unknown_keys_not_included(self):
        spec = {"unknownSection": {"value": 1}}
        result = map_config_to_webmethods(spec)
        assert "unknownSection" not in result
        assert result == {}
