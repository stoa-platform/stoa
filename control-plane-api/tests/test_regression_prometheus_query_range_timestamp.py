"""Regression coverage for Prometheus query_range timestamp formatting."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.prometheus_client import PrometheusClient


@pytest.mark.asyncio
async def test_query_range_uses_prometheus_epoch_timestamps():
    """Range queries must not send timezone strings Prometheus rejects."""
    client = PrometheusClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "data": {"resultType": "matrix", "result": []},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_client_instance

        start = datetime(2026, 5, 10, 15, 55, 23, tzinfo=UTC)
        end = datetime(2026, 5, 10, 16, 0, 23, tzinfo=UTC)
        result = await client.query_range("up", start, end, step="60s")

    assert result == {"resultType": "matrix", "result": []}
    params = mock_client_instance.get.call_args.kwargs["params"]
    assert params["start"] == "1778428523.0"
    assert params["end"] == "1778428823.0"
    assert "+00:00Z" not in params["start"]
    assert "+00:00Z" not in params["end"]
