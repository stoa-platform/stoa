"""Git router - provider-agnostic GitOps operations (CAB-1890)"""

import logging

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
        commits = await git.list_commits(
            path=scoped_path, limit=limit
        )  # TODO(CAB-1889): add list_commits to GitProvider ABC
        return [CommitInfo(**c) for c in commits]
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
    content = await git.get_file(scoped_path, ref=ref)  # TODO(CAB-1889): add get_file to GitProvider ABC
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
    scoped_path = _tenant_path(tenant_id, path) if path else _tenant_path(tenant_id)
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    try:
        tree = git._project.repository_tree(path=scoped_path, ref=ref)  # TODO(CAB-1889): abstract _project access
        items = [TreeItem(name=item["name"], type=item["type"], path=item["path"]) for item in tree]
        return TreeListResponse(items=items)
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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    scoped_path = _tenant_path(tenant_id, file_path)
    msg = commit_message or f"Update {file_path} for tenant {tenant_id}"

    # Try to get existing file to determine create vs update
    existing = await git.get_file(scoped_path, ref=branch)  # TODO(CAB-1889): add get_file to GitProvider ABC
    try:
        if existing is not None:
            # TODO(CAB-1889): abstract _project access
            file_obj = git._project.files.get(scoped_path, ref=branch)
            file_obj.content = body.content
            file_obj.save(branch=branch, commit_message=msg)
        else:
            # TODO(CAB-1889): abstract _project access
            git._project.files.create(
                {
                    "file_path": scoped_path,
                    "branch": branch,
                    "content": body.content,
                    "commit_message": msg,
                }
            )
    except Exception as e:
        logger.error(f"Failed to create/update file {scoped_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    return {"path": file_path, "action": "updated" if existing else "created"}


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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    scoped_path = _tenant_path(tenant_id, file_path)
    msg = commit_message or f"Delete {file_path} for tenant {tenant_id}"

    try:
        git._project.files.delete(
            file_path=scoped_path, commit_message=msg, branch=branch
        )  # TODO(CAB-1889): abstract _project access
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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    try:
        mrs = git._project.mergerequests.list(state=state)  # TODO(CAB-1889): abstract _project access
        return [
            MergeRequestResponse(
                id=mr.id,
                iid=mr.iid,
                title=mr.title,
                description=mr.description or "",
                state=mr.state,
                source_branch=mr.source_branch,
                target_branch=mr.target_branch,
                web_url=mr.web_url,
                created_at=mr.created_at,
                author=mr.author.get("name", "") if isinstance(mr.author, dict) else str(mr.author),
            )
            for mr in mrs
        ]
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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    try:
        # TODO(CAB-1889): abstract _project access
        new_mr = git._project.mergerequests.create(
            {
                "title": mr.title,
                "description": mr.description,
                "source_branch": mr.source_branch,
                "target_branch": mr.target_branch,
            }
        )
        return MergeRequestResponse(
            id=new_mr.id,
            iid=new_mr.iid,
            title=new_mr.title,
            description=new_mr.description or "",
            state=new_mr.state,
            source_branch=new_mr.source_branch,
            target_branch=new_mr.target_branch,
            web_url=new_mr.web_url,
            created_at=new_mr.created_at,
            author=new_mr.author.get("name", "") if isinstance(new_mr.author, dict) else str(new_mr.author),
        )
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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    try:
        mr = git._project.mergerequests.get(mr_iid)  # TODO(CAB-1889): abstract _project access
        mr.merge()
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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    try:
        branches = git._project.branches.list()  # TODO(CAB-1889): abstract _project access
        return [
            BranchInfo(
                name=b.name,
                commit_sha=b.commit["id"] if isinstance(b.commit, dict) else str(b.commit),
                protected=getattr(b, "protected", False),
            )
            for b in branches
        ]
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
    if not git._project:  # TODO(CAB-1889): abstract _project access
        raise HTTPException(status_code=503, detail="Git provider not connected")

    try:
        # TODO(CAB-1889): abstract _project access
        branch = git._project.branches.create(
            {
                "branch": body.name,
                "ref": body.ref,
            }
        )
        return BranchInfo(
            name=branch.name,
            commit_sha=branch.commit["id"] if isinstance(branch.commit, dict) else str(branch.commit),
            protected=getattr(branch, "protected", False),
        )
    except Exception as e:
        logger.error(f"Failed to create branch {body.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create branch: {e}")
