"""Git router - GitLab operations for GitOps"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..services.git_service import git_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/git", tags=["Git"])


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
):
    """List recent commits for tenant repository"""
    scoped_path = _tenant_path(tenant_id, path) if path else _tenant_path(tenant_id)
    try:
        commits = await git_service.list_commits(path=scoped_path, limit=limit)
        return [CommitInfo(**c) for c in commits]
    except Exception as e:
        logger.error(f"Failed to list commits for tenant {tenant_id}: {e}")
        return []


@router.get("/files/{file_path:path}")
@require_tenant_access
async def get_file(tenant_id: str, file_path: str, ref: str = "main", user: User = Depends(get_current_user)):
    """Get file content from GitLab"""
    scoped_path = _tenant_path(tenant_id, file_path)
    content = await git_service.get_file(scoped_path, ref=ref)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileContent(path=file_path, content=content)


@router.get("/tree")
@require_tenant_access
async def get_tree(
    tenant_id: str,
    path: str = "",
    ref: str = "main",
    user: User = Depends(get_current_user),
):
    """Get directory tree from GitLab"""
    scoped_path = _tenant_path(tenant_id, path) if path else _tenant_path(tenant_id)
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    try:
        tree = git_service._project.repository_tree(path=scoped_path, ref=ref)
        items = [{"name": item["name"], "type": item["type"], "path": item["path"]} for item in tree]
        return {"items": items}
    except Exception:
        return {"items": []}


@router.post("/files/{file_path:path}", status_code=201)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def create_or_update_file(
    tenant_id: str,
    file_path: str,
    body: FileCreateUpdate,
    branch: str = Query(default="main"),
    commit_message: str | None = Query(default=None),
    user: User = Depends(get_current_user),
):
    """Create or update a file in GitLab"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    scoped_path = _tenant_path(tenant_id, file_path)
    msg = commit_message or f"Update {file_path} for tenant {tenant_id}"

    # Try to get existing file to determine create vs update
    existing = await git_service.get_file(scoped_path, ref=branch)
    try:
        if existing is not None:
            file_obj = git_service._project.files.get(scoped_path, ref=branch)
            file_obj.content = body.content
            file_obj.save(branch=branch, commit_message=msg)
        else:
            git_service._project.files.create(
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


@router.delete("/files/{file_path:path}")
@require_permission(Permission.APIS_DELETE)
@require_tenant_access
async def delete_file(
    tenant_id: str,
    file_path: str,
    branch: str = Query(default="main"),
    commit_message: str | None = Query(default=None),
    user: User = Depends(get_current_user),
):
    """Delete a file from GitLab"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    scoped_path = _tenant_path(tenant_id, file_path)
    msg = commit_message or f"Delete {file_path} for tenant {tenant_id}"

    try:
        git_service._project.files.delete(file_path=scoped_path, commit_message=msg, branch=branch)
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
):
    """List merge requests"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    try:
        mrs = git_service._project.mergerequests.list(state=state)
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
async def create_merge_request(tenant_id: str, mr: MergeRequestCreate, user: User = Depends(get_current_user)):
    """Create a merge request"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    try:
        new_mr = git_service._project.mergerequests.create(
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


@router.post("/merge-requests/{mr_iid}/merge")
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def merge_request(tenant_id: str, mr_iid: int, user: User = Depends(get_current_user)):
    """Merge a merge request"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    try:
        mr = git_service._project.mergerequests.get(mr_iid)
        mr.merge()
        return {"message": "Merge request merged", "iid": mr_iid}
    except Exception as e:
        logger.error(f"Failed to merge MR !{mr_iid}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to merge: {e}")


# Branches
@router.get("/branches", response_model=list[BranchInfo])
@require_tenant_access
async def list_branches(tenant_id: str, user: User = Depends(get_current_user)):
    """List branches"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    try:
        branches = git_service._project.branches.list()
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
):
    """Create a new branch"""
    if not git_service._project:
        raise HTTPException(status_code=503, detail="GitLab not connected")

    try:
        branch = git_service._project.branches.create(
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
