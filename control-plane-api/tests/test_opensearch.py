"""
STOA Platform - OpenSearch Integration Tests
============================================

Tests for:
- Index templates and mappings
- Sync service functionality
- Audit trail logging
- Search API endpoints
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opensearchpy import AsyncOpenSearch


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def opensearch_client() -> AsyncMock:
    """Mock OpenSearch client."""
    client = AsyncMock(spec=AsyncOpenSearch)
    client.info.return_value = {"cluster_name": "test-cluster"}
    client.indices.exists.return_value = True
    client.indices.refresh.return_value = {"_shards": {"successful": 1}}
    return client


@pytest.fixture
def sample_tool() -> dict:
    """Sample tool document."""
    return {
        "id": str(uuid.uuid4()),
        "name": "test-tool",
        "description": "A test tool for unit testing",
        "category": "testing",
        "tags": ["test", "unit", "mock"],
        "tenant_id": "tenant-123",
        "visibility": "private",
        "version": "1.0.0",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "metadata": {"author": "test"},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "call_count": 100,
        "avg_latency_ms": 50.0,
        "success_rate": 0.99,
        "last_called_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_audit_event() -> dict:
    """Sample audit event."""
    return {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": str(uuid.uuid4()),
        "event_type": "subscription.created",
        "event_category": "data_modification",
        "severity": "info",
        "actor": {
            "id": "user-123",
            "email": "test@example.com",
            "type": "user",
        },
        "tenant_id": "tenant-123",
        "resource": {
            "type": "subscription",
            "id": "sub-456",
        },
        "action": "POST /api/v1/subscriptions",
        "outcome": "success",
    }


# =============================================================================
# Index Template Tests
# =============================================================================

class TestIndexTemplates:
    """Tests for index templates."""
    
    def test_tools_template_valid_json(self):
        """Test tools template is valid JSON."""
        with open("index-templates/tools-template.json") as f:
            template = json.load(f)
        
        assert "index_patterns" in template
        assert "template" in template
        assert template["index_patterns"] == ["tools"]
    
    def test_audit_template_valid_json(self):
        """Test audit template is valid JSON."""
        with open("index-templates/audit-template.json") as f:
            template = json.load(f)
        
        assert "index_patterns" in template
        assert template["index_patterns"] == ["audit-*"]
        assert "mappings" in template["template"]
    
    def test_analytics_template_valid_json(self):
        """Test analytics template is valid JSON."""
        with open("index-templates/analytics-template.json") as f:
            template = json.load(f)
        
        assert "index_patterns" in template
        assert template["index_patterns"] == ["analytics-*"]
    
    def test_ism_policies_valid_json(self):
        """Test ISM policies are valid JSON."""
        with open("index-templates/ism-policies.json") as f:
            policies = json.load(f)
        
        assert "policies" in policies
        assert len(policies["policies"]) == 2
        
        policy_ids = [p["policy_id"] for p in policies["policies"]]
        assert "audit-policy" in policy_ids
        assert "analytics-policy" in policy_ids


# =============================================================================
# Sync Service Tests
# =============================================================================

class TestSyncService:
    """Tests for sync service."""
    
    @pytest.mark.asyncio
    async def test_transform_tool(self, sample_tool):
        """Test tool transformation."""
        from sync_service import SyncService, Settings
        
        settings = Settings(
            postgres_host="localhost",
            opensearch_host="http://localhost:9200",
        )
        service = SyncService(settings)
        
        doc = service.transform_tool(sample_tool)
        
        assert doc["id"] == sample_tool["id"]
        assert doc["name"] == sample_tool["name"]
        assert doc["tenant_id"] == sample_tool["tenant_id"]
        assert "indexed_at" in doc
        assert doc["stats"]["call_count"] == 100
    
    @pytest.mark.asyncio
    async def test_index_tools(self, opensearch_client, sample_tool):
        """Test bulk indexing tools."""
        from sync_service import SyncService, Settings
        
        settings = Settings(
            postgres_host="localhost",
            opensearch_host="http://localhost:9200",
        )
        service = SyncService(settings)
        service.os_client = opensearch_client
        
        with patch("opensearchpy.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (1, [])
            
            result = await service.index_tools([sample_tool])
            
            assert result["indexed"] == 1
            assert result["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_health_check(self, opensearch_client):
        """Test health check."""
        from sync_service import SyncService, Settings
        
        settings = Settings(
            postgres_host="localhost",
            opensearch_host="http://localhost:9200",
        )
        service = SyncService(settings)
        service.os_client = opensearch_client
        
        # Mock pg_pool
        service.pg_pool = AsyncMock()
        service.pg_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(fetchval=AsyncMock(return_value=1))
        )
        service.pg_pool.acquire.return_value.__aexit__ = AsyncMock()
        
        opensearch_client.cluster.health.return_value = {"status": "green"}
        
        health = await service.health_check()
        
        assert health["status"] == "healthy"


# =============================================================================
# Audit Middleware Tests
# =============================================================================

class TestAuditMiddleware:
    """Tests for audit middleware."""
    
    def test_classify_request_authentication(self):
        """Test authentication request classification."""
        from audit_middleware import AuditMiddleware
        
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/auth/login"
        
        middleware = AuditMiddleware(MagicMock(), MagicMock())
        event_type, category = middleware._classify_request(request)
        
        assert event_type == "authentication"
        assert category.value == "authentication"
    
    def test_classify_request_data_modification(self):
        """Test data modification classification."""
        from audit_middleware import AuditMiddleware
        
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/subscriptions"
        
        middleware = AuditMiddleware(MagicMock(), MagicMock())
        event_type, category = middleware._classify_request(request)
        
        assert "subscription" in event_type
        assert category.value == "data_modification"
    
    def test_get_severity(self):
        """Test severity determination."""
        from audit_middleware import AuditMiddleware, EventSeverity
        
        middleware = AuditMiddleware(MagicMock(), MagicMock())
        
        assert middleware._get_severity(200) == EventSeverity.INFO
        assert middleware._get_severity(400) == EventSeverity.WARNING
        assert middleware._get_severity(500) == EventSeverity.ERROR
    
    def test_extract_resource(self):
        """Test resource extraction from path."""
        from audit_middleware import AuditMiddleware
        
        request = MagicMock()
        request.url.path = "/api/v1/subscriptions/sub-123"
        
        middleware = AuditMiddleware(MagicMock(), MagicMock())
        resource = middleware._extract_resource(request)
        
        assert resource["type"] == "subscription"
        assert resource["id"] == "sub-123"


# =============================================================================
# Search API Tests
# =============================================================================

class TestSearchAPI:
    """Tests for search API."""
    
    @pytest.mark.asyncio
    async def test_search_tools(self, opensearch_client):
        """Test tool search."""
        from search_router import SearchService
        
        opensearch_client.search.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_id": "tool-1",
                        "_score": 1.5,
                        "_source": {
                            "id": "tool-1",
                            "name": "Test Tool",
                            "description": "A test tool",
                            "category": "testing",
                            "tags": ["test"],
                            "tenant_id": "tenant-123",
                            "visibility": "private",
                            "version": "1.0.0",
                            "stats": {},
                        },
                        "highlight": {
                            "name": ["<em>Test</em> Tool"],
                        },
                    }
                ],
            },
            "aggregations": {
                "categories": {"buckets": [{"key": "testing", "doc_count": 1}]},
                "tags": {"buckets": [{"key": "test", "doc_count": 1}]},
                "visibility": {"buckets": [{"key": "private", "doc_count": 1}]},
            },
            "took": 5,
        }
        
        service = SearchService(opensearch_client)
        result = await service.search_tools(
            query="test",
            tenant_id="tenant-123",
        )
        
        assert result.total == 1
        assert len(result.results) == 1
        assert result.results[0].name == "Test Tool"
        assert result.took_ms == 5
    
    @pytest.mark.asyncio
    async def test_suggest(self, opensearch_client):
        """Test auto-complete suggestions."""
        from search_router import SearchService
        
        opensearch_client.search.return_value = {
            "suggest": {
                "tool-suggest": [
                    {
                        "options": [
                            {"_id": "tool-1", "text": "Test Tool", "_score": 1.0},
                        ]
                    }
                ]
            },
            "took": 2,
        }
        
        service = SearchService(opensearch_client)
        result = await service.suggest(
            query="tes",
            tenant_id="tenant-123",
        )
        
        assert len(result.suggestions) == 1
        assert result.suggestions[0]["name"] == "Test Tool"
    
    @pytest.mark.asyncio
    async def test_get_facets(self, opensearch_client):
        """Test facets retrieval."""
        from search_router import SearchService
        
        opensearch_client.search.return_value = {
            "aggregations": {
                "categories": {"buckets": [
                    {"key": "testing", "doc_count": 5},
                    {"key": "utilities", "doc_count": 3},
                ]},
                "tags": {"buckets": [
                    {"key": "test", "doc_count": 5},
                ]},
                "visibility": {"buckets": [
                    {"key": "private", "doc_count": 8},
                ]},
            },
        }
        
        service = SearchService(opensearch_client)
        result = await service.get_facets(tenant_id="tenant-123")
        
        assert len(result.categories) == 2
        assert result.categories[0]["key"] == "testing"


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.integration
class TestOpenSearchIntegration:
    """Integration tests (require running OpenSearch)."""
    
    @pytest.fixture
    async def real_client(self) -> AsyncGenerator[AsyncOpenSearch, None]:
        """Get real OpenSearch client."""
        import os
        
        client = AsyncOpenSearch(
            hosts=[os.environ.get("OPENSEARCH_HOST", "https://localhost:9200")],
            http_auth=(
                os.environ.get("OPENSEARCH_USER", "admin"),
                os.environ.get("OPENSEARCH_PASSWORD", "admin"),
            ),
            verify_certs=False,
        )
        
        try:
            yield client
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_index_and_search(self, real_client):
        """Test end-to-end index and search."""
        # Create test document
        doc = {
            "id": str(uuid.uuid4()),
            "name": "Integration Test Tool",
            "description": "Tool for integration testing",
            "category": "testing",
            "tags": ["integration", "test"],
            "tenant_id": "test-tenant",
            "visibility": "private",
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Index document
        await real_client.index(
            index="tools",
            id=doc["id"],
            body=doc,
            refresh=True,
        )
        
        # Search for it
        result = await real_client.search(
            index="tools",
            body={
                "query": {
                    "match": {"name": "Integration"}
                }
            }
        )
        
        assert result["hits"]["total"]["value"] >= 1
        
        # Cleanup
        await real_client.delete(
            index="tools",
            id=doc["id"],
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
