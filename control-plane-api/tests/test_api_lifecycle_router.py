"""Router tests for the canonical API lifecycle endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from src.models.catalog import APICatalog


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalars_result(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def test_create_draft_endpoint_returns_lifecycle_state(client_as_tenant_admin, mock_db_session) -> None:
    mock_db_session.execute.side_effect = [
        _scalar_result(None),
        _scalar_result(None),
        _rows_result([]),
        _scalars_result([]),
    ]

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/lifecycle/drafts",
        json={
            "name": "Payments API",
            "display_name": "Payments API",
            "version": "1.0.0",
            "description": "Payment operations",
            "backend_url": "https://payments.internal",
            "openapi_spec": {
                "openapi": "3.0.3",
                "info": {"title": "Payments API", "version": "1.0.0"},
                "paths": {},
            },
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["api_id"] == "payments-api"
    assert data["catalog_status"] == "draft"
    assert data["lifecycle_phase"] == "draft"
    assert data["portal_published"] is False
    assert data["spec"]["source"] == "inline"
    assert data["deployments"] == []
    assert data["promotions"] == []
    mock_db_session.commit.assert_awaited_once()


def test_get_lifecycle_state_endpoint_is_registered_before_api_catch_all(
    client_as_tenant_admin,
    mock_db_session,
) -> None:
    catalog = APICatalog(
        id=uuid4(),
        tenant_id="acme",
        api_id="payments-api",
        api_name="Payments API",
        version="1.0.0",
        status="draft",
        tags=[],
        portal_published=False,
        api_metadata={
            "display_name": "Payments API",
            "description": "Payment operations",
            "backend_url": "https://payments.internal",
            "lifecycle": {"spec_source": "inline"},
        },
        openapi_spec={
            "openapi": "3.0.3",
            "info": {"title": "Payments API", "version": "1.0.0"},
            "paths": {},
        },
    )
    mock_db_session.execute.side_effect = [
        _scalar_result(catalog),
        _rows_result([]),
        _scalars_result([]),
    ]

    response = client_as_tenant_admin.get("/v1/tenants/acme/apis/payments-api/lifecycle")

    assert response.status_code == 200
    data = response.json()
    assert data["api_id"] == "payments-api"
    assert data["catalog_status"] == "draft"
    assert data["lifecycle_phase"] == "draft"


def test_validate_draft_endpoint_returns_ready_state(client_as_tenant_admin, mock_db_session) -> None:
    catalog = APICatalog(
        id=uuid4(),
        tenant_id="acme",
        api_id="payments-api",
        api_name="Payments API",
        version="1.0.0",
        status="draft",
        tags=[],
        portal_published=False,
        api_metadata={
            "display_name": "Payments API",
            "description": "Payment operations",
            "backend_url": "https://payments.internal",
            "lifecycle": {"spec_source": "inline"},
        },
        openapi_spec={
            "openapi": "3.0.3",
            "info": {"title": "Payments API", "version": "1.0.0"},
            "paths": {"/payments": {"get": {"responses": {"200": {"description": "ok"}}}}},
        },
    )
    mock_db_session.execute.side_effect = [
        _scalar_result(catalog),
        _rows_result([]),
        _scalars_result([]),
    ]

    response = client_as_tenant_admin.post("/v1/tenants/acme/apis/payments-api/lifecycle/validate")

    assert response.status_code == 200
    data = response.json()
    assert data["api_id"] == "payments-api"
    assert data["status"] == "ready"
    assert data["validation"]["valid"] is True
    assert data["validation"]["spec_format"] == "openapi"
    assert data["lifecycle"]["catalog_status"] == "ready"
    assert data["lifecycle"]["deployments"] == []
    mock_db_session.commit.assert_awaited_once()


def test_validate_draft_endpoint_returns_422_for_invalid_spec(client_as_tenant_admin, mock_db_session) -> None:
    catalog = APICatalog(
        id=uuid4(),
        tenant_id="acme",
        api_id="payments-api",
        api_name="Payments API",
        version="1.0.0",
        status="draft",
        tags=[],
        portal_published=False,
        api_metadata={
            "display_name": "Payments API",
            "description": "Payment operations",
            "backend_url": "https://payments.internal",
            "lifecycle": {"spec_source": "inline"},
        },
        openapi_spec={
            "openapi": "3.0.3",
            "info": {"title": "Payments API", "version": "1.0.0"},
            "paths": {"/payments": {"get": {"operationId": "listPayments"}}},
        },
    )
    mock_db_session.execute.side_effect = [_scalar_result(catalog)]

    response = client_as_tenant_admin.post("/v1/tenants/acme/apis/payments-api/lifecycle/validate")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "openapi_operation_responses_missing"
    assert catalog.status == "draft"
    mock_db_session.commit.assert_awaited_once()
