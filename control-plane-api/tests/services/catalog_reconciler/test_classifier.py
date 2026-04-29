"""Tests for ``classify_legacy``.

Spec §6.14 + §11.1 audit-informed (CAB-2188 B12, CAB-2193 B14).

Fixtures based on the audit B14 verdict (executed 2026-04-27):

* 5 ``demo`` cat A: ``account-management-api``, ``customer-360-api``,
  ``fraud-detection-api``, ``payment-api``, ``petstore``
* 7 ``demo`` cat B: ``demo-api2``, ``test``, ``test2``, ``test3``, ``test5``,
  ``toto-api``, ``toto2`` (UUID drift uniform — both ``api_id`` and ``git_path``
  UUID-shaped)
* 1 ``demo`` cat C: ``banking-services-v1-2`` (Git file absent)
* 13 ``demo``/``oasis`` cat D rows (git_path NULL + git_commit_sha NULL)
"""

from __future__ import annotations

from typing import Any

import pytest

from src.services.catalog_reconciler.classifier import LegacyCategory, classify_legacy

_VALID_UUID = "12345678-1234-1234-1234-123456789012"


def _row(
    *,
    api_id: str,
    git_path: str | None,
    git_commit_sha: str | None,
    catalog_content_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "api_id": api_id,
        "git_path": git_path,
        "git_commit_sha": git_commit_sha,
        "catalog_content_hash": catalog_content_hash,
    }


class TestClassifyLegacy:
    @pytest.mark.asyncio
    async def test_absent_when_no_row(self) -> None:
        assert await classify_legacy(actual_row=None, git_file_exists=False) == LegacyCategory.ABSENT
        assert await classify_legacy(actual_row=None, git_file_exists=True) == LegacyCategory.ABSENT

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "api_name",
        [
            "account-management-api",
            "customer-360-api",
            "fraud-detection-api",
            "payment-api",
            "petstore",
        ],
    )
    async def test_healthy_adoptable_5_demo_apis(self, api_name: str) -> None:
        row = _row(
            api_id=api_name,
            git_path=f"tenants/demo/apis/{api_name}/api.yaml",
            git_commit_sha="a" * 40,
        )
        assert await classify_legacy(actual_row=row, git_file_exists=True) == LegacyCategory.HEALTHY_ADOPTABLE

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "api_name",
        ["demo-api2", "test", "test2", "test3", "test5", "toto-api", "toto2"],
    )
    async def test_uuid_hard_drift_7_demo_apis(self, api_name: str) -> None:
        # Audit B14 §11.1: both api_id and git_path are UUID-shaped on cat B.
        row = _row(
            api_id=_VALID_UUID,
            git_path=f"tenants/demo/apis/{_VALID_UUID}/api.yaml",
            git_commit_sha="a" * 40,
        )
        assert await classify_legacy(actual_row=row, git_file_exists=True) == LegacyCategory.UUID_HARD_DRIFT

    @pytest.mark.asyncio
    async def test_orphan_db_banking_services(self) -> None:
        row = _row(
            api_id="banking-services-v1-2",
            git_path="tenants/demo/apis/banking-services-v1-2/api.yaml",
            git_commit_sha="a" * 40,
        )
        assert await classify_legacy(actual_row=row, git_file_exists=False) == LegacyCategory.ORPHAN_DB

    @pytest.mark.asyncio
    async def test_pre_gitops_db_only(self) -> None:
        row = _row(api_id="legacy-api", git_path=None, git_commit_sha=None)
        assert await classify_legacy(actual_row=row, git_file_exists=False) == LegacyCategory.PRE_GITOPS
        # Even if a Git file exists at canonical path, NULL pointers means D
        # (the row hasn't been bound yet).
        assert await classify_legacy(actual_row=row, git_file_exists=True) == LegacyCategory.PRE_GITOPS

    @pytest.mark.asyncio
    async def test_gitops_created_with_hash(self) -> None:
        row = _row(
            api_id="petstore",
            git_path="tenants/demo-gitops/apis/petstore/api.yaml",
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
        )
        assert await classify_legacy(actual_row=row, git_file_exists=True) == LegacyCategory.GITOPS_CREATED

    @pytest.mark.asyncio
    async def test_uuid_in_api_id_only_still_b(self) -> None:
        # api_id UUID + git_path canonical → still B (UUID dominates)
        row = _row(
            api_id=_VALID_UUID,
            git_path="tenants/demo/apis/petstore/api.yaml",
            git_commit_sha="a" * 40,
        )
        assert await classify_legacy(actual_row=row, git_file_exists=True) == LegacyCategory.UUID_HARD_DRIFT

    @pytest.mark.asyncio
    async def test_uuid_in_git_path_only_still_b(self) -> None:
        # api_id slug + git_path UUID-shaped → still B
        row = _row(
            api_id="petstore",
            git_path=f"tenants/demo/apis/{_VALID_UUID}/api.yaml",
            git_commit_sha="a" * 40,
        )
        assert await classify_legacy(actual_row=row, git_file_exists=True) == LegacyCategory.UUID_HARD_DRIFT

    @pytest.mark.asyncio
    async def test_categories_string_values_stable(self) -> None:
        # These string values feed api_sync_status.last_error and metrics; they
        # must remain stable across implementations.
        assert LegacyCategory.HEALTHY_ADOPTABLE.value == "A"
        assert LegacyCategory.UUID_HARD_DRIFT.value == "B"
        assert LegacyCategory.ORPHAN_DB.value == "C"
        assert LegacyCategory.PRE_GITOPS.value == "D"
        assert LegacyCategory.GITOPS_CREATED.value == "gitops_created"
        assert LegacyCategory.ABSENT.value == "absent"

    @pytest.mark.asyncio
    async def test_categories_mutually_exclusive_for_audit_fixtures(self) -> None:
        """Sanity sweep over the 6 audit fixtures — exactly one category each."""
        cases: list[tuple[dict[str, Any] | None, bool, LegacyCategory]] = [
            (None, False, LegacyCategory.ABSENT),
            (
                _row(
                    api_id="petstore",
                    git_path="tenants/demo/apis/petstore/api.yaml",
                    git_commit_sha="a" * 40,
                ),
                True,
                LegacyCategory.HEALTHY_ADOPTABLE,
            ),
            (
                _row(
                    api_id=_VALID_UUID,
                    git_path=f"tenants/demo/apis/{_VALID_UUID}/api.yaml",
                    git_commit_sha="a" * 40,
                ),
                True,
                LegacyCategory.UUID_HARD_DRIFT,
            ),
            (
                _row(
                    api_id="banking-services-v1-2",
                    git_path="tenants/demo/apis/banking-services-v1-2/api.yaml",
                    git_commit_sha="a" * 40,
                ),
                False,
                LegacyCategory.ORPHAN_DB,
            ),
            (
                _row(api_id="legacy-api", git_path=None, git_commit_sha=None),
                False,
                LegacyCategory.PRE_GITOPS,
            ),
            (
                _row(
                    api_id="petstore",
                    git_path="tenants/demo-gitops/apis/petstore/api.yaml",
                    git_commit_sha="a" * 40,
                    catalog_content_hash="b" * 64,
                ),
                True,
                LegacyCategory.GITOPS_CREATED,
            ),
        ]
        for row, file_exists, expected in cases:
            assert await classify_legacy(actual_row=row, git_file_exists=file_exists) == expected
