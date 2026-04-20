"""Regression test for CAB-2135: spec.tags and spec.category must survive
normalization of Kind=API manifests.

Prior to the fix, ``_normalize_api_data`` dropped both fields, which made
``catalog_sync_service._upsert_api`` compute ``portal_published=False`` for
every new-kind API (the promotion flag keys off the ``portal:published`` tag).
That in turn hid banking-demo/fapi-banking from
``GET /v1/internal/catalog/apis/expanded``.
"""

from unittest.mock import AsyncMock

from src.services.github_service import GitHubService


class TestRegressionCab2135ApiTagsCategoryNormalization:
    async def test_normalization_preserves_spec_tags_and_category(self):
        svc = GitHubService()
        svc.get_file_content = AsyncMock(return_value="""
apiVersion: gostoa.dev/v1
kind: API
metadata:
  name: fapi-banking
  version: 1.2.0
spec:
  displayName: FAPI Banking Demo
  description: Regulated EU banking demo API
  category: banking
  tags:
    - portal:published
    - banking
    - regulated-eu
  backend:
    url: http://banking-mock.demo-banking-mock.svc.cluster.local:8080
  deployments:
    dev: true
    staging: false
""")

        api = await svc.get_api("banking-demo", "fapi-banking")

        assert api["category"] == "banking"
        assert api["tags"] == ["portal:published", "banking", "regulated-eu"]

    async def test_normalization_defaults_tags_to_empty_list_when_absent(self):
        svc = GitHubService()
        svc.get_file_content = AsyncMock(return_value="""
apiVersion: gostoa.dev/v1
kind: API
metadata:
  name: no-tags-api
spec:
  displayName: No Tags API
  backend:
    url: https://example.com
""")

        api = await svc.get_api("demo", "no-tags-api")

        assert api["tags"] == []
        assert api["category"] is None
