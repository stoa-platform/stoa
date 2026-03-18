"""Tests for API/MCP Discovery — YAML-driven Catalog (CAB-1637, CAB-1639)."""

import pytest

from src.catalog.loader import (
    CatalogEntry,
    CatalogResponse,
    CatalogTool,
    SearchResult,
    get_catalog,
    get_categories,
    reload_catalog,
)
from src.routers.discovery import DetectedSpec


@pytest.fixture(autouse=True)
def _fresh_catalog():
    """Ensure each test sees a freshly loaded catalog."""
    reload_catalog()
    yield


class TestYAMLCatalog:
    """Tests for the YAML-driven catalog loading."""

    def test_catalog_loads_from_yaml(self):
        """Catalog loads entries from YAML files."""
        entries = get_catalog()
        assert len(entries) > 0
        assert all(isinstance(e, CatalogEntry) for e in entries)

    def test_catalog_has_minimum_entries(self):
        """DoD: Catalogue d'au moins 10 APIs publiques EU pré-configurées."""
        entries = get_catalog()
        assert len(entries) >= 10

    def test_catalog_entries_have_required_fields(self):
        """All entries have the required fields from CAB-1639 spec."""
        for entry in get_catalog():
            assert entry.id
            assert entry.name
            assert entry.display_name
            assert entry.description
            assert entry.category
            assert entry.country
            assert entry.protocol in ("openapi", "mcp", "graphql")
            assert entry.status in ("verified", "community", "experimental")
            assert entry.auth_type in ("none", "api_key", "oauth2", "basic")

    def test_catalog_has_eu_entries(self):
        """Catalog contains EU-region entries."""
        entries = get_catalog()
        eu_entries = [e for e in entries if "EU" in e.region]
        assert len(eu_entries) >= 8

    def test_catalog_has_mcp_entries(self):
        """Catalog contains MCP protocol entries."""
        entries = get_catalog()
        mcp_entries = [e for e in entries if e.protocol == "mcp"]
        assert len(mcp_entries) >= 1

    def test_catalog_has_openapi_entries(self):
        """Catalog contains OpenAPI protocol entries."""
        entries = get_catalog()
        openapi_entries = [e for e in entries if e.protocol == "openapi"]
        assert len(openapi_entries) >= 8

    def test_catalog_ids_are_unique(self):
        """All catalog entry IDs are unique."""
        entries = get_catalog()
        ids = [e.id for e in entries]
        assert len(ids) == len(set(ids))

    def test_catalog_categories(self):
        """Catalog covers multiple categories."""
        categories = get_categories()
        assert len(categories) >= 5

    def test_catalog_has_verified_entries(self):
        """DoD: At least 3 catalog entries are 'verified'."""
        entries = get_catalog()
        verified = [e for e in entries if e.status == "verified"]
        assert len(verified) >= 3

    def test_catalog_has_tools(self):
        """Entries with tools have properly structured tool objects."""
        entries = get_catalog()
        entries_with_tools = [e for e in entries if e.tools]
        assert len(entries_with_tools) >= 5
        for entry in entries_with_tools:
            for tool in entry.tools:
                assert isinstance(tool, CatalogTool)
                assert tool.name

    def test_catalog_has_country_codes(self):
        """Entries have valid country codes."""
        entries = get_catalog()
        countries = {e.country for e in entries}
        assert "FR" in countries
        assert "EU" in countries

    def test_reload_catalog(self):
        """reload_catalog() forces a fresh load."""
        entries1 = get_catalog()
        entries2 = reload_catalog()
        assert len(entries1) == len(entries2)


class TestCatalogFiltering:
    """Tests for catalog filtering."""

    def test_filter_by_category(self):
        """Filter catalog by category."""
        entries = get_catalog()
        business = [e for e in entries if e.category == "business-registry"]
        assert len(business) >= 2

    def test_filter_by_protocol(self):
        """Filter catalog by protocol."""
        entries = get_catalog()
        mcp_only = [e for e in entries if e.protocol == "mcp"]
        openapi_only = [e for e in entries if e.protocol == "openapi"]
        assert len(mcp_only) + len(openapi_only) == len(entries)

    def test_filter_by_region(self):
        """Filter catalog by region."""
        entries = get_catalog()
        fr_entries = [e for e in entries if "FR" in e.region]
        assert len(fr_entries) >= 1

    def test_filter_by_country(self):
        """Filter catalog by country code."""
        entries = get_catalog()
        fr_entries = [e for e in entries if e.country == "FR"]
        assert len(fr_entries) >= 2  # INPI, DGFiP, BOAMP, FranceConnect, data.gouv.fr

    def test_filter_by_status(self):
        """Filter catalog by verification status."""
        entries = get_catalog()
        verified = [e for e in entries if e.status == "verified"]
        community = [e for e in entries if e.status == "community"]
        experimental = [e for e in entries if e.status == "experimental"]
        assert len(verified) >= 3
        assert len(community) >= 3
        assert len(experimental) >= 1


class TestSearch:
    """Tests for catalog search functionality."""

    def test_search_by_name(self):
        """Search finds entries by name."""
        entries = get_catalog()
        query = "inpi"
        matches = [
            e
            for e in entries
            if query in e.name.lower() or query in e.display_name.lower() or query in e.description.lower()
        ]
        assert len(matches) >= 1

    def test_search_by_tag(self):
        """Search finds entries by tag."""
        entries = get_catalog()
        query = "vat"
        matches = [e for e in entries if any(query in tag for tag in e.tags)]
        assert len(matches) >= 1

    def test_search_by_category(self):
        """Search finds entries by category."""
        entries = get_catalog()
        query = "finance"
        matches = [e for e in entries if query in e.category.lower()]
        assert len(matches) >= 1

    def test_search_no_results(self):
        """Search returns empty for non-matching query."""
        entries = get_catalog()
        query = "xyznonexistent"
        matches = [
            e
            for e in entries
            if query in e.name.lower() or query in e.display_name.lower() or query in e.description.lower()
        ]
        assert len(matches) == 0

    def test_search_case_insensitive(self):
        """Search is case-insensitive."""
        entries = get_catalog()
        for query in ["INPI", "inpi", "Inpi"]:
            matches = [
                e
                for e in entries
                if query.lower() in e.name.lower()
                or query.lower() in e.display_name.lower()
                or query.lower() in e.description.lower()
            ]
            assert len(matches) >= 1


class TestDetection:
    """Tests for URL-based protocol detection schemas."""

    def test_detected_spec_schema(self):
        """DetectedSpec schema validates correctly."""
        spec = DetectedSpec(
            url="https://example.com/openapi.json",
            protocol="openapi",
            title="Test API",
            version="1.0.0",
            endpoints_count=5,
        )
        assert spec.protocol == "openapi"
        assert spec.endpoints_count == 5

    def test_detected_mcp_spec(self):
        """DetectedSpec schema works for MCP."""
        spec = DetectedSpec(
            url="https://example.com/mcp/capabilities",
            protocol="mcp",
            title="Test MCP",
            tools_count=10,
        )
        assert spec.protocol == "mcp"
        assert spec.tools_count == 10

    def test_catalog_response_schema(self):
        """CatalogResponse schema validates correctly."""
        resp = CatalogResponse(
            entries=get_catalog()[:2],
            total=2,
            categories=["business-registry"],
        )
        assert resp.total == 2

    def test_search_result_schema(self):
        """SearchResult schema validates correctly."""
        resp = SearchResult(
            entries=get_catalog()[:1],
            total=1,
            query="test",
        )
        assert resp.query == "test"
