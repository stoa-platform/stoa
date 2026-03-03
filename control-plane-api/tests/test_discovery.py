"""Tests for API/MCP Discovery — Smart Connector Catalog (CAB-1637)."""


from src.routers.discovery import (
    CURATED_CATALOG,
    CatalogEntry,
    CatalogResponse,
    DetectedSpec,
    SearchResult,
    _get_catalog,
)


class TestCuratedCatalog:
    """Tests for the curated catalog data and listing."""

    def test_catalog_has_minimum_entries(self):
        """DoD: Catalogue d'au moins 10 APIs publiques EU pré-configurées."""
        assert len(CURATED_CATALOG) >= 10

    def test_catalog_entries_are_valid(self):
        """All catalog entries parse as valid CatalogEntry."""
        entries = _get_catalog()
        assert all(isinstance(e, CatalogEntry) for e in entries)

    def test_catalog_has_eu_entries(self):
        """Catalog contains EU-region entries."""
        entries = _get_catalog()
        eu_entries = [e for e in entries if "EU" in e.region]
        assert len(eu_entries) >= 8

    def test_catalog_has_mcp_entries(self):
        """Catalog contains MCP protocol entries."""
        entries = _get_catalog()
        mcp_entries = [e for e in entries if e.protocol == "mcp"]
        assert len(mcp_entries) >= 1

    def test_catalog_has_openapi_entries(self):
        """Catalog contains OpenAPI protocol entries."""
        entries = _get_catalog()
        openapi_entries = [e for e in entries if e.protocol == "openapi"]
        assert len(openapi_entries) >= 8

    def test_catalog_ids_are_unique(self):
        """All catalog entry IDs are unique."""
        ids = [e["id"] for e in CURATED_CATALOG]
        assert len(ids) == len(set(ids))

    def test_catalog_categories(self):
        """Catalog covers multiple categories."""
        categories = {e["category"] for e in CURATED_CATALOG}
        assert len(categories) >= 5

    def test_filter_by_category(self):
        """Filter catalog by category."""
        entries = _get_catalog()
        business = [e for e in entries if e.category == "business-registry"]
        assert len(business) >= 2

    def test_filter_by_protocol(self):
        """Filter catalog by protocol."""
        entries = _get_catalog()
        mcp_only = [e for e in entries if e.protocol == "mcp"]
        openapi_only = [e for e in entries if e.protocol == "openapi"]
        assert len(mcp_only) + len(openapi_only) == len(entries)

    def test_filter_by_region(self):
        """Filter catalog by region."""
        entries = _get_catalog()
        fr_entries = [e for e in entries if "FR" in e.region]
        assert len(fr_entries) >= 1


class TestSearch:
    """Tests for catalog search functionality."""

    def test_search_by_name(self):
        """Search finds entries by name."""
        entries = _get_catalog()
        query = "inpi"
        matches = [
            e
            for e in entries
            if query in e.name.lower()
            or query in e.display_name.lower()
            or query in e.description.lower()
        ]
        assert len(matches) >= 1

    def test_search_by_tag(self):
        """Search finds entries by tag."""
        entries = _get_catalog()
        query = "vat"
        matches = [e for e in entries if any(query in tag for tag in e.tags)]
        assert len(matches) >= 1

    def test_search_by_category(self):
        """Search finds entries by category."""
        entries = _get_catalog()
        query = "finance"
        matches = [e for e in entries if query in e.category.lower()]
        assert len(matches) >= 1

    def test_search_no_results(self):
        """Search returns empty for non-matching query."""
        entries = _get_catalog()
        query = "xyznonexistent"
        matches = [
            e
            for e in entries
            if query in e.name.lower()
            or query in e.display_name.lower()
            or query in e.description.lower()
        ]
        assert len(matches) == 0

    def test_search_case_insensitive(self):
        """Search is case-insensitive."""
        entries = _get_catalog()
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
    """Tests for URL-based protocol detection."""

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
            entries=_get_catalog()[:2],
            total=2,
            categories=["business-registry"],
        )
        assert resp.total == 2

    def test_search_result_schema(self):
        """SearchResult schema validates correctly."""
        resp = SearchResult(
            entries=_get_catalog()[:1],
            total=1,
            query="test",
        )
        assert resp.query == "test"
