import pytest
import yaml

from src.models.catalog import APICatalog
from src.services.gitops_writer.backfill import GitOpsCatalogBackfill, _render_row_api_yaml
from tests.services._fakes import InMemoryCatalogGitClient


def _row(**overrides) -> APICatalog:
    defaults = {
        "tenant_id": "demo",
        "api_id": "petstore",
        "api_name": "Petstore",
        "version": "1.0.0",
        "status": "draft",
        "tags": ["demo"],
        "portal_published": False,
        "audience": "public",
        "api_metadata": {
            "display_name": "Petstore",
            "description": "Demo API",
            "backend_url": "https://petstore.example",
            "deployments": {"dev": True, "staging": False},
        },
        "openapi_spec": None,
        "target_gateways": [],
        "git_path": None,
        "git_commit_sha": None,
        "catalog_content_hash": None,
    }
    defaults.update(overrides)
    return APICatalog(**defaults)


def test_render_row_api_yaml_preserves_console_fields() -> None:
    parsed = yaml.safe_load(_render_row_api_yaml(_row()))

    assert parsed["id"] == "petstore"
    assert parsed["name"] == "petstore"
    assert parsed["display_name"] == "Petstore"
    assert parsed["backend_url"] == "https://petstore.example"
    assert parsed["status"] == "draft"
    assert parsed["deployments"] == {"dev": True, "staging": False}


def test_render_row_api_yaml_uses_openapi_server_fallback() -> None:
    parsed = yaml.safe_load(
        _render_row_api_yaml(
            _row(
                api_metadata={"display_name": "Petstore"},
                openapi_spec={"servers": [{"url": "https://from-openapi.example"}]},
            )
        )
    )

    assert parsed["backend_url"] == "https://from-openapi.example"


def test_render_row_api_yaml_requires_backend_url() -> None:
    with pytest.raises(ValueError, match="missing backend_url"):
        _render_row_api_yaml(_row(api_metadata={}, openapi_spec=None))


@pytest.mark.asyncio
async def test_backfill_dry_run_reports_would_create_for_pre_gitops_row() -> None:
    fake_git = InMemoryCatalogGitClient()
    backfill = GitOpsCatalogBackfill(catalog_git_client=fake_git, db_session=None)  # type: ignore[arg-type]

    result = await backfill.backfill_row(_row(), dry_run=True)

    assert result.status == "dry_run_would_create"
    assert result.git_path == "tenants/demo/apis/petstore/api.yaml"


@pytest.mark.asyncio
async def test_backfill_dry_run_skips_uuid_hard_drift() -> None:
    fake_git = InMemoryCatalogGitClient()
    backfill = GitOpsCatalogBackfill(catalog_git_client=fake_git, db_session=None)  # type: ignore[arg-type]

    result = await backfill.backfill_row(
        _row(api_id="00000000-0000-0000-0000-000000000000"),
        dry_run=True,
    )

    assert result.status == "skipped_uuid_hard_drift"
