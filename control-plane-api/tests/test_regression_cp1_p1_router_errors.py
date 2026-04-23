"""Regression guards for CP-1 P1 — router error mapping + path validation.

Closes:
- H.3 (HTTPException detail leaking str(e) with provider internals)
- H.4 (delete_file converted every exception into 404)
- H.5 (listing routes silently returning [] on provider failure)
- H.10 (missing path sanitization in _tenant_path)

Invariants pinned:
- FileNotFoundError is ONLY translated to an empty response on get_tree
  (and a raw 404 on get_file / delete_file). list_commits, list_branches
  and list_merge_requests surface provider failures as 502/504.
- HTTPException.detail never echoes the raw str(exc). Server log still
  carries exc_info=True; clients correlate via X-Request-ID response
  header.
- Path segments ``..``, backslash, absolute prefix, and any ASCII
  control character (0x00-0x1f + 0x7f) are rejected with 400.

regression for CP-1 H.3
regression for CP-1 H.4
regression for CP-1 H.5
regression for CP-1 H.10
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

_ADMIN_USER = MagicMock()
_ADMIN_USER.id = "admin-1"
_ADMIN_USER.email = "admin@gostoa.dev"
_ADMIN_USER.tenant_id = "acme"
_ADMIN_USER.roles = ["cpi-admin"]


def _build_app(mock_git=None):
    from src.auth.dependencies import get_current_user
    from src.routers.git import router
    from src.services.git_provider import get_git_provider

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    if mock_git is not None:
        app.dependency_overrides[get_git_provider] = lambda: mock_git
    return app


def _mock_git(**attrs):
    m = MagicMock()
    m.is_connected = MagicMock(return_value=True)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


BASE = "/v1/tenants/acme/git"

# Sentinels that should never leak into detail.
_SECRET_SHAPED = "token=ghp_SENSITIVE_ABC123 at https://api.github.com/repos/stoa/catalog"


# ──────────────────────────────────────────────────────────────────
# H.3 — no str(e) leak in HTTPException.detail
# ──────────────────────────────────────────────────────────────────


class TestNoExceptionLeakInDetail:
    def test_write_file_generic_detail_no_leak(self):
        """regression for CP-1 H.3"""
        mock_git = _mock_git(write_file=AsyncMock(side_effect=Exception(_SECRET_SHAPED)))
        client = TestClient(_build_app(mock_git))
        resp = client.post(f"{BASE}/files/new.yaml", json={"content": "x"})
        assert resp.status_code == 502
        assert _SECRET_SHAPED not in resp.text
        assert "ghp_SENSITIVE_ABC123" not in resp.text
        assert "api.github.com" not in resp.text

    def test_create_merge_request_generic_detail_no_leak(self):
        """regression for CP-1 H.3"""
        mock_git = _mock_git(create_merge_request=AsyncMock(side_effect=Exception(_SECRET_SHAPED)))
        client = TestClient(_build_app(mock_git))
        resp = client.post(
            f"{BASE}/merge-requests",
            json={
                "title": "T",
                "description": "D",
                "source_branch": "feat/x",
                "target_branch": "main",
            },
        )
        assert resp.status_code == 502
        assert _SECRET_SHAPED not in resp.text

    def test_merge_request_generic_detail_no_leak(self):
        """regression for CP-1 H.3"""
        mock_git = _mock_git(merge_merge_request=AsyncMock(side_effect=Exception(_SECRET_SHAPED)))
        client = TestClient(_build_app(mock_git))
        resp = client.post(f"{BASE}/merge-requests/1/merge")
        assert resp.status_code == 502
        assert _SECRET_SHAPED not in resp.text

    def test_create_branch_generic_detail_no_leak(self):
        """regression for CP-1 H.3"""
        mock_git = _mock_git(create_branch=AsyncMock(side_effect=Exception(_SECRET_SHAPED)))
        client = TestClient(_build_app(mock_git))
        resp = client.post(f"{BASE}/branches", json={"name": "feat/x", "ref": "main"})
        assert resp.status_code == 502
        assert _SECRET_SHAPED not in resp.text


# ──────────────────────────────────────────────────────────────────
# H.4 — delete_file error mapping
# ──────────────────────────────────────────────────────────────────


class TestDeleteFileErrorMapping:
    def test_missing_file_returns_404(self):
        """regression for CP-1 H.4"""
        mock_git = _mock_git(remove_file=AsyncMock(side_effect=FileNotFoundError("nope")))
        client = TestClient(_build_app(mock_git))
        resp = client.delete(f"{BASE}/files/nope.yaml")
        assert resp.status_code == 404

    def test_timeout_returns_504(self):
        """regression for CP-1 H.4"""
        mock_git = _mock_git(remove_file=AsyncMock(side_effect=TimeoutError("slow")))
        client = TestClient(_build_app(mock_git))
        resp = client.delete(f"{BASE}/files/valid.yaml")
        assert resp.status_code == 504
        assert "timeout" in resp.json()["detail"].lower()

    def test_provider_5xx_returns_502(self):
        """regression for CP-1 H.4"""
        mock_git = _mock_git(remove_file=AsyncMock(side_effect=Exception("GitHub 500")))
        client = TestClient(_build_app(mock_git))
        resp = client.delete(f"{BASE}/files/valid.yaml")
        assert resp.status_code == 502
        assert "GitHub 500" not in resp.text


# ──────────────────────────────────────────────────────────────────
# H.5 — listing routes surface provider failures instead of silent []
# ──────────────────────────────────────────────────────────────────


class TestListingsSurfaceProviderFailures:
    def test_list_commits_provider_5xx_returns_502(self):
        """regression for CP-1 H.5"""
        mock_git = _mock_git(list_path_commits=AsyncMock(side_effect=Exception("provider down")))
        client = TestClient(_build_app(mock_git))
        resp = client.get(f"{BASE}/commits")
        assert resp.status_code == 502

    def test_list_branches_timeout_returns_504(self):
        """regression for CP-1 H.5"""
        mock_git = _mock_git(list_branches=AsyncMock(side_effect=TimeoutError("slow")))
        client = TestClient(_build_app(mock_git))
        resp = client.get(f"{BASE}/branches")
        assert resp.status_code == 504

    def test_list_merge_requests_provider_5xx_returns_502(self):
        """regression for CP-1 H.5"""
        mock_git = _mock_git(list_merge_requests=AsyncMock(side_effect=Exception("provider down")))
        client = TestClient(_build_app(mock_git))
        resp = client.get(f"{BASE}/merge-requests")
        assert resp.status_code == 502

    def test_get_tree_file_not_found_returns_empty(self):
        """regression for CP-1 H.5 — get_tree is the ONLY listing that
        preserves FileNotFoundError → []. Other listings must not do the
        same or they reintroduce the false-empty bug."""
        mock_git = _mock_git(list_tree=AsyncMock(side_effect=FileNotFoundError("missing path")))
        client = TestClient(_build_app(mock_git))
        resp = client.get(f"{BASE}/tree")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_tree_provider_failure_returns_502(self):
        """regression for CP-1 H.5"""
        mock_git = _mock_git(list_tree=AsyncMock(side_effect=Exception("provider down")))
        client = TestClient(_build_app(mock_git))
        resp = client.get(f"{BASE}/tree")
        assert resp.status_code == 502


# ──────────────────────────────────────────────────────────────────
# H.10 — path sanitization
# ──────────────────────────────────────────────────────────────────


class TestPathSanitization:
    def test_parent_segment_rejected(self):
        """regression for CP-1 H.10"""
        mock_git = _mock_git(remove_file=AsyncMock())
        client = TestClient(_build_app(mock_git))
        resp = client.delete(f"{BASE}/files/..%2Fescape.yaml")
        assert resp.status_code == 400
        mock_git.remove_file.assert_not_awaited()

    def test_null_byte_rejected(self):
        """regression for CP-1 H.10"""
        mock_git = _mock_git(write_file=AsyncMock())
        client = TestClient(_build_app(mock_git))
        # %00 is a NUL byte; starlette URL-decodes path params.
        resp = client.post(f"{BASE}/files/evil%00.yaml", json={"content": "x"})
        assert resp.status_code == 400
        mock_git.write_file.assert_not_awaited()

    def test_other_control_chars_rejected_unit(self):
        """regression for CP-1 H.10 - validate_file_path unit check.

        HTTP layer mangles raw control chars (e.g. %0A bounces to 404 via
        starlette's routing quirks), so we exercise the validator itself
        to prove every ASCII control char 0x00-0x1f plus 0x7f rejects.
        """
        import pytest as _pytest
        from fastapi import HTTPException

        from src.routers.git import _validate_file_path

        for code in (*range(0x00, 0x20), 0x7F):
            bad = f"foo{chr(code)}bar.yaml"
            with _pytest.raises(HTTPException) as excinfo:
                _validate_file_path(bad)
            assert excinfo.value.status_code == 400, f"expected 400 for code {code:#04x}"

    def test_backslash_rejected(self):
        """regression for CP-1 H.10"""
        mock_git = _mock_git(write_file=AsyncMock())
        client = TestClient(_build_app(mock_git))
        resp = client.post(f"{BASE}/files/foo%5Cbar.yaml", json={"content": "x"})
        assert resp.status_code == 400
        mock_git.write_file.assert_not_awaited()

    def test_normal_nested_path_accepted(self):
        """regression for CP-1 H.10 — valid nested paths still pass."""
        mock_git = _mock_git(write_file=AsyncMock(return_value="created"))
        client = TestClient(_build_app(mock_git))
        resp = client.post(f"{BASE}/files/apis/foo/api.yaml", json={"content": "x"})
        assert resp.status_code == 201
        mock_git.write_file.assert_awaited_once()
