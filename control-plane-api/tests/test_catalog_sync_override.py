"""Tests for multi-environment override support in CatalogSyncService (CAB-2015).

Covers: resolve_api_config, _upsert_api with overrides, GitProvider.get_api_override.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.catalog_sync_service import CatalogSyncService, resolve_api_config

# ─────────────────────────────────────────────
# Unit tests for resolve_api_config (pure function)
# ─────────────────────────────────────────────


class TestResolveApiConfig:
    """DoD: base only, base+override, new keys, removed keys."""

    def test_base_only_no_override(self):
        """Override absent = base config returned unchanged."""
        base = {"name": "billing-api", "backend_url": "https://default.internal", "version": "1.0.0"}
        result = resolve_api_config(base, None)
        assert result == base
        assert result is not base  # should not mutate original

    def test_base_plus_override_replaces_keys(self):
        """Override keys replace base keys (shallow merge)."""
        base = {"name": "billing-api", "backend_url": "https://default.internal", "rate_limit": 100}
        override = {"backend_url": "https://staging-billing.internal", "rate_limit": 50}
        result = resolve_api_config(base, override)
        assert result == {
            "name": "billing-api",
            "backend_url": "https://staging-billing.internal",
            "rate_limit": 50,
        }

    def test_override_with_new_keys(self):
        """Override can add keys not present in base."""
        base = {"name": "billing-api", "backend_url": "https://default.internal"}
        override = {"cache_ttl": 300, "debug": True}
        result = resolve_api_config(base, override)
        assert result == {
            "name": "billing-api",
            "backend_url": "https://default.internal",
            "cache_ttl": 300,
            "debug": True,
        }

    def test_override_does_not_remove_base_keys(self):
        """Shallow merge: base keys not in override remain untouched."""
        base = {"name": "billing-api", "backend_url": "https://default.internal", "tags": ["finance"]}
        override = {"backend_url": "https://prod-billing.acme.com"}
        result = resolve_api_config(base, override)
        assert result["tags"] == ["finance"]
        assert result["name"] == "billing-api"
        assert result["backend_url"] == "https://prod-billing.acme.com"

    def test_empty_override_returns_base(self):
        """Empty override dict returns base unchanged."""
        base = {"name": "billing-api"}
        result = resolve_api_config(base, {})
        assert result == base


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


def _make_git() -> MagicMock:
    git = MagicMock()
    git._project = MagicMock()
    git.connect = AsyncMock()
    git.get_api_override = AsyncMock(return_value=None)
    return git


# ─────────────────────────────────────────────
# Integration tests: _upsert_api with override merge
# ─────────────────────────────────────────────


class TestUpsertApiWithOverride:
    """CatalogSyncService._upsert_api must merge overrides before DB insert."""

    @pytest.fixture
    def svc(self):
        db = _make_db()
        git = _make_git()
        return CatalogSyncService(db=db, git_service=git, enable_gateway_reconciliation=False)

    @pytest.mark.asyncio
    async def test_upsert_without_override(self, svc):
        """When no override exists, api_metadata stored as-is."""
        svc.git.get_api_override.return_value = None
        api = {"name": "billing-api", "backend_url": "https://default.internal", "version": "1.0.0"}

        await svc._upsert_api("acme", "billing-api", api, None, "abc123")

        svc.db.execute.assert_called_once()
        params = svc.db.execute.call_args[0][0].compile().params
        # Column is named "metadata" in APICatalog model
        assert params["metadata"]["backend_url"] == "https://default.internal"

    @pytest.mark.asyncio
    async def test_upsert_with_override_merges(self, svc):
        """When override exists, merged config stored in api_metadata."""
        svc.git.get_api_override.return_value = {
            "backend_url": "https://staging-billing.internal",
            "rate_limit": 50,
        }
        api = {"name": "billing-api", "backend_url": "https://default.internal", "version": "1.0.0"}

        await svc._upsert_api("acme", "billing-api", api, None, "abc123")

        svc.db.execute.assert_called_once()
        params = svc.db.execute.call_args[0][0].compile().params
        assert params["metadata"]["backend_url"] == "https://staging-billing.internal"
        assert params["metadata"]["rate_limit"] == 50
        assert params["metadata"]["version"] == "1.0.0"
