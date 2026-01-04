"""Tests for health endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test /health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "stoa-mcp-gateway"
    assert "version" in data
    assert "timestamp" in data


def test_ready_endpoint(client):
    """Test /ready endpoint returns status."""
    response = client.get("/ready")
    # Status can be 200 (ready) or 503 (not ready) depending on app state
    assert response.status_code in [200, 503]
    data = response.json()
    assert data["status"] in ["ready", "not_ready"]
    assert data["service"] == "stoa-mcp-gateway"
    assert "checks" in data


def test_live_endpoint(client):
    """Test /live endpoint returns alive status."""
    response = client.get("/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_root_endpoint(client):
    """Test root endpoint returns service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "stoa-mcp-gateway"
    assert "version" in data
    assert "links" in data


def test_mcp_tools_endpoint(client):
    """Test MCP tools endpoint (placeholder)."""
    response = client.get("/mcp/v1/tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data


def test_mcp_resources_endpoint(client):
    """Test MCP resources endpoint (placeholder)."""
    response = client.get("/mcp/v1/resources")
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
