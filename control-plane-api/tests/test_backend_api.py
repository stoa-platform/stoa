"""Tests for backend API and scoped API key endpoints (CAB-1188/CAB-1249)."""

import hashlib
from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.auth.dependencies import User
from src.models.backend_api import BackendApi, BackendApiAuthType, BackendApiStatus
from src.models.saas_api_key import SaasApiKey, SaasApiKeyStatus

# ============== Fixtures ==============

TENANT_ID = "test-tenant"
USER_ADMIN = User(id="admin-1", email="admin@test.com", username="admin", roles=["cpi-admin"], tenant_id=TENANT_ID)
USER_TENANT_ADMIN = User(id="ta-1", email="ta@test.com", username="tadmin", roles=["tenant-admin"], tenant_id=TENANT_ID)
USER_VIEWER = User(id="viewer-1", email="v@test.com", username="viewer", roles=["viewer"], tenant_id=TENANT_ID)
USER_OTHER_TENANT = User(
    id="other-1", email="o@test.com", username="other", roles=["tenant-admin"], tenant_id="other-tenant"
)


def _make_backend_api(
    name: str = "petstore",
    tenant_id: str = TENANT_ID,
    status: BackendApiStatus = BackendApiStatus.DRAFT,
    auth_type: BackendApiAuthType = BackendApiAuthType.NONE,
) -> BackendApi:
    api = BackendApi(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        display_name=f"{name} API",
        description=f"Test {name}",
        backend_url=f"https://{name}.example.com",
        auth_type=auth_type,
        auth_config_encrypted=None,
        status=status,
        tool_count=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test",
    )
    return api


def _make_saas_key(
    name: str = "test-key",
    tenant_id: str = TENANT_ID,
    allowed_ids: list[str] | None = None,
) -> SaasApiKey:
    return SaasApiKey(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        key_hash=hashlib.sha256(b"test").hexdigest(),
        key_prefix="stoa_saas_ab12",
        allowed_backend_api_ids=allowed_ids or [],
        status=SaasApiKeyStatus.ACTIVE,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test",
    )


# ============== Unit Tests: BackendApi Model ==============


class TestBackendApiModel:
    def test_model_repr(self):
        api = _make_backend_api()
        assert "BackendApi" in repr(api)
        assert "petstore" in repr(api)

    def test_auth_type_enum_values(self):
        assert BackendApiAuthType.NONE == "none"
        assert BackendApiAuthType.API_KEY == "api_key"
        assert BackendApiAuthType.BEARER == "bearer"
        assert BackendApiAuthType.BASIC == "basic"
        assert BackendApiAuthType.OAUTH2_CC == "oauth2_cc"

    def test_status_enum_values(self):
        assert BackendApiStatus.DRAFT == "draft"
        assert BackendApiStatus.ACTIVE == "active"
        assert BackendApiStatus.DISABLED == "disabled"


class TestSaasApiKeyModel:
    def test_model_repr(self):
        key = _make_saas_key()
        assert "SaasApiKey" in repr(key)
        assert "test-key" in repr(key)

    def test_status_enum_values(self):
        assert SaasApiKeyStatus.ACTIVE == "active"
        assert SaasApiKeyStatus.REVOKED == "revoked"
        assert SaasApiKeyStatus.EXPIRED == "expired"


# ============== Unit Tests: Encryption Service ==============


class TestEncryptionService:
    def test_encrypt_decrypt_roundtrip(self):
        from src.services.encryption_service import decrypt_auth_config, encrypt_auth_config

        original = {"header_name": "X-API-Key", "header_value": "secret123"}
        encrypted = encrypt_auth_config(original)
        assert encrypted != str(original)
        decrypted = decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_output(self):
        from src.services.encryption_service import encrypt_auth_config

        config = {"key": "value"}
        enc1 = encrypt_auth_config(config)
        enc2 = encrypt_auth_config(config)
        # Fernet uses random IV, so two encryptions of the same data differ
        assert enc1 != enc2

    def test_decrypt_invalid_token(self):
        from src.services.encryption_service import decrypt_auth_config

        with pytest.raises(ValueError, match="Cannot decrypt"):
            decrypt_auth_config("not-a-valid-fernet-token")


