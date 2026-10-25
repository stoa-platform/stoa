"""Tests for signup service — email validation, invite codes, plan selection (CAB-1541)."""

from unittest.mock import AsyncMock, MagicMock

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
    def configure(self, monkeypatch, mode="invite", codes=()):
        settings = type("S", (), {"SIGNUP_MODE": mode, "signup_invite_codes_list": list(codes)})()
        monkeypatch.setattr("src.services.signup_service.settings", settings)

    @pytest.mark.parametrize("plan", [SignupPlan.TRIAL, SignupPlan.STANDARD])
    def test_default_refuses_without_invitation(self, monkeypatch, plan):
        from fastapi import HTTPException

        self.configure(monkeypatch)
        with pytest.raises(HTTPException) as caught:
            validate_invite_code(None, plan)
        assert caught.value.status_code == 400
        assert caught.value.detail == "Signup is unavailable."

    @pytest.mark.parametrize("plan", [SignupPlan.TRIAL, SignupPlan.STANDARD])
    def test_valid_invitation_passes(self, monkeypatch, plan):
        import secrets

        code = secrets.token_urlsafe(32)
        self.configure(monkeypatch, codes=[code])
        validate_invite_code(code, plan)

    def test_open_trial_is_explicit(self, monkeypatch):
        self.configure(monkeypatch, mode="open")
        validate_invite_code(None, SignupPlan.TRIAL)

    def test_open_standard_still_requires_invitation(self, monkeypatch):
        from fastapi import HTTPException

        self.configure(monkeypatch, mode="open")
        with pytest.raises(HTTPException):
            validate_invite_code(None, SignupPlan.STANDARD)

    def test_invalid_and_missing_codes_have_same_response(self, monkeypatch):
        import secrets

        from fastapi import HTTPException

        self.configure(monkeypatch, codes=[secrets.token_urlsafe(32)])
        details = []
        for code in (None, secrets.token_urlsafe(32)):
            with pytest.raises(HTTPException) as caught:
                validate_invite_code(code, SignupPlan.TRIAL)
            details.append(caught.value.detail)
        assert details == ["Signup is unavailable."] * 2

    def test_settings_default_and_unknown_mode(self):
        from pydantic import ValidationError

        from src.config import Settings

        assert Settings.model_fields["SIGNUP_MODE"].default == "invite"
        with pytest.raises(ValidationError) as caught:
            Settings(SIGNUP_MODE="unsupported", _env_file=None)
        assert any(error["loc"] == ("SIGNUP_MODE",) for error in caught.value.errors(include_input=False))


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
            "SIGNUP_MODE": "open",
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
            "SIGNUP_MODE": "open",
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
            "SIGNUP_MODE": "open",
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
            "SIGNUP_MODE": "open",
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
            "SIGNUP_MODE": "invite",
            "signup_invite_codes_list": [],
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
        import secrets

        code = secrets.token_urlsafe(32)
        from src.services.signup_service import signup_tenant

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        monkeypatch.setattr("src.services.signup_service.settings", type("S", (), {
            "SIGNUP_BLOCKED_EMAIL_DOMAINS": "",
            "SIGNUP_MODE": "invite",
            "signup_invite_codes_list": [code],
        })())
        monkeypatch.setattr("src.services.signup_service.TenantRepository", lambda db: mock_repo)
        monkeypatch.setattr("src.services.signup_service.provision_tenant", AsyncMock())

        req = SelfServiceSignupRequest(
            name="Enterprise Corp",
            display_name="Enterprise Corp",
            owner_email="cto@enterprise.com",
            plan=SignupPlan.STANDARD,
            invite_code=code,
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
            "SIGNUP_MODE": "open",
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
