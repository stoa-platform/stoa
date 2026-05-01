import pytest

from src.services.gitops_writer.backfill import GitOpsCatalogBackfill
from tests.services._fakes import InMemoryCatalogGitClient
from tests.services.gitops_writer.test_backfill_unit import _row


@pytest.mark.asyncio
async def test_regression_gitops_backfill_creates_canonical_api_yaml_for_legacy_db_api() -> None:
    fake_git = InMemoryCatalogGitClient()
    backfill = GitOpsCatalogBackfill(catalog_git_client=fake_git, db_session=None)  # type: ignore[arg-type]

    result = await backfill.backfill_row(_row(tenant_id="__all__", api_id="demo-petstore"), dry_run=True)

    assert result.status == "dry_run_would_create"
    assert result.git_path == "tenants/__all__/apis/demo-petstore/api.yaml"