# ============== Unit Tests: Schemas ==============


class TestBackendApiSchemas:
    def test_create_schema_validation(self):
        from src.schemas.backend_api import BackendApiCreate

        schema = BackendApiCreate(
            name="test-api",
            backend_url="https://api.example.com",
            auth_type="api_key",
            auth_config={"header_name": "X-Key", "header_value": "secret"},
        )
        assert schema.name == "test-api"
        assert schema.auth_type == "api_key"

    def test_create_schema_min_fields(self):
        from src.schemas.backend_api import BackendApiCreate

        schema = BackendApiCreate(name="minimal", backend_url="https://example.com")
        assert schema.auth_type == "none"
        assert schema.auth_config is None

    def test_create_schema_name_min_length(self):
        from src.schemas.backend_api import BackendApiCreate

        with pytest.raises(ValidationError):
            BackendApiCreate(name="", backend_url="https://example.com")

    def test_key_create_schema(self):
        from src.schemas.backend_api import SaasApiKeyCreate

        uid = uuid4()
        schema = SaasApiKeyCreate(name="my-key", allowed_backend_api_ids=[uid], rate_limit_rpm=60)
        assert schema.name == "my-key"
        assert len(schema.allowed_backend_api_ids) == 1

    def test_key_create_requires_at_least_one_api(self):
        from src.schemas.backend_api import SaasApiKeyCreate

        with pytest.raises(ValidationError):
            SaasApiKeyCreate(name="empty-key", allowed_backend_api_ids=[])


# ============== Unit Tests: Key Generation ==============


class TestKeyGeneration:
    def test_generate_api_key_format(self):
        from src.routers.backend_apis import _generate_api_key

        plaintext, key_hash, prefix = _generate_api_key()
        assert plaintext.startswith("stoa_saas_")
        assert prefix.startswith("stoa_saas_")
        assert len(key_hash) == 64  # SHA-256 hex
        assert hashlib.sha256(plaintext.encode()).hexdigest() == key_hash

    def test_generate_api_key_uniqueness(self):
        from src.routers.backend_apis import _generate_api_key

        keys = {_generate_api_key()[0] for _ in range(10)}
        assert len(keys) == 10


# ============== Unit Tests: Response Mapping ==============


class TestResponseMapping:
    def test_to_response_hides_credentials(self):
        from src.routers.backend_apis import _to_response

        api = _make_backend_api()
        api.auth_config_encrypted = "encrypted-data"
        response = _to_response(api)
        assert response.has_credentials is True
        # Ensure no encrypted data leaks
        assert "encrypted" not in str(response.model_dump())

    def test_to_response_no_credentials(self):
        from src.routers.backend_apis import _to_response

        api = _make_backend_api()
        api.auth_config_encrypted = None
        response = _to_response(api)
        assert response.has_credentials is False


# ============== Unit Tests: Access Control ==============


class TestAccessControl:
    def test_tenant_access_admin(self):
        from src.routers.backend_apis import _has_tenant_access

        assert _has_tenant_access(USER_ADMIN, "any-tenant") is True

    def test_tenant_access_same_tenant(self):
        from src.routers.backend_apis import _has_tenant_access

        assert _has_tenant_access(USER_TENANT_ADMIN, TENANT_ID) is True

    def test_tenant_access_different_tenant(self):
        from src.routers.backend_apis import _has_tenant_access

        assert _has_tenant_access(USER_OTHER_TENANT, TENANT_ID) is False

    def test_write_access_viewer_denied(self):
        from fastapi import HTTPException

        from src.routers.backend_apis import _require_write_access

        with pytest.raises(HTTPException) as exc_info:
            _require_write_access(USER_VIEWER, TENANT_ID)
        assert exc_info.value.status_code == 403

    def test_write_access_tenant_admin_allowed(self):
        from src.routers.backend_apis import _require_write_access

        # Should not raise
        _require_write_access(USER_TENANT_ADMIN, TENANT_ID)

    def test_write_access_other_tenant_denied(self):
        from fastapi import HTTPException

        from src.routers.backend_apis import _require_write_access

        with pytest.raises(HTTPException) as exc_info:
            _require_write_access(USER_OTHER_TENANT, TENANT_ID)
        assert exc_info.value.status_code == 403
