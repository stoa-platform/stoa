"""Tests for git router — GitLab-backed operations."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _build_test_app(user=None):
    from src.routers.git import router

    app = FastAPI()
    app.include_router(router)

    if user is None:
        user = _ADMIN_USER

    async def override_get_current_user():
        return user

    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return app


TENANT = "acme"
BASE = f"/v1/tenants/{TENANT}/git"


# ---- Commits ----


@patch("src.routers.git.git_service")
def test_list_commits_empty(mock_git):
    mock_git.list_commits = AsyncMock(return_value=[])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("src.routers.git.git_service")
def test_list_commits_with_data(mock_git):
    mock_git.list_commits = AsyncMock(
        return_value=[{"sha": "abc123", "message": "init", "author": "dev", "date": "2026-01-01T00:00:00"}]
    )
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["sha"] == "abc123"


@patch("src.routers.git.git_service")
def test_list_commits_with_path(mock_git):
    mock_git.list_commits = AsyncMock(return_value=[])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/commits?path=apis")
    assert resp.status_code == 200
    mock_git.list_commits.assert_called_once_with(path="tenants/acme/apis", limit=20)


# ---- Files ----


@patch("src.routers.git.git_service")
def test_get_file_success(mock_git):
    mock_git.get_file = AsyncMock(return_value="file content here")
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/files/apis/test.yaml")
    assert resp.status_code == 200
    assert resp.json()["content"] == "file content here"
    mock_git.get_file.assert_called_once_with("tenants/acme/apis/test.yaml", ref="main")


@patch("src.routers.git.git_service")
def test_get_file_not_found(mock_git):
    mock_git.get_file = AsyncMock(return_value=None)
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/files/nonexistent.yaml")
    assert resp.status_code == 404


@patch("src.routers.git.git_service")
def test_create_file(mock_git):
    mock_git._project = MagicMock()
    mock_git.get_file = AsyncMock(return_value=None)  # file doesn't exist
    mock_git._project.files.create = MagicMock()
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/files/new.yaml", json={"content": "hello"})
    assert resp.status_code == 201
    assert resp.json()["action"] == "created"


@patch("src.routers.git.git_service")
def test_update_file(mock_git):
    mock_git._project = MagicMock()
    mock_git.get_file = AsyncMock(return_value="old content")  # file exists
    file_obj = MagicMock()
    mock_git._project.files.get = MagicMock(return_value=file_obj)
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/files/existing.yaml", json={"content": "new content"})
    assert resp.status_code == 201
    assert resp.json()["action"] == "updated"


@patch("src.routers.git.git_service")
def test_delete_file(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.files.delete = MagicMock()
    client = TestClient(_build_test_app())
    resp = client.delete(f"{BASE}/files/old.yaml")
    assert resp.status_code == 200
    assert resp.json()["message"] == "File deleted"


# ---- Tree ----


@patch("src.routers.git.git_service")
def test_tree_success(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.repository_tree = MagicMock(
        return_value=[
            {"name": "apis", "type": "tree", "path": "tenants/acme/apis"},
            {"name": "tenant.yaml", "type": "blob", "path": "tenants/acme/tenant.yaml"},
        ]
    )
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/tree")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@patch("src.routers.git.git_service")
def test_tree_empty(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.repository_tree = MagicMock(side_effect=Exception("not found"))
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/tree")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---- Merge Requests ----


@patch("src.routers.git.git_service")
def test_list_merge_requests_empty(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.mergerequests.list = MagicMock(return_value=[])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("src.routers.git.git_service")
def test_create_merge_request(mock_git):
    mock_git._project = MagicMock()
    mr_mock = MagicMock()
    mr_mock.id = 1
    mr_mock.iid = 1
    mr_mock.title = "Test MR"
    mr_mock.description = "desc"
    mr_mock.state = "opened"
    mr_mock.source_branch = "feat/x"
    mr_mock.target_branch = "main"
    mr_mock.web_url = "https://gitlab.com/mr/1"
    mr_mock.created_at = "2026-01-01T00:00:00"
    mr_mock.author = {"name": "dev"}
    mock_git._project.mergerequests.create = MagicMock(return_value=mr_mock)
    client = TestClient(_build_test_app())
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


@patch("src.routers.git.git_service")
def test_merge_merge_request(mock_git):
    mock_git._project = MagicMock()
    mr_mock = MagicMock()
    mock_git._project.mergerequests.get = MagicMock(return_value=mr_mock)
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 200
    mr_mock.merge.assert_called_once()


# ---- Branches ----


@patch("src.routers.git.git_service")
def test_list_branches(mock_git):
    mock_git._project = MagicMock()
    branch_mock = MagicMock()
    branch_mock.name = "main"
    branch_mock.commit = {"id": "abc123"}
    branch_mock.protected = True
    mock_git._project.branches.list = MagicMock(return_value=[branch_mock])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/branches")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "main"


@patch("src.routers.git.git_service")
def test_create_branch(mock_git):
    mock_git._project = MagicMock()
    branch_mock = MagicMock()
    branch_mock.name = "feat/new"
    branch_mock.commit = {"id": "def456"}
    branch_mock.protected = False
    mock_git._project.branches.create = MagicMock(return_value=branch_mock)
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/branches", json={"name": "feat/new", "ref": "main"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "feat/new"


# ---- RBAC ----


@patch("src.routers.git.git_service")
def test_viewer_can_read(mock_git):
    mock_git.list_commits = AsyncMock(return_value=[])
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200


@patch("src.routers.git.git_service")
def test_viewer_cannot_create_file(mock_git):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.post(f"{BASE}/files/test.yaml", json={"content": "x"})
    assert resp.status_code == 403


@patch("src.routers.git.git_service")
def test_viewer_cannot_delete_file(mock_git):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.delete(f"{BASE}/files/test.yaml")
    assert resp.status_code == 403


# ---- 503 when _project is None ----


@patch("src.routers.git.git_service")
def test_tree_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/tree")
    assert resp.status_code == 503
    assert "GitLab not connected" in resp.json()["detail"]


@patch("src.routers.git.git_service")
def test_create_file_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/files/new.yaml", json={"content": "x"})
    assert resp.status_code == 503


@patch("src.routers.git.git_service")
def test_delete_file_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.delete(f"{BASE}/files/old.yaml")
    assert resp.status_code == 503


@patch("src.routers.git.git_service")
def test_list_merge_requests_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 503


@patch("src.routers.git.git_service")
def test_create_merge_request_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.post(
        f"{BASE}/merge-requests",
        json={"title": "T", "description": "D", "source_branch": "feat/x", "target_branch": "main"},
    )
    assert resp.status_code == 503


@patch("src.routers.git.git_service")
def test_merge_request_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 503


@patch("src.routers.git.git_service")
def test_list_branches_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/branches")
    assert resp.status_code == 503


@patch("src.routers.git.git_service")
def test_create_branch_503_when_project_none(mock_git):
    mock_git._project = None
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/branches", json={"name": "feat/new", "ref": "main"})
    assert resp.status_code == 503


# ---- Exception / error fallback paths ----


@patch("src.routers.git.git_service")
def test_list_commits_exception_returns_empty(mock_git):
    mock_git.list_commits = AsyncMock(side_effect=Exception("gitlab timeout"))
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/commits")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("src.routers.git.git_service")
def test_create_file_exception_returns_500(mock_git):
    mock_git._project = MagicMock()
    mock_git.get_file = AsyncMock(return_value=None)
    mock_git._project.files.create = MagicMock(side_effect=Exception("write failed"))
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/files/new.yaml", json={"content": "x"})
    assert resp.status_code == 500
    assert "Failed to save file" in resp.json()["detail"]


@patch("src.routers.git.git_service")
def test_update_file_exception_returns_500(mock_git):
    mock_git._project = MagicMock()
    mock_git.get_file = AsyncMock(return_value="old content")
    file_obj = MagicMock()
    file_obj.save = MagicMock(side_effect=Exception("save failed"))
    mock_git._project.files.get = MagicMock(return_value=file_obj)
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/files/existing.yaml", json={"content": "new"})
    assert resp.status_code == 500


@patch("src.routers.git.git_service")
def test_delete_file_exception_returns_404(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.files.delete = MagicMock(side_effect=Exception("not found"))
    client = TestClient(_build_test_app())
    resp = client.delete(f"{BASE}/files/missing.yaml")
    assert resp.status_code == 404
    assert "File not found" in resp.json()["detail"]


@patch("src.routers.git.git_service")
def test_list_merge_requests_exception_returns_empty(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.mergerequests.list = MagicMock(side_effect=Exception("gitlab error"))
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("src.routers.git.git_service")
def test_create_merge_request_exception_returns_500(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.mergerequests.create = MagicMock(side_effect=Exception("create failed"))
    client = TestClient(_build_test_app())
    resp = client.post(
        f"{BASE}/merge-requests",
        json={"title": "T", "description": "D", "source_branch": "feat/x", "target_branch": "main"},
    )
    assert resp.status_code == 500
    assert "Failed to create merge request" in resp.json()["detail"]


@patch("src.routers.git.git_service")
def test_merge_merge_request_exception_returns_500(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.mergerequests.get = MagicMock(side_effect=Exception("merge failed"))
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 500
    assert "Failed to merge" in resp.json()["detail"]


@patch("src.routers.git.git_service")
def test_list_branches_exception_returns_empty(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.branches.list = MagicMock(side_effect=Exception("gitlab error"))
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/branches")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("src.routers.git.git_service")
def test_create_branch_exception_returns_500(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.branches.create = MagicMock(side_effect=Exception("create failed"))
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/branches", json={"name": "feat/err", "ref": "main"})
    assert resp.status_code == 500
    assert "Failed to create branch" in resp.json()["detail"]


# ---- Additional edge cases ----


@patch("src.routers.git.git_service")
def test_list_commits_with_custom_limit(mock_git):
    mock_git.list_commits = AsyncMock(return_value=[])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/commits?limit=50")
    assert resp.status_code == 200
    mock_git.list_commits.assert_called_once_with(path="tenants/acme", limit=50)


@patch("src.routers.git.git_service")
def test_list_merge_requests_with_data(mock_git):
    mock_git._project = MagicMock()
    mr_mock = MagicMock()
    mr_mock.id = 10
    mr_mock.iid = 5
    mr_mock.title = "Fix bug"
    mr_mock.description = None  # test None description
    mr_mock.state = "merged"
    mr_mock.source_branch = "fix/bug"
    mr_mock.target_branch = "main"
    mr_mock.web_url = "https://gitlab.com/mr/5"
    mr_mock.created_at = "2026-01-15T00:00:00"
    mr_mock.author = "dev-string"  # test non-dict author
    mock_git._project.mergerequests.list = MagicMock(return_value=[mr_mock])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/merge-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["description"] == ""
    assert data[0]["author"] == "dev-string"


@patch("src.routers.git.git_service")
def test_create_file_with_custom_commit_message(mock_git):
    mock_git._project = MagicMock()
    mock_git.get_file = AsyncMock(return_value=None)
    mock_git._project.files.create = MagicMock()
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/files/new.yaml?commit_message=custom+msg", json={"content": "data"})
    assert resp.status_code == 201


@patch("src.routers.git.git_service")
def test_get_tree_with_path_param(mock_git):
    mock_git._project = MagicMock()
    mock_git._project.repository_tree = MagicMock(return_value=[])
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/tree?path=apis")
    assert resp.status_code == 200
    mock_git._project.repository_tree.assert_called_once_with(path="tenants/acme/apis", ref="main")


@patch("src.routers.git.git_service")
def test_viewer_cannot_create_branch(mock_git):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.post(f"{BASE}/branches", json={"name": "feat/x", "ref": "main"})
    assert resp.status_code == 403


@patch("src.routers.git.git_service")
def test_viewer_cannot_create_merge_request(mock_git):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.post(
        f"{BASE}/merge-requests",
        json={"title": "T", "description": "D", "source_branch": "feat/x", "target_branch": "main"},
    )
    assert resp.status_code == 403


@patch("src.routers.git.git_service")
def test_viewer_cannot_merge_request(mock_git):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.post(f"{BASE}/merge-requests/1/merge")
    assert resp.status_code == 403
