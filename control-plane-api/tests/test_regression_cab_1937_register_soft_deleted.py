"""Regression test for CAB-1937: gateway registration 409 on soft-deleted instance.

After auto-purge (CAB-1897) or manual cleanup, a gateway re-registering with the
same deterministic name hit a 409 Conflict because get_by_name() filters out
soft-deleted entries, causing the INSERT to violate the unique constraint on name.

Fix: check for soft-deleted entries and resurrect them instead of creating new ones.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.models.gateway_instance import GatewayInstanceStatus, GatewayType

VALID_KEY = "test_key_cab1937"
REGISTER_URL = "/v1/internal/gateways/register"
GW_KEY_HEADER = "X-Gateway-Key"


def _make_gateway_instance(**overrides):
    gw_id = overrides.pop("id", uuid4())
    defaults = {
        "id": gw_id,
        "name": "gw-host-edgemcp-staging",
        "display_name": "STOA Gateway (edge-mcp)",
        "gateway_type": GatewayType.STOA_EDGE_MCP,
        "environment": "staging",
        "tenant_id": None,
        "base_url": "http://localhost:8080",
        "auth_config": {"type": "gateway_key"},
        "status": GatewayInstanceStatus.ONLINE,
        "last_health_check": datetime.now(UTC),
        "health_details": {"mode": "edge-mcp", "hostname": "gw-host"},
        "capabilities": ["rest", "mcp"],
        "version": "0.2.0",
        "tags": ["mode:edge-mcp", "auto-registered"],
        "mode": "edge-mcp",
        "target_gateway_url": None,
        "public_url": None,
        "ui_url": None,
        "protected": False,
        "deleted_at": None,
        "deleted_by": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestRegressionCab1937RegisterSoftDeleted:
    """POST /register must resurrect a soft-deleted entry instead of 409."""

    def test_regression_register_after_soft_delete(self, client):
        """Gateway re-registration after auto-purge resurrects the soft-deleted entry."""
        deleted_gw = _make_gateway_instance(
            deleted_at=datetime(2026, 3, 30, tzinfo=UTC),
            deleted_by="auto-purge",
            status=MagicMock(value="offline"),
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=deleted_gw)
            mock_repo.update = AsyncMock(return_value=deleted_gw)

            resp = client.post(
                REGISTER_URL,
                json={
                    "hostname": "gw-host",
                    "mode": "edge-mcp",
                    "version": "0.3.0",
                    "environment": "staging",
                    "admin_url": "http://gw:8080",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 201
        mock_repo.create.assert_not_called()
        mock_repo.update.assert_awaited_once()
        assert deleted_gw.deleted_at is None
        assert deleted_gw.deleted_by is None
        assert deleted_gw.version == "0.3.0"

    def test_regression_resurrect_skips_cancel_and_replace(self, client):
        """Resurrection path should not reach cancel-and-replace or create steps."""
        deleted_gw = _make_gateway_instance(
            deleted_at=datetime(2026, 3, 30, tzinfo=UTC),
            deleted_by="replaced-by:other-gw",
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=deleted_gw)
            mock_repo.update = AsyncMock(return_value=deleted_gw)

            resp = client.post(
                REGISTER_URL,
                json={
                    "hostname": "gw-host",
                    "mode": "edge-mcp",
                    "version": "0.2.0",
                    "environment": "staging",
                    "admin_url": "http://gw:8080",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 201
        mock_repo.find_self_registered_by_mode_env.assert_not_called()
        mock_repo.get_by_source_and_type.assert_not_called()
        mock_repo.create.assert_not_called()
