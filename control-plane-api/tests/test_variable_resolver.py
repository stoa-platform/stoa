"""Tests for VariableResolver service (CAB-1291)"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.variable_resolver import VARIABLE_PATTERN, VAULT_PATTERN, VariableResolver


class TestPatterns:
    def test_variable_pattern_simple(self):
        m = VARIABLE_PATTERN.search("${FOO}")
        assert m is not None
        assert m.group(1) == "FOO"
        assert m.group(2) is None

    def test_variable_pattern_with_default(self):
        m = VARIABLE_PATTERN.search("${FOO:bar}")
        assert m.group(1) == "FOO"
        assert m.group(2) == "bar"

    def test_variable_pattern_underscore_digits(self):
        m = VARIABLE_PATTERN.search("${BACKEND_URL_2}")
        assert m.group(1) == "BACKEND_URL_2"

    def test_variable_pattern_no_match_lowercase(self):
        m = VARIABLE_PATTERN.search("${foo}")
        assert m is None

    def test_variable_pattern_multiple(self):
        matches = VARIABLE_PATTERN.findall("${A}/path/${B:default}")
        assert len(matches) == 2

    def test_vault_pattern_match(self):
        m = VAULT_PATTERN.match("vault:secret/data/dev/api#client_secret")
        assert m is not None
        assert m.group(1) == "secret/data/dev/api"
        assert m.group(2) == "client_secret"

    def test_vault_pattern_no_match(self):
        assert VAULT_PATTERN.match("not-a-vault-ref") is None
        assert VAULT_PATTERN.match("vault:path-without-key") is None


class TestResolveString:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_simple_substitution(self):
        result = self.resolver.resolve_string("${HOST}/api", {"HOST": "example.com"})
        assert result == "example.com/api"

    def test_multiple_vars(self):
        result = self.resolver.resolve_string(
            "${PROTO}://${HOST}:${PORT}",
            {"PROTO": "https", "HOST": "api.example.com", "PORT": "8443"},
        )
        assert result == "https://api.example.com:8443"

    def test_default_value_used(self):
        result = self.resolver.resolve_string("${HOST:localhost}", {})
        assert result == "localhost"

    def test_default_ignored_when_var_present(self):
        result = self.resolver.resolve_string("${HOST:localhost}", {"HOST": "prod.com"})
        assert result == "prod.com"

    def test_unresolved_kept(self):
        result = self.resolver.resolve_string("${MISSING}", {})
        assert result == "${MISSING}"

    def test_no_variables(self):
        result = self.resolver.resolve_string("plain string", {"FOO": "bar"})
        assert result == "plain string"

    def test_empty_string(self):
        result = self.resolver.resolve_string("", {"FOO": "bar"})
        assert result == ""

    def test_numeric_value(self):
        result = self.resolver.resolve_string("port=${PORT}", {"PORT": 8080})
        assert result == "port=8080"


class TestResolveDict:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_flat_dict(self):
        result = self.resolver.resolve_dict(
            {"url": "${HOST}/api", "port": "${PORT:3000}"},
            {"HOST": "example.com"},
        )
        assert result == {"url": "example.com/api", "port": "3000"}

    def test_nested_dict(self):
        template = {"backend": {"url": "${URL}", "timeout": 30}}
        result = self.resolver.resolve_dict(template, {"URL": "http://svc:8080"})
        assert result["backend"]["url"] == "http://svc:8080"
        assert result["backend"]["timeout"] == 30

    def test_list_in_dict(self):
        template = {"hosts": ["${HOST_1}", "${HOST_2}"]}
        result = self.resolver.resolve_dict(template, {"HOST_1": "a.com", "HOST_2": "b.com"})
        assert result["hosts"] == ["a.com", "b.com"]

    def test_list_with_dicts(self):
        template = {"routes": [{"path": "${PATH}"}]}
        result = self.resolver.resolve_dict(template, {"PATH": "/api"})
        assert result["routes"] == [{"path": "/api"}]

    def test_non_string_preserved(self):
        template = {"enabled": True, "count": 5, "ratio": 0.5}
        result = self.resolver.resolve_dict(template, {})
        assert result == {"enabled": True, "count": 5, "ratio": 0.5}

    def test_list_with_non_string_items(self):
        template = {"items": [1, 2, True]}
        result = self.resolver.resolve_dict(template, {})
        assert result["items"] == [1, 2, True]


class TestMergeConfigs:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_simple_merge(self):
        result = self.resolver.merge_configs({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_override(self):
        result = self.resolver.merge_configs({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_deep_merge(self):
        base = {"db": {"host": "localhost", "port": 5432}}
        override = {"db": {"host": "prod.db.com"}}
        result = self.resolver.merge_configs(base, override)
        assert result == {"db": {"host": "prod.db.com", "port": 5432}}

    def test_empty_configs_skipped(self):
        result = self.resolver.merge_configs({}, {"a": 1}, None, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_three_configs(self):
        result = self.resolver.merge_configs({"a": 1}, {"b": 2}, {"a": 3})
        assert result == {"a": 3, "b": 2}


class TestExtractVariables:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_single_var(self):
        assert self.resolver.extract_variables("${FOO}") == ["FOO"]

    def test_multiple_vars(self):
        result = self.resolver.extract_variables("${A}/path/${B}")
        assert result == ["A", "B"]

    def test_no_vars(self):
        assert self.resolver.extract_variables("plain") == []

    def test_var_with_default(self):
        assert self.resolver.extract_variables("${FOO:bar}") == ["FOO"]


class TestExtractAllVariables:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_from_string(self):
        assert self.resolver.extract_all_variables("${A}") == {"A"}

    def test_from_dict(self):
        result = self.resolver.extract_all_variables({"url": "${HOST}", "path": "${PATH}"})
        assert result == {"HOST", "PATH"}

    def test_from_nested(self):
        data = {"backend": {"url": "${URL}"}, "routes": ["${PATH}"]}
        result = self.resolver.extract_all_variables(data)
        assert result == {"URL", "PATH"}

    def test_from_list(self):
        result = self.resolver.extract_all_variables(["${A}", "${B}"])
        assert result == {"A", "B"}

    def test_non_string(self):
        assert self.resolver.extract_all_variables(42) == set()


class TestValidateConfig:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_all_provided(self):
        template = {"url": "${HOST}"}
        missing = self.resolver.validate_config(template, {"HOST": "example.com"})
        assert missing == []

    def test_missing_variable(self):
        template = {"url": "${HOST}", "key": "${API_KEY}"}
        missing = self.resolver.validate_config(template, {"HOST": "example.com"})
        assert "API_KEY" in missing

    def test_default_not_reported_missing(self):
        template = {"url": "${HOST:localhost}"}
        missing = self.resolver.validate_config(template, {})
        assert missing == []


class TestResolveVaultReference:
    @pytest.mark.asyncio
    async def test_no_vault_client(self):
        resolver = VariableResolver(vault_client=None)
        result = await resolver.resolve_vault_reference("vault:secret/path#key")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_reference(self):
        resolver = VariableResolver()
        result = await resolver.resolve_vault_reference("not-a-vault-ref")
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_resolution(self):
        vault = AsyncMock()
        vault.get_secret.return_value = {"client_secret": "s3cr3t"}
        resolver = VariableResolver(vault_client=vault)
        result = await resolver.resolve_vault_reference("vault:secret/data/dev#client_secret")
        assert result == "s3cr3t"
        vault.get_secret.assert_called_once_with("secret/data/dev")

    @pytest.mark.asyncio
    async def test_vault_key_not_found(self):
        vault = AsyncMock()
        vault.get_secret.return_value = {"other_key": "val"}
        resolver = VariableResolver(vault_client=vault)
        result = await resolver.resolve_vault_reference("vault:secret/data#missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_vault_secret_not_found(self):
        vault = AsyncMock()
        vault.get_secret.return_value = None
        resolver = VariableResolver(vault_client=vault)
        result = await resolver.resolve_vault_reference("vault:secret/missing#key")
        assert result is None

    @pytest.mark.asyncio
    async def test_vault_error_returns_none(self):
        vault = AsyncMock()
        vault.get_secret.side_effect = Exception("connection refused")
        resolver = VariableResolver(vault_client=vault)
        result = await resolver.resolve_vault_reference("vault:secret/path#key")
        assert result is None


class TestResolveApiConfig:
    @pytest.mark.asyncio
    async def test_simple_resolution(self):
        resolver = VariableResolver()
        template = {"backend": {"url": "${BACKEND_URL}"}}
        global_config = {"variables": {"BACKEND_URL": "http://api-dev.local"}}
        result = await resolver.resolve_api_config(template, "dev", global_config)
        assert result["backend"]["url"] == "http://api-dev.local"

    @pytest.mark.asyncio
    async def test_environment_variable_injected(self):
        resolver = VariableResolver()
        template = {"env": "${ENVIRONMENT}"}
        result = await resolver.resolve_api_config(template, "staging")
        assert result["env"] == "staging"

    @pytest.mark.asyncio
    async def test_api_env_overrides_global(self):
        resolver = VariableResolver()
        template = {"url": "${URL}"}
        global_config = {"variables": {"URL": "http://global"}}
        api_config = {"variables": {"URL": "http://api-specific"}}
        result = await resolver.resolve_api_config(template, "dev", global_config, api_config)
        assert result["url"] == "http://api-specific"

    @pytest.mark.asyncio
    async def test_vault_refs_resolved(self):
        vault = AsyncMock()
        vault.get_secret.return_value = {"token": "v-secret"}
        resolver = VariableResolver(vault_client=vault)
        template = {"secret": "vault:secret/data#token"}
        result = await resolver.resolve_api_config(template, "prod")
        assert result["secret"] == "v-secret"

    @pytest.mark.asyncio
    async def test_no_global_no_api_config(self):
        resolver = VariableResolver()
        template = {"env": "${ENVIRONMENT}", "static": "value"}
        result = await resolver.resolve_api_config(template, "dev")
        assert result["env"] == "dev"
        assert result["static"] == "value"

    @pytest.mark.asyncio
    async def test_global_without_variables_key(self):
        resolver = VariableResolver()
        template = {"url": "${URL}"}
        global_config = {"URL": "http://flat-config"}
        result = await resolver.resolve_api_config(template, "dev", global_config)
        assert result["url"] == "http://flat-config"

    @pytest.mark.asyncio
    async def test_vault_ref_in_list(self):
        vault = AsyncMock()
        vault.get_secret.return_value = {"key": "secret-val"}
        resolver = VariableResolver(vault_client=vault)
        template = {"secrets": ["vault:secret/path#key", "plain"]}
        result = await resolver.resolve_api_config(template, "dev")
        assert result["secrets"] == ["secret-val", "plain"]

    @pytest.mark.asyncio
    async def test_vault_ref_in_nested_dict_in_list(self):
        vault = AsyncMock()
        vault.get_secret.return_value = {"val": "resolved"}
        resolver = VariableResolver(vault_client=vault)
        template = {"items": [{"ref": "vault:path#val"}]}
        result = await resolver.resolve_api_config(template, "dev")
        assert result["items"] == [{"ref": "resolved"}]
