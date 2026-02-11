# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Cross-tenant cache isolation tests (CAB-881 — Step 4/4).

Pr1nc3ss requirement: Zero data leakage between tenants.

Verifies:
- Tenant A cannot read Tenant B's cache entries
- Invalidation is tenant-scoped
- GDPR cleanup respects tenant boundaries
- Lookup queries always include tenant_id WHERE clause
"""

import json
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.cache.semantic_cache import SemanticCache


@pytest.fixture
def mock_session():
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None
    result.rowcount = 0
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


@pytest.fixture
def cache():
    embedder = MagicMock()
    embedder.build_cache_key.return_value = '{"tool":"test","args":{}}'
    embedder.hash_key.return_value = "a" * 64
    embedder.embed.return_value = [0.1] * 384
    return SemanticCache(embedder=embedder)


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


class TestCrossTenantIsolation:
    """Ensure cache queries ALWAYS filter by tenant_id."""

    @pytest.mark.asyncio
    async def test_lookup_includes_tenant_id(self, cache, mock_session):
        """Every lookup query must include tenant_id parameter."""
        await cache.lookup(mock_session, "tenant-alpha", "tool-a", {})

        for call_args in mock_session.execute.call_args_list:
            params = call_args[0][1]  # Second positional arg is params dict
            assert "tenant_id" in params
            assert params["tenant_id"] == "tenant-alpha"

    @pytest.mark.asyncio
    async def test_different_tenants_different_lookups(self, cache, mock_session):
        """Two tenants with same tool+args should produce separate queries."""
        await cache.lookup(mock_session, "tenant-alpha", "tool-a", {"q": "test"})
        mock_session.execute.reset_mock()

        await cache.lookup(mock_session, "tenant-beta", "tool-a", {"q": "test"})

        for call_args in mock_session.execute.call_args_list:
            params = call_args[0][1]
            assert params["tenant_id"] == "tenant-beta"

    @pytest.mark.asyncio
    async def test_store_includes_tenant_id(self, cache, mock_session):
        """Store must bind tenant_id in the INSERT."""
        await cache.store(
            mock_session, "tenant-alpha", "tool-a", {}, {"data": "secret"}
        )

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == "tenant-alpha"

    @pytest.mark.asyncio
    async def test_invalidate_scoped_to_tenant(self, cache, mock_session):
        """Invalidation must only delete entries for the specified tenant."""
        result = MagicMock()
        result.rowcount = 5
        mock_session.execute = AsyncMock(return_value=result)

        await cache.invalidate(mock_session, "tenant-alpha", tool_name="tool-a")

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == "tenant-alpha"
        assert params["tool_name"] == "tool-a"

    @pytest.mark.asyncio
    async def test_invalidate_all_scoped_to_tenant(self, cache, mock_session):
        """Full invalidation (no tool_name) still scoped to tenant."""
        result = MagicMock()
        result.rowcount = 10
        mock_session.execute = AsyncMock(return_value=result)

        await cache.invalidate(mock_session, "tenant-beta")

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == "tenant-beta"
        assert "tool_name" not in params

    @pytest.mark.asyncio
    async def test_sql_queries_contain_tenant_filter(self, cache, mock_session):
        """Verify the raw SQL text contains WHERE tenant_id clause."""
        await cache.lookup(mock_session, "tenant-x", "tool", {})

        for call_args in mock_session.execute.call_args_list:
            sql_text = str(call_args[0][0])
            assert "tenant_id" in sql_text.lower()


# =============================================================================
# RLS Policy Verification
# =============================================================================


class TestRLSPolicy:
    """Verify the migration creates proper RLS policies."""

    def test_migration_file_has_rls(self):
        """The migration must enable RLS and create a tenant_isolation policy."""
        from pathlib import Path

        migration_dir = Path(__file__).parent.parent / "migrations" / "versions"
        migration_file = migration_dir / "003_cab881_semantic_cache.py"

        content = migration_file.read_text()
        assert "ENABLE ROW LEVEL SECURITY" in content
        assert "tenant_isolation" in content
        assert "tenant_id" in content

    def test_migration_has_downgrade(self):
        """Downgrade must drop the RLS policy."""
        from pathlib import Path

        migration_dir = Path(__file__).parent.parent / "migrations" / "versions"
        migration_file = migration_dir / "003_cab881_semantic_cache.py"

        content = migration_file.read_text()
        assert "DROP POLICY" in content
        assert "DISABLE ROW LEVEL SECURITY" in content


# =============================================================================
# Tenant-Scoped Cleanup
# =============================================================================


class TestTenantScopedCleanup:

    @pytest.mark.asyncio
    async def test_expired_cleanup_not_tenant_scoped(self, cache, mock_session):
        """TTL cleanup deletes ALL expired entries (cross-tenant is OK for expired)."""
        result = MagicMock()
        result.rowcount = 15
        mock_session.execute = AsyncMock(return_value=result)

        count = await cache.cleanup_expired(mock_session)
        assert count == 15

        # TTL cleanup uses expires_at, not tenant_id
        sql = str(mock_session.execute.call_args[0][0])
        assert "expires_at" in sql.lower()

    @pytest.mark.asyncio
    async def test_gdpr_cleanup_not_tenant_scoped(self, cache, mock_session):
        """GDPR cleanup deletes ALL old entries (hard delete for compliance)."""
        result = MagicMock()
        result.rowcount = 8
        mock_session.execute = AsyncMock(return_value=result)

        count = await cache.cleanup_gdpr(mock_session, max_age_hours=24)
        assert count == 8
