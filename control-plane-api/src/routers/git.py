"""Git router - provider-agnostic GitOps operations (CAB-1890, CAB-1889 CP-1)."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..services.git_provider import GitProvider, get_git_provider, git_provider_factory


class TreeItem(BaseModel):
    name: str
    type: str
    path: str


class TreeListResponse(BaseModel):
    items: list[TreeItem]


class FileContentResponse(BaseModel):
    items: list[dict]


class FileActionResponse(BaseModel):
    path: str
    action: str


class MessageResponse(BaseModel):
    message: str


class MergeResultResponse(BaseModel):
    message: str
    iid: int


logger = logging.getLogger(__name__)

# Backward-compat shim for test patching (see conftest.py _git_di_bridge)
git_service = git_provider_factory()

router = APIRouter(prefix="/v1/tenants/{tenant_id}/git", tags=["Advanced — GitOps"])


class CommitInfo(BaseModel):
    sha: str
    message: str
    author: str
    date: str


class FileContent(BaseModel):
    path: str
    content: str
    encoding: str = "text"  # text or base64


class FileCreateUpdate(BaseModel):
    content: str
    encoding: str = "text"


class MergeRequestCreate(BaseModel):
    title: str
    description: str
    source_branch: str
    target_branch: str = "main"


class MergeRequestResponse(BaseModel):
    id: int
    iid: int
    title: str
    description: str
    state: str
    source_branch: str
    target_branch: str
    web_url: str
    created_at: str
    author: str


class BranchInfo(BaseModel):
    name: str
    commit_sha: str
    protected: bool = False


class BranchCreate(BaseModel):
    name: str
    ref: str = "main"


def _tenant_path(tenant_id: str, path: str = "") -> str:
    """Build scoped path under the tenant directory."""
    base = f"tenants/{tenant_id}"
    return f"{base}/{path}" if path else base


def _require_connected(git: GitProvider) -> None:
    if not git.is_connected():
        raise HTTPException(status_code=503, detail="Git provider not connected")


@router.get("/commits", response_model=list[CommitInfo])
@require_tenant_access
async def list_commits(
    tenant_id: str,
    path: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """List recent commits for tenant repository"""
    scoped_path = _tenant_path(tenant_id, path) if path else _tenant_path(tenant_id)
    try:
        commits = await git.list_path_commits(path=scoped_path, limit=limit)
        return [CommitInfo(**asdict(c)) for c in commits]
    except Exception as e:
        logger.error(f"Failed to list commits for tenant {tenant_id}: {e}")
        return []


@router.get("/files/{file_path:path}", response_model=FileContent)
@require_tenant_access
async def get_file(
    tenant_id: str,
    file_path: str,
    ref: str = "main",
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Get file content from git provider"""
    scoped_path = _tenant_path(tenant_id, file_path)
    content = await git.read_file(scoped_path, ref=ref)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileContent(path=file_path, content=content)


@router.get("/tree", response_model=TreeListResponse)
@require_tenant_access
async def get_tree(
    tenant_id: str,
    path: str = "",
    ref: str = "main",
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Get directory tree from git provider"""
    _require_connected(git)
    scoped_path = _tenant_path(tenant_id, path) if path else _tenant_path(tenant_id)
    try:
        entries = await git.list_tree(scoped_path, ref=ref)
        return TreeListResponse(items=[TreeItem(**asdict(e)) for e in entries])
    except Exception:
        return TreeListResponse(items=[])


@router.post("/files/{file_path:path}", status_code=201, response_model=FileActionResponse)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def create_or_update_file(
    tenant_id: str,
    file_path: str,
    body: FileCreateUpdate,
    branch: str = Query(default="main"),
    commit_message: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Create or update a file in git provider"""
    _require_connected(git)
    scoped_path = _tenant_path(tenant_id, file_path)
    msg = commit_message or f"Update {file_path} for tenant {tenant_id}"

    try:
        action = await git.write_file(scoped_path, body.content, commit_message=msg, branch=branch)
    except Exception as e:
        logger.error(f"Failed to create/update file {scoped_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    return {"path": file_path, "action": action}


@router.delete("/files/{file_path:path}", response_model=MessageResponse)
@require_permission(Permission.APIS_DELETE)
@require_tenant_access
async def delete_file(
    tenant_id: str,
    file_path: str,
    branch: str = Query(default="main"),
    commit_message: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Delete a file from git provider"""
    _require_connected(git)
    scoped_path = _tenant_path(tenant_id, file_path)
    msg = commit_message or f"Delete {file_path} for tenant {tenant_id}"

    try:
        await git.remove_file(scoped_path, commit_message=msg, branch=branch)
    except Exception as e:
        logger.error(f"Failed to delete file {scoped_path}: {e}")
        raise HTTPException(status_code=404, detail="File not found")

    return {"message": "File deleted"}


# Merge Requests
@router.get("/merge-requests", response_model=list[MergeRequestResponse])
@require_tenant_access
async def list_merge_requests(
    tenant_id: str,
    state: str = "opened",
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """List merge requests"""
    _require_connected(git)
    try:
        mrs = await git.list_merge_requests(state=state)
        return [MergeRequestResponse(**asdict(mr)) for mr in mrs]
    except Exception as e:
        logger.error(f"Failed to list merge requests: {e}")
        return []


@router.post("/merge-requests", response_model=MergeRequestResponse, status_code=201)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def create_merge_request(
    tenant_id: str,
    mr: MergeRequestCreate,
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Create a merge request"""
    _require_connected(git)
    try:
        new_mr = await git.create_merge_request(
            title=mr.title,
            description=mr.description,
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
        )
        return MergeRequestResponse(**asdict(new_mr))
    except Exception as e:
        logger.error(f"Failed to create merge request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create merge request: {e}")


@router.post("/merge-requests/{mr_iid}/merge", response_model=MergeResultResponse)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def merge_request(
    tenant_id: str,
    mr_iid: int,
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Merge a merge request"""
    _require_connected(git)
    try:
        await git.merge_merge_request(mr_iid)
        return {"message": "Merge request merged", "iid": mr_iid}
    except Exception as e:
        logger.error(f"Failed to merge MR !{mr_iid}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to merge: {e}")


# Branches
@router.get("/branches", response_model=list[BranchInfo])
@require_tenant_access
async def list_branches(
    tenant_id: str,
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """List branches"""
    _require_connected(git)
    try:
        branches = await git.list_branches()
        return [BranchInfo(**asdict(b)) for b in branches]
    except Exception as e:
        logger.error(f"Failed to list branches: {e}")
        return []


@router.post("/branches", response_model=BranchInfo, status_code=201)
@require_permission(Permission.APIS_CREATE)
@require_tenant_access
async def create_branch(
    tenant_id: str,
    body: BranchCreate,
    user: User = Depends(get_current_user),
    git: GitProvider = Depends(get_git_provider),
):
    """Create a new branch"""
    _require_connected(git)
    try:
        branch = await git.create_branch(name=body.name, ref=body.ref)
        return BranchInfo(**asdict(branch))
    except Exception as e:
        logger.error(f"Failed to create branch {body.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create branch: {e}")
