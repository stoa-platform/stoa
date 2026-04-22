"""Tests for git router — provider-agnostic (CAB-1889 CP-1).

The router must talk only to the GitProvider interface. These tests mock the
interface methods (list_tree, write_file, list_merge_requests, ...) — they do
NOT mock provider internals like _project/_gh. That is the whole point of CP-1.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.git_provider import BranchRef, CommitRef, MergeRequestRef, TreeEntry

_ADMIN_USER = MagicMock()
_ADMIN_USER.id = "admin-1"
_ADMIN_USER.email = "admin@gostoa.dev"
_ADMIN_USER.tenant_id = "acme"
_ADMIN_USER.roles = ["cpi-admin"]

_VIEWER_USER = MagicMock()
_VIEWER_USER.id = "viewer-1"
_VIEWER_USER.email = "viewer@gostoa.dev"
_VIEWER_USER.tenant_id = "acme"
_VIEWER_USER.roles = ["viewer"]


def _build_test_app(user=None, mock_git=None):
    from src.routers.git import router
    from src.services.git_provider import get_git_provider

    app = FastAPI()
    app.include_router(router)

    if user is None:
        user = _ADMIN_USER

    async def override_get_current_user():
        return user

    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    if mock_git is not None:
        app.dependency_overrides[get_git_provider] = lambda: mock_git

    return app


def _make_mock_git(connected: bool = True, **attrs):
    """Return a MagicMock simulating a connected GitProvider by default."""
    m = MagicMock()
    m.is_connected = MagicMock(return_value=connected)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


TENANT = "acme"
BASE = f"/v1/tenants/{TENANT}/git"


# ---- Commits ----


def test_list_commits_empty():
    mock_git = _make_mock_git(list_path_commits=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_commits_with_data():
    mock_git = _make_mock_git(
        list_path_commits=AsyncMock(
            return_value=[CommitRef(sha="abc123", message="init", author="dev", date="2026-01-01T00:00:00")]
        )
    )
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["sha"] == "abc123"


def test_list_commits_with_path():
    mock_git = _make_mock_git(list_path_commits=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/commits?path=apis")
    assert resp.status_code == 200
    mock_git.list_path_commits.assert_called_once_with(path="tenants/acme/apis", limit=20)


# ---- Files ----


def test_get_file_success():
    mock_git = _make_mock_git(read_file=AsyncMock(return_value="file content here"))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/files/apis/test.yaml")
    assert resp.status_code == 200
    assert resp.json()["content"] == "file content here"
    mock_git.read_file.assert_called_once_with("tenants/acme/apis/test.yaml", ref="main")


def test_get_file_not_found():
    mock_git = _make_mock_git(read_file=AsyncMock(return_value=None))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/files/nonexistent.yaml")
    assert resp.status_code == 404


def test_create_file():
    mock_git = _make_mock_git(write_file=AsyncMock(return_value="created"))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/files/new.yaml", json={"content": "hello"})
    assert resp.status_code == 201
    assert resp.json()["action"] == "created"
    mock_git.write_file.assert_called_once()
    _, kwargs = mock_git.write_file.call_args
    assert kwargs == {"commit_message": "Update new.yaml for tenant acme", "branch": "main"}


def test_update_file():
    mock_git = _make_mock_git(write_file=AsyncMock(return_value="updated"))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/files/existing.yaml", json={"content": "new content"})
    assert resp.status_code == 201
    assert resp.json()["action"] == "updated"


def test_delete_file():
    mock_git = _make_mock_git(remove_file=AsyncMock(return_value=True))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.delete(f"{BASE}/files/old.yaml")
    assert resp.status_code == 200
    assert resp.json()["message"] == "File deleted"


# ---- Tree ----


def test_tree_success():
    mock_git = _make_mock_git(
        list_tree=AsyncMock(
            return_value=[
                TreeEntry(name="apis", type="tree", path="tenants/acme/apis"),
                TreeEntry(name="tenant.yaml", type="blob", path="tenants/acme/tenant.yaml"),
            ]
        )
    )
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/tree")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_tree_empty():
    mock_git = _make_mock_git(list_tree=AsyncMock(side_effect=Exception("not found")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/tree")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---- Merge Requests ----


def test_list_merge_requests_empty():
    mock_git = _make_mock_git(list_merge_requests=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 200
    assert resp.json() == []


def _mr_ref(**overrides):
    defaults = {
        "id": 1,
        "iid": 1,
        "title": "Test MR",
        "description": "desc",
        "state": "opened",
        "source_branch": "feat/x",
        "target_branch": "main",
        "web_url": "https://gitlab.com/mr/1",
        "created_at": "2026-01-01T00:00:00",
        "author": "dev",
    }
    defaults.update(overrides)
    return MergeRequestRef(**defaults)


def test_create_merge_request():
    mr = _mr_ref()
    mock_git = _make_mock_git(create_merge_request=AsyncMock(return_value=mr))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(
        f"{BASE}/merge-requests",
        json={
            "title": "Test MR",
            "description": "desc",
            "source_branch": "feat/x",
            "target_branch": "main",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "Test MR"


def test_merge_merge_request():
    mock_git = _make_mock_git(merge_merge_request=AsyncMock(return_value=_mr_ref(state="merged")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 200
    mock_git.merge_merge_request.assert_called_once_with(1)


# ---- Branches ----


def test_list_branches():
    mock_git = _make_mock_git(
        list_branches=AsyncMock(return_value=[BranchRef(name="main", commit_sha="abc123", protected=True)])
    )
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/branches")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "main"


def test_create_branch():
    mock_git = _make_mock_git(
        create_branch=AsyncMock(return_value=BranchRef(name="feat/new", commit_sha="def456", protected=False))
    )
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/branches", json={"name": "feat/new", "ref": "main"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "feat/new"
    mock_git.create_branch.assert_called_once_with(name="feat/new", ref="main")


# ---- RBAC ----


def test_viewer_can_read():
    mock_git = _make_mock_git(list_path_commits=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(user=_VIEWER_USER, mock_git=mock_git))
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200


def test_viewer_cannot_create_file():
    mock_git = _make_mock_git()
    client = TestClient(_build_test_app(user=_VIEWER_USER, mock_git=mock_git))
    resp = client.post(f"{BASE}/files/test.yaml", json={"content": "x"})
    assert resp.status_code == 403


def test_viewer_cannot_delete_file():
    mock_git = _make_mock_git()
    client = TestClient(_build_test_app(user=_VIEWER_USER, mock_git=mock_git))
    resp = client.delete(f"{BASE}/files/test.yaml")
    assert resp.status_code == 403


# ---- 503 when provider is not connected ----


def test_tree_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/tree")
    assert resp.status_code == 503
    assert "Git provider not connected" in resp.json()["detail"]


def test_create_file_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/files/new.yaml", json={"content": "x"})
    assert resp.status_code == 503


def test_delete_file_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.delete(f"{BASE}/files/old.yaml")
    assert resp.status_code == 503


def test_list_merge_requests_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 503


def test_create_merge_request_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(
        f"{BASE}/merge-requests",
        json={"title": "T", "description": "D", "source_branch": "feat/x", "target_branch": "main"},
    )
    assert resp.status_code == 503


def test_merge_request_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 503


def test_list_branches_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/branches")
    assert resp.status_code == 503


def test_create_branch_503_when_disconnected():
    mock_git = _make_mock_git(connected=False)
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/branches", json={"name": "feat/new", "ref": "main"})
    assert resp.status_code == 503


# ---- Exception / error fallback paths ----


def test_list_commits_exception_returns_empty():
    mock_git = _make_mock_git(list_path_commits=AsyncMock(side_effect=Exception("gitlab timeout")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_file_exception_returns_500():
    mock_git = _make_mock_git(write_file=AsyncMock(side_effect=Exception("write failed")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/files/new.yaml", json={"content": "x"})
    assert resp.status_code == 500
    assert "Failed to save file" in resp.json()["detail"]


def test_update_file_exception_returns_500():
    mock_git = _make_mock_git(write_file=AsyncMock(side_effect=Exception("save failed")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/files/existing.yaml", json={"content": "new"})
    assert resp.status_code == 500


def test_delete_file_exception_returns_404():
    mock_git = _make_mock_git(remove_file=AsyncMock(side_effect=Exception("not found")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.delete(f"{BASE}/files/missing.yaml")
    assert resp.status_code == 404
    assert "File not found" in resp.json()["detail"]


def test_list_merge_requests_exception_returns_empty():
    mock_git = _make_mock_git(list_merge_requests=AsyncMock(side_effect=Exception("gitlab error")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_merge_request_exception_returns_500():
    mock_git = _make_mock_git(create_merge_request=AsyncMock(side_effect=Exception("create failed")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(
        f"{BASE}/merge-requests",
        json={"title": "T", "description": "D", "source_branch": "feat/x", "target_branch": "main"},
    )
    assert resp.status_code == 500
    assert "Failed to create merge request" in resp.json()["detail"]


def test_merge_merge_request_exception_returns_500():
    mock_git = _make_mock_git(merge_merge_request=AsyncMock(side_effect=Exception("merge failed")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 500
    assert "Failed to merge" in resp.json()["detail"]


def test_list_branches_exception_returns_empty():
    mock_git = _make_mock_git(list_branches=AsyncMock(side_effect=Exception("gitlab error")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/branches")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_branch_exception_returns_500():
    mock_git = _make_mock_git(create_branch=AsyncMock(side_effect=Exception("create failed")))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/branches", json={"name": "feat/err", "ref": "main"})
    assert resp.status_code == 500
    assert "Failed to create branch" in resp.json()["detail"]


# ---- Additional edge cases ----


def test_list_commits_with_custom_limit():
    mock_git = _make_mock_git(list_path_commits=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/commits?limit=50")
    assert resp.status_code == 200
    mock_git.list_path_commits.assert_called_once_with(path="tenants/acme", limit=50)


def test_list_merge_requests_with_data():
    mr = _mr_ref(
        id=10,
        iid=5,
        title="Fix bug",
        description="",
        state="merged",
        source_branch="fix/bug",
        web_url="https://gitlab.com/mr/5",
        created_at="2026-01-15T00:00:00",
        author="dev-string",
    )
    mock_git = _make_mock_git(list_merge_requests=AsyncMock(return_value=[mr]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["description"] == ""
    assert data[0]["author"] == "dev-string"


def test_create_file_with_custom_commit_message():
    mock_git = _make_mock_git(write_file=AsyncMock(return_value="created"))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/files/new.yaml?commit_message=custom+msg", json={"content": "data"})
    assert resp.status_code == 201
    _, kwargs = mock_git.write_file.call_args
    assert kwargs["commit_message"] == "custom msg"


def test_get_tree_with_path_param():
    mock_git = _make_mock_git(list_tree=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/tree?path=apis")
    assert resp.status_code == 200
    mock_git.list_tree.assert_called_once_with("tenants/acme/apis", ref="main")


def test_viewer_cannot_create_branch():
    mock_git = _make_mock_git()
    client = TestClient(_build_test_app(user=_VIEWER_USER, mock_git=mock_git))
    resp = client.post(f"{BASE}/branches", json={"name": "feat/x", "ref": "main"})
    assert resp.status_code == 403


def test_viewer_cannot_create_merge_request():
    mock_git = _make_mock_git()
    client = TestClient(_build_test_app(user=_VIEWER_USER, mock_git=mock_git))
    resp = client.post(
        f"{BASE}/merge-requests",
        json={"title": "T", "description": "D", "source_branch": "feat/x", "target_branch": "main"},
    )
    assert resp.status_code == 403


def test_viewer_cannot_merge_request():
    mock_git = _make_mock_git()
    client = TestClient(_build_test_app(user=_VIEWER_USER, mock_git=mock_git))
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 403


# ---- GitHub-style PR mapped as merge request (iid ← pr_number) ----


def test_merge_merge_request_maps_iid_for_github():
    """Router passes mr_iid unchanged — GitHubService translates iid → pr.number internally.

    This regression-guards the interface contract: routers speak in iid terms.
    """
    merged = _mr_ref(id=99, iid=42, state="merged", web_url="https://github.com/org/repo/pull/42")
    mock_git = _make_mock_git(merge_merge_request=AsyncMock(return_value=merged))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.post(f"{BASE}/merge-requests/42/merge")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Merge request merged", "iid": 42}
    mock_git.merge_merge_request.assert_called_once_with(42)


def test_router_does_not_touch_provider_internals():
    """CP-1 metric: the router must never access _project or _gh.

    Regression guard — if someone reintroduces a ``git._project`` / ``git._gh``
    access in the router, this test fails loudly.
    """
    import inspect

    from src.routers import git as git_router

    source = inspect.getsource(git_router)
    forbidden = ["._project", "._gh ", "._gh.", "._gh)", "._repo", "_internal"]
    for token in forbidden:
        assert token not in source, f"Router leaks provider internal: {token!r} found"


def test_list_merge_requests_filters_by_state():
    """Router forwards ?state= to provider.list_merge_requests verbatim."""
    mock_git = _make_mock_git(list_merge_requests=AsyncMock(return_value=[]))
    client = TestClient(_build_test_app(mock_git=mock_git))
    resp = client.get(f"{BASE}/merge-requests?state=merged")
    assert resp.status_code == 200
    mock_git.list_merge_requests.assert_called_once_with(state="merged")
