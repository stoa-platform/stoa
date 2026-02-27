"""Tests for signup service — email validation, invite codes, plan selection (CAB-1541)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.tenant import TenantProvisioningStatus
from src.schemas.self_service import SelfServiceSignupRequest, SignupPlan
from src.services.signup_service import (
    slugify_tenant_name,
    validate_email_domain,
    validate_invite_code,
)


# ── slugify_tenant_name ──


class TestSlugifyTenantName:
    def test_basic_slug(self):
        assert slugify_tenant_name("My Company") == "my-company"

    def test_preserves_hyphens(self):
        assert slugify_tenant_name("acme-corp") == "acme-corp"

    def test_strips_special_chars(self):
        assert slugify_tenant_name("Hello World!") == "hello-world"

    def test_collapses_multiple_hyphens(self):
        assert slugify_tenant_name("foo  bar") == "foo-bar"

    def test_strips_leading_trailing_hyphens(self):
        assert slugify_tenant_name("-foo-") == "foo"

    def test_underscores_become_empty(self):
        # underscores are removed by the regex, spaces become hyphens
        assert slugify_tenant_name("my_company") == "mycompany"

    def test_invalid_slug_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            slugify_tenant_name("!!!")
        assert exc_info.value.status_code == 400


# ── validate_email_domain ──


class TestValidateEmailDomain:
    def test_valid_domain_passes(self):
        validate_email_domain("user@example.com")  # must not raise

    def test_corporate_domain_passes(self):
        validate_email_domain("dev@acme-corp.io")  # must not raise

    def test_disposable_domain_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_email_domain("spam@mailinator.com")
        assert exc_info.value.status_code == 400
        assert "mailinator.com" in exc_info.value.detail

    def test_disposable_yopmail_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            validate_email_domain("test@yopmail.com")

    def test_disposable_guerrillamail_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            validate_email_domain("x@guerrillamail.com")

    def test_case_insensitive_domain(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            validate_email_domain("user@Mailinator.COM")

    def test_config_override_blocklist(self, monkeypatch):
        """SIGNUP_BLOCKED_EMAIL_DOMAINS config overrides the default blocklist."""
        monkeypatch.setattr(
            "src.services.signup_service.settings",
            type("S", (), {"SIGNUP_BLOCKED_EMAIL_DOMAINS": "custom-blocked.com,another.org"})(),
        )
        from fastapi import HTTPException

        # Custom domain is blocked
        with pytest.raises(HTTPException):
            validate_email_domain("user@custom-blocked.com")

        # Default blocklist domain is now allowed (override replaces, not extends)
        validate_email_domain("user@mailinator.com")  # must not raise


# ── validate_invite_code ──


class TestValidateInviteCode:
    def _mock_settings(self, codes: str = ""):
        return type("S", (), {"signup_invite_codes_list": [c.strip() for c in codes.split(",") if c.strip()]})()

    def test_trial_no_code_no_config_passes(self, monkeypatch):
        monkeypatch.setattr("src.services.signup_service.settings", self._mock_settings(""))
        validate_invite_code(None, SignupPlan.TRIAL)  # must not raise

    def test_trial_valid_code_passes(self, monkeypatch):
        monkeypatch.setattr("src.services.signup_service.settings", self._mock_settings("BETA2026"))
        validate_invite_code("BETA2026", SignupPlan.TRIAL)  # must not raise

    def test_trial_invalid_code_raises(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr("src.services.signup_service.settings", self._mock_settings("BETA2026"))
        with pytest.raises(HTTPException) as exc_info:
            validate_invite_code("WRONG", SignupPlan.TRIAL)
        assert exc_info.value.status_code == 400

    def test_standard_requires_code(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr("src.services.signup_service.settings", self._mock_settings("STD-CODE"))
        with pytest.raises(HTTPException) as exc_info:
            validate_invite_code(None, SignupPlan.STANDARD)
        assert exc_info.value.status_code == 400
        assert "required" in exc_info.value.detail.lower()

    def test_standard_valid_code_passes(self, monkeypatch):
        monkeypatch.setattr("src.services.signup_service.settings", self._mock_settings("STD-CODE"))
        validate_invite_code("STD-CODE", SignupPlan.STANDARD)  # must not raise

    def test_standard_invalid_code_raises(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr("src.services.signup_service.settings", self._mock_settings("STD-CODE"))
        with pytest.raises(HTTPException) as exc_info:
            validate_invite_code("BAD-CODE", SignupPlan.STANDARD)
        assert exc_info.value.status_code == 400


# ── signup_tenant (integration-level unit tests) ──


def _make_tenant_mock(
    tenant_id="my-company",
    provisioning_status="pending",
    settings=None,
):
    m = MagicMock()
    m.id = tenant_id
    m.provisioning_status = provisioning_status
    m.settings = settings or {"plan": "trial"}
    return m


class TestSignupTenant:
    @pytest.mark.asyncio
    async def test_new_signup_returns_provisioning(self, monkeypatch):
        """New tenant signup creates tenant and returns provisioning status."""
        from src.services.signup_service import signup_tenant

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": [],
        })())
        monkeypatch.setattr("src.services.signup_service.TenantRepository", lambda db: mock_repo)
        monkeypatch.setattr("src.services.signup_service.provision_tenant", AsyncMock())

        req = SelfServiceSignupRequest(
            name="My Company",
            display_name="My Company Inc.",
            owner_email="owner@example.com",
        )
        result = await signup_tenant(mock_db, req)

        assert result.tenant_id == "my-company"
        assert result.status == "provisioning"
        assert result.plan == "trial"
        mock_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_ready_returns_ready(self, monkeypatch):
        """Existing READY tenant returns idempotent ready response."""
        from src.services.signup_service import signup_tenant

        existing = _make_tenant_mock(
            provisioning_status=TenantProvisioningStatus.READY.value,
            settings={"plan": "standard"},
        )
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing)
        mock_db = AsyncMock()

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": [],
        })())
        monkeypatch.setattr("src.services.signup_service.TenantRepository", lambda db: mock_repo)

        req = SelfServiceSignupRequest(
            name="My Company",
            display_name="My Company Inc.",
            owner_email="owner@example.com",
        )
        result = await signup_tenant(mock_db, req)

        assert result.status == "ready"
        assert result.plan == "standard"

    @pytest.mark.asyncio
    async def test_existing_provisioning_returns_current_status(self, monkeypatch):
        """Existing PROVISIONING tenant returns current status."""
        from src.services.signup_service import signup_tenant

        existing = _make_tenant_mock(
            provisioning_status=TenantProvisioningStatus.PROVISIONING.value,
        )
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing)
        mock_db = AsyncMock()

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": [],
        })())
        monkeypatch.setattr("src.services.signup_service.TenantRepository", lambda db: mock_repo)

        req = SelfServiceSignupRequest(
            name="My Company",
            display_name="My Company Inc.",
            owner_email="owner@example.com",
        )
        result = await signup_tenant(mock_db, req)

        assert result.status == "provisioning"

    @pytest.mark.asyncio
    async def test_disposable_email_blocked(self, monkeypatch):
        """Signup with disposable email is rejected."""
        from fastapi import HTTPException

        from src.services.signup_service import signup_tenant

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": [],
        })())

        req = SelfServiceSignupRequest(
            name="Spammer Inc",
            display_name="Spammer",
            owner_email="spam@mailinator.com",
        )
        with pytest.raises(HTTPException) as exc_info:
            await signup_tenant(AsyncMock(), req)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_standard_plan_without_code_rejected(self, monkeypatch):
        """Standard plan signup without invite code is rejected."""
        from fastapi import HTTPException

        from src.services.signup_service import signup_tenant

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": ["VALID-CODE"],
        })())

        req = SelfServiceSignupRequest(
            name="Enterprise Corp",
            display_name="Enterprise Corp",
            owner_email="cto@enterprise.com",
            plan=SignupPlan.STANDARD,
        )
        with pytest.raises(HTTPException) as exc_info:
            await signup_tenant(AsyncMock(), req)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_standard_plan_with_valid_code_succeeds(self, monkeypatch):
        """Standard plan signup with valid invite code succeeds."""
        from src.services.signup_service import signup_tenant

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": ["ENTERPRISE-2026"],
        })())
        monkeypatch.setattr("src.services.signup_service.TenantRepository", lambda db: mock_repo)
        monkeypatch.setattr("src.services.signup_service.provision_tenant", AsyncMock())

        req = SelfServiceSignupRequest(
            name="Enterprise Corp",
            display_name="Enterprise Corp",
            owner_email="cto@enterprise.com",
            plan=SignupPlan.STANDARD,
            invite_code="ENTERPRISE-2026",
        )
        result = await signup_tenant(mock_db, req)

        assert result.plan == "standard"
        assert result.status == "provisioning"

    @pytest.mark.asyncio
    async def test_plan_stored_in_tenant_settings(self, monkeypatch):
        """Plan value is stored in tenant.settings."""
        from src.services.signup_service import signup_tenant

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        created_tenants = []

        async def capture_create(tenant):
            created_tenants.append(tenant)

        mock_repo.create = AsyncMock(side_effect=capture_create)
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "signup_invite_codes_list": [],
        })())
        monkeypatch.setattr("src.services.signup_service.TenantRepository", lambda db: mock_repo)
        monkeypatch.setattr("src.services.signup_service.provision_tenant", AsyncMock())

        req = SelfServiceSignupRequest(
            name="Test Corp",
            display_name="Test Corp",
            owner_email="test@example.com",
            plan=SignupPlan.TRIAL,
        )
        await signup_tenant(mock_db, req)

        assert len(created_tenants) == 1
        assert created_tenants[0].settings["plan"] == "trial"
