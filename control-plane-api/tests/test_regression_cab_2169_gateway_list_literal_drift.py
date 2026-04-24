from datetime import UTC, datetime
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.models.gateway_instance import GatewayType
from src.schemas.gateway import GatewayTypeLiteral


def _mock_gateway_instance(**overrides):
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "name": "kong-standalone",
        "display_name": "Kong DB-less",
        "gateway_type": "kong",
        "base_url": "https://kong.gostoa.dev",
        "status": "online",
        "environment": "production",
        "mode": None,
        "tenant_id": None,
        "last_health_check": None,
        "auth_config": {},
        "health_details": None,
        "capabilities": [],
        "version": None,
        "tags": [],
        "target_gateway_url": None,
        "public_url": None,
        "ui_url": None,
        "protected": False,
        "enabled": True,
        "visibility": None,
        "source": "self_register",
        "deleted_at": None,
        "deleted_by": None,
        "created_at": datetime(2026, 2, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
    }
    for key, value in {**defaults, **overrides}.items():
        setattr(mock, key, value)
    return mock


def test_regression_cab_2169_gateway_type_literal_covers_every_orm_value():
    orm_values = {gateway_type.value for gateway_type in GatewayType}
    literal_values = set(get_args(GatewayTypeLiteral))
    missing = orm_values - literal_values

    assert not missing, f"GatewayTypeLiteral missing ORM values {missing}."


def test_regression_cab_2169_list_gateways_accepts_every_orm_gateway_type(app_with_cpi_admin, mock_db_session):
    mocks = [
        _mock_gateway_instance(name=f"gw-{gateway_type.value}", gateway_type=gateway_type.value)
        for gateway_type in GatewayType
    ]

    with patch("src.routers.gateway_instances.GatewayInstanceService") as mock_service:
        mock_service.return_value.list = AsyncMock(return_value=(mocks, len(mocks)))

        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/admin/gateways")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == len(mocks)
