"""Unit tests for FederationService — CAB-1378

Tests business logic for master/sub-account lifecycle,
delegation tokens, bulk revoke, and tool allow-lists.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.federation import MasterAccountStatus, SubAccountStatus
from src.services.federation_service import FederationService, _generate_federation_key


class TestGenerateFederationKey:
    """Test _generate_federation_key helper."""

    def test_key_format(self):
        """Key has prefix + random part, hash is sha256."""
        plaintext, key_hash, prefix = _generate_federation_key()

        assert plaintext.startswith("stoa_fed_")
        assert prefix.startswith("stoa_fed_")
        assert plaintext.startswith(prefix)
        assert len(key_hash) == 64  # sha256 hex digest

    def test_keys_are_unique(self):
        """Successive calls produce different keys."""
        k1, h1, _ = _generate_federation_key()
        k2, h2, _ = _generate_federation_key()
        assert k1 != k2
        assert h1 != h2


class TestCreateMasterAccount:
    """FederationService.create_master_account"""

    @pytest.fixture()
    def svc(self):
        db = AsyncMock()
        svc = FederationService(db)
        svc.master_repo = MagicMock()
        svc.sub_repo = MagicMock()
        return svc

    def test_create_success(self, svc):
        """Creates a master account when name is unique."""
        svc.master_repo.get_by_tenant_and_name = AsyncMock(return_value=None)
        mock_master = MagicMock()
        svc.master_repo.create = AsyncMock(return_value=mock_master)

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            svc.create_master_account("acme", "partner-a", "Partner A", None, 10, None, "user-1")
        )

        assert result is mock_master
        svc.master_repo.create.assert_awaited_once()

    def test_create_duplicate_raises(self, svc):
        """Raises ValueError when name already exists."""
        svc.master_repo.get_by_tenant_and_name = AsyncMock(return_value=MagicMock())

        import asyncio

        with pytest.raises(ValueError, match="already exists"):
            asyncio.get_event_loop().run_until_complete(
                svc.create_master_account("acme", "existing", None, None, 10, None, "user-1")
            )


class TestCreateSubAccount:
    """FederationService.create_sub_account"""

    @pytest.fixture()
    def svc(self):
        db = AsyncMock()
        svc = FederationService(db)
        svc.master_repo = MagicMock()
        svc.sub_repo = MagicMock()
        return svc

    @patch("src.services.federation_service.keycloak_service")
    def test_create_sub_success(self, mock_kc, svc):
        """Creates a sub-account with API key and KC client."""
        master = MagicMock()
        master.id = uuid4()
        master.tenant_id = "acme"
        master.name = "partner-a"
        master.max_sub_accounts = 10

        svc.sub_repo.get_by_master_and_name = AsyncMock(return_value=None)
        svc.master_repo.count_sub_accounts = AsyncMock(return_value=2)
        mock_sub = MagicMock()
        svc.sub_repo.create = AsyncMock(return_value=mock_sub)
        mock_kc.setup_federation_client = AsyncMock(return_value="kc-client-id")

        import asyncio

        sub, key = asyncio.get_event_loop().run_until_complete(
            svc.create_sub_account(master, "sub-1", "Sub One", "partner", "user-1")
        )

        assert sub is mock_sub
        assert key.startswith("stoa_fed_")
        svc.sub_repo.create.assert_awaited_once()

    def test_create_sub_limit_exceeded(self, svc):
        """Raises ValueError when sub-account limit reached."""
        master = MagicMock()
        master.id = uuid4()
        master.max_sub_accounts = 2

        svc.sub_repo.get_by_master_and_name = AsyncMock(return_value=None)
        svc.master_repo.count_sub_accounts = AsyncMock(return_value=2)

        import asyncio

        with pytest.raises(ValueError, match="limit"):
            asyncio.get_event_loop().run_until_complete(
                svc.create_sub_account(master, "sub-3", None, "partner", "user-1")
            )


class TestDelegateToken:
    """FederationService.delegate_token"""

    @pytest.fixture()
    def svc(self):
        db = AsyncMock()
        svc = FederationService(db)
        svc.master_repo = MagicMock()
        svc.sub_repo = MagicMock()
        return svc

    @patch("src.services.federation_service.keycloak_service")
    def test_delegate_token_success(self, mock_kc, svc):
        """Issues delegation token for active sub-account."""
        sub = MagicMock()
        sub.status = SubAccountStatus.ACTIVE
        sub.kc_client_id = "kc-client-123"
        sub.name = "sub-1"

        mock_kc.exchange_federation_token = AsyncMock(
            return_value={"access_token": "tok", "expires_in": 3600}
        )

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            svc.delegate_token(sub, ["stoa:read"], 3600)
        )

        assert result["access_token"] == "tok"

    def test_delegate_token_inactive_raises(self, svc):
        """Raises ValueError for non-active sub-account."""
        sub = MagicMock()
        sub.status = SubAccountStatus.REVOKED
        sub.name = "sub-revoked"

        import asyncio

        with pytest.raises(ValueError, match="not active"):
            asyncio.get_event_loop().run_until_complete(
                svc.delegate_token(sub, ["stoa:read"], 3600)
            )


class TestBulkRevoke:
    """FederationService.bulk_revoke"""

    @pytest.fixture()
    def svc(self):
        db = AsyncMock()
        svc = FederationService(db)
        svc.master_repo = MagicMock()
        svc.sub_repo = MagicMock()
        return svc

    def test_bulk_revoke_counts(self, svc):
        """Returns (newly_revoked, already_revoked, total) counts."""
        master_id = uuid4()
        svc.master_repo.count_sub_accounts = AsyncMock(return_value=5)
        svc.sub_repo.bulk_revoke = AsyncMock(return_value=(3, 2))

        import asyncio

        newly, already, total = asyncio.get_event_loop().run_until_complete(
            svc.bulk_revoke(master_id)
        )

        assert newly == 3
        assert already == 2
        assert total == 5
