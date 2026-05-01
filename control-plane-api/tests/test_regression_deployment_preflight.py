"""Regression tests for deployment preflight before Kafka/SSE dispatch.

webMethods can reject syntactically parseable OpenAPI specs during import with
generic 400 errors. The deploy flow must catch deterministic contract failures
before creating GatewayDeployment records and before emitting sync events.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _catalog(openapi_spec: dict):
    catalog = MagicMock()
    catalog.id = uuid4()
    catalog.api_name = "Alpha Vantage Stock Data"
    catalog.api_id = "stoa-Alpha-Vantage-Stock-Data"
    catalog.tenant_id = "demo"
    catalog.version = "1.0.0"
    catalog.openapi_spec = openapi_spec
    catalog.api_metadata = None
    return catalog


def _webmethods_gateway():
    gateway = MagicMock()
    gateway.id = uuid4()
    gateway.name = "connect-webmethods-dev"
    gateway.environment = "dev"
    gateway.gateway_type = MagicMock(value="stoa")
    gateway.mode = "connect"
    gateway.source = "self_register"
    gateway.deployment_mode = "connect"
    gateway.target_gateway_type = "webmethods"
    gateway.topology = "remote-agent"
    gateway.health_details = {}
    gateway.endpoints = {}
    gateway.base_url = "http://connect-webmethods-dev:8090"
    gateway.public_url = None
    gateway.ui_url = None
    gateway.target_gateway_url = "https://webmethods.gostoa.dev"
    gateway.tags = ["connect", "webmethods"]
    gateway.enabled = True
    return gateway


@pytest.mark.asyncio
async def test_regression_webmethods_preflight_blocks_invalid_openapi_before_dispatch():
    from src.services.deployment_orchestration_service import DeploymentOrchestrationService

    catalog = _catalog(
        {
            "openapi": "3.0.3",
            "info": {"title": "Alpha Vantage Stock Data", "version": "1.0.0"},
            "paths": {
                "/query": {
                    "get": {
                        "summary": "Fetch stock data"
                        # Missing responses: parseable OpenAPI object, not acceptable for webMethods import.
                    }
                }
            },
        }
    )
    gateway = _webmethods_gateway()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(catalog), _result(gateway), _result(gateway)])
    svc = DeploymentOrchestrationService(db)

    with patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy:
        with pytest.raises(ValueError, match="Deployment preflight failed"):
            await svc.deploy_api_to_env(
                tenant_id="demo",
                api_identifier=str(catalog.id),
                environment="dev",
                gateway_ids=[gateway.id],
                deployed_by="admin",
            )

        mock_deploy.assert_not_awaited()


@pytest.mark.asyncio
async def test_regression_webmethods_preflight_reports_targeted_error():
    from src.services.deployment_orchestration_service import DeploymentOrchestrationService

    catalog = _catalog(
        {
            "openapi": "3.0.3",
            "info": {"title": "Alpha Vantage Stock Data", "version": "1.0.0"},
            "paths": {"/query": {"get": {"summary": "Fetch stock data"}}},
        }
    )
    gateway = _webmethods_gateway()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(catalog), _result(gateway), _result(gateway)])
    svc = DeploymentOrchestrationService(db)

    results = await svc.preflight_deploy_api_to_env(
        tenant_id="demo",
        api_identifier=str(catalog.id),
        environment="dev",
        gateway_ids=[gateway.id],
    )

    assert len(results) == 1
    assert results[0].deployable is False
    assert results[0].gateway_name == "connect-webmethods-dev"
    assert results[0].target_gateway_type == "webmethods"
    assert results[0].errors[0].code == "openapi_operation_responses_missing"
    assert results[0].errors[0].path.endswith(".responses")


@pytest.mark.asyncio
async def test_regression_admin_preflight_reports_targeted_error_for_explicit_gateways():
    from src.services.deployment_orchestration_service import DeploymentOrchestrationService

    catalog = _catalog(
        {
            "openapi": "3.0.3",
            "info": {"title": "Alpha Vantage Stock Data", "version": "1.0.0"},
            "paths": {"/query": {"get": {"summary": "Fetch stock data"}}},
        }
    )
    gateway = _webmethods_gateway()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(catalog), _result(gateway)])
    svc = DeploymentOrchestrationService(db)

    results = await svc.preflight_api_to_gateways(
        api_catalog_id=catalog.id,
        gateway_ids=[gateway.id],
    )

    assert len(results) == 1
    assert results[0].deployable is False
    assert results[0].gateway_name == "connect-webmethods-dev"
    assert results[0].target_gateway_type == "webmethods"
    assert results[0].errors[0].code == "openapi_operation_responses_missing"
