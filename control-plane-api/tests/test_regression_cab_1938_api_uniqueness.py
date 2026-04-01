"""Regression test for CAB-1938: API uniqueness on (tenant_id, api_name, version) with slug api_id.

Ticket: CAB-1938
Root cause: Old unique constraint was on (tenant_id, api_id) without version awareness.
  Two APIs with the same name but different versions would conflict. Soft-deleted APIs
  blocked re-creation of the same name.
Invariant:
  - Same (name, version) in same tenant → 409
  - Same name, different version → OK
  - api_id is auto-generated slug from name
"""

class TestSlugify:
    """Unit tests for _slugify helper."""

    def test_simple_name(self):
        from src.routers.apis import _slugify
        assert _slugify("My Cool API") == "my-cool-api"

    def test_special_characters(self):
        from src.routers.apis import _slugify
        assert _slugify("API@v2.0 (beta)") == "apiv20-beta"

    def test_multiple_spaces_and_hyphens(self):
        from src.routers.apis import _slugify
        assert _slugify("my  --  api") == "my-api"

    def test_leading_trailing_whitespace(self):
        from src.routers.apis import _slugify
        assert _slugify("  hello world  ") == "hello-world"

    def test_empty_string_fallback(self):
        from src.routers.apis import _slugify
        assert _slugify("!!!") == "api"

    def test_already_slug(self):
        from src.routers.apis import _slugify
        assert _slugify("my-api") == "my-api"

    def test_uppercase(self):
        from src.routers.apis import _slugify
        assert _slugify("Payment Gateway") == "payment-gateway"


class TestApiFromCatalogDisplayName:
    """Ensure _api_from_catalog reads display_name from metadata."""

    def test_display_name_from_metadata(self):
        from unittest.mock import MagicMock

        from src.routers.apis import _api_from_catalog

        api = MagicMock()
        api.api_id = "my-api"
        api.tenant_id = "tenant-1"
        api.api_name = "my-api"
        api.version = "1.0.0"
        api.status = "draft"
        api.tags = []
        api.api_metadata = {
            "display_name": "My Pretty API",
            "description": "desc",
            "backend_url": "http://backend",
            "deployments": {},
        }

        result = _api_from_catalog(api)
        assert result.display_name == "My Pretty API"

    def test_display_name_fallback_to_api_name(self):
        from unittest.mock import MagicMock

        from src.routers.apis import _api_from_catalog

        api = MagicMock()
        api.api_id = "my-api"
        api.tenant_id = "tenant-1"
        api.api_name = "my-api"
        api.version = "1.0.0"
        api.status = "draft"
        api.tags = []
        api.api_metadata = {"description": "", "backend_url": "", "deployments": {}}

        result = _api_from_catalog(api)
        assert result.display_name == "my-api"
