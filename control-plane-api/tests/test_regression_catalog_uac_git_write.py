"""Regression tests for Git-backed UAC catalog materialization."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.services.github_service import GitHubService


@pytest.mark.asyncio
@patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
@patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
@patch.object(GitHubService, "_ensure_tenant_exists", new_callable=AsyncMock)
async def test_api_create_writes_canonical_uac_json(mock_tenant, mock_exists, mock_batch):
    service = GitHubService()
    service._gh = AsyncMock()
    mock_exists.return_value = False
    mock_batch.return_value = {"sha": "abc", "url": ""}

    await service.create_api(
        "banking-demo",
        {
            "id": "alpha-vantage-stock-data",
            "name": "Alpha Vantage Stock Data",
            "display_name": "Alpha Vantage Stock Data",
            "version": "1.2.0",
            "backend_url": "https://stocks.example.com",
            "openapi_spec": {
                "openapi": "3.0.0",
                "info": {"title": "Alpha Vantage", "version": "1.2.0"},
                "paths": {
                    "/quote": {
                        "get": {
                            "operationId": "getQuote",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            },
        },
    )

    actions = {a["file_path"]: a["content"] for a in mock_batch.call_args.kwargs["actions"]}
    uac = json.loads(actions["tenants/banking-demo/apis/alpha-vantage-stock-data/uac.json"])
    assert uac["name"] == "alpha-vantage-stock-data"
    assert uac["tenant_id"] == "banking-demo"
    assert uac["endpoints"][0]["backend_url"] == "https://stocks.example.com/quote"
