# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Git router - GitLab operations for GitOps"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from ..auth import get_current_user, User, Permission, require_permission, require_tenant_access

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

@router.get("/commits", response_model=List[CommitInfo])
@require_tenant_access
async def list_commits(
    tenant_id: str,
    path: Optional[str] = None,
    limit: int = 20,
    user: User = Depends(get_current_user)
):
    """List recent commits for tenant repository"""
    # TODO: Implement with GitLab service
    return []

@router.get("/files/{file_path:path}")
@require_tenant_access
async def get_file(
    tenant_id: str, file_path: str, ref: str = "main", user: User = Depends(get_current_user)
):
    """Get file content from GitLab"""
    # TODO: Implement with GitLab service
    raise HTTPException(status_code=404, detail="File not found")

@router.get("/tree")
@require_tenant_access
async def get_tree(
    tenant_id: str,
    path: str = "",
    ref: str = "main",
    user: User = Depends(get_current_user)
):
    """Get directory tree from GitLab"""
    # TODO: Implement with GitLab service
    return {"items": []}

@router.post("/files/{file_path:path}")
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def create_or_update_file(
    tenant_id: str,
    file_path: str,
    content: FileContent,
    branch: str = "main",
    commit_message: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Create or update a file in GitLab"""
    # TODO: Implement with GitLab service
    pass

@router.delete("/files/{file_path:path}")
@require_permission(Permission.APIS_DELETE)
@require_tenant_access
async def delete_file(
    tenant_id: str,
    file_path: str,
    branch: str = "main",
    commit_message: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Delete a file from GitLab"""
    # TODO: Implement with GitLab service
    return {"message": "File deleted"}

# Merge Requests
@router.get("/merge-requests", response_model=List[MergeRequestResponse])
@require_tenant_access
async def list_merge_requests(
    tenant_id: str,
    state: str = "opened",
    user: User = Depends(get_current_user)
):
    """List merge requests"""
    # TODO: Implement with GitLab service
    return []

@router.post("/merge-requests", response_model=MergeRequestResponse)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def create_merge_request(
    tenant_id: str, mr: MergeRequestCreate, user: User = Depends(get_current_user)
):
    """Create a merge request"""
    # TODO: Implement with GitLab service
    pass

@router.post("/merge-requests/{mr_iid}/merge")
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def merge_request(
    tenant_id: str, mr_iid: int, user: User = Depends(get_current_user)
):
    """Merge a merge request"""
    # TODO: Implement with GitLab service
    # This triggers GitOps deployment via webhook
    return {"message": "Merge request merged"}

# Branches
@router.get("/branches")
@require_tenant_access
async def list_branches(tenant_id: str, user: User = Depends(get_current_user)):
    """List branches"""
    # TODO: Implement with GitLab service
    return {"branches": []}

@router.post("/branches")
@require_permission(Permission.APIS_CREATE)
@require_tenant_access
async def create_branch(
    tenant_id: str,
    branch_name: str,
    ref: str = "main",
    user: User = Depends(get_current_user)
):
    """Create a new branch"""
    # TODO: Implement with GitLab service
    return {"branch": branch_name, "created": True}
