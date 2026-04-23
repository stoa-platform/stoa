"""Git router - provider-agnostic GitOps operations (CAB-1890, CAB-1889 CP-1)."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..services.git_provider import GitProvider, get_git_provider, git_provider_factory

# CP-1 H.10: reject paths containing parent segments, absolute prefix,
# backslash, or any ASCII control character (including NUL, TAB, etc).
# Defensive hardening - current providers treat paths literally, but any
# future refactor introducing os.path.normpath / Path().resolve would
# open a traversal window. Applied centrally in _validate_file_path.
_CONTROL_CHAR_RANGE = frozenset((*range(0x00, 0x20), 0x7F))


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


def _validate_file_path(path: str) -> None:
    """CP-1 H.10: reject paths that could escape the tenant scope.

    Rejects:
      - any ``..`` segment (parent traversal)
      - absolute path (``/...``)
      - backslash (Windows-style separator; reserved)
      - any ASCII control character (0x00-0x1f and 0x7f)

    Raises:
        HTTPException(400) on any violation.
    """
    if not path:
        return
    if path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    if ".." in path.split("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    if any(ord(c) in _CONTROL_CHAR_RANGE for c in path):
        raise HTTPException(status_code=400, detail="Invalid path")


def _tenant_path(tenant_id: str, path: str = "") -> str:
    """Build scoped path under the tenant directory.

    CP-1 H.10: caller-supplied ``path`` is validated for traversal /
    control-char injection before concatenation.
    """
    _validate_file_path(path)
    base = f"tenants/{tenant_id}"
    return f"{base}/{path}" if path else base


def _require_connected(git: GitProvider) -> None:
    if not git.is_connected():
        raise HTTPException(status_code=503, detail="Git provider not connected")


def _map_provider_exception(exc: Exception, action: str) -> HTTPException:
    """CP-1 H.3/H.4/H.5: map a raw provider exception to a sanitised HTTP error.

    - ``FileNotFoundError`` → 404 "Not found"
    - ``TimeoutError`` → 504 "Upstream timeout"
    - anything else → 502 "Upstream provider error"

    The original exception is never echoed into ``detail`` — ``str(exc)``
    on PyGithub / python-gitlab errors contains API URLs, request IDs,
    and can surface token fragments. The caller logs ``exc_info=True`` at
    ERROR, and the request_id bound in contextvars by the http_logging
    middleware is returned to the client via the ``X-Request-ID``
    response header for server-side correlation.
    """
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail="Not found")
    if isinstance(exc, TimeoutError):
        return HTTPException(status_code=504, detail=f"Upstream timeout while attempting to {action}")
    return HTTPException(status_code=502, detail=f"Upstream provider error while attempting to {action}")


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
        # CP-1 H.5: do not silently swallow into []. Provider down must
        # surface as 502/504 so the UI can distinguish "no commits" from
        # "provider unreachable".
        logger.error("Failed to list commits for tenant %s", tenant_id, exc_info=True)
        raise _map_provider_exception(e, "list commits") from e


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
    try:
        content = await git.read_file(scoped_path, ref=ref)
    except (FileNotFoundError, TimeoutError) as e:
        raise _map_provider_exception(e, "read file") from e
    except Exception as e:
        logger.error("Failed to read file %s", scoped_path, exc_info=True)
        raise _map_provider_exception(e, "read file") from e
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
    except FileNotFoundError:
        # CP-1 H.5: path that does not exist in the tree is a legitimate
        # "empty listing" (distinct from a provider failure). get_tree is
        # the ONLY listing route that keeps this mapping — list_commits,
        # list_branches and list_merge_requests surface provider errors
        # as 502/504 instead of masking them.
        return TreeListResponse(items=[])
    except Exception as e:
        logger.error("Failed to list tree at %s", scoped_path, exc_info=True)
        raise _map_provider_exception(e, "list tree") from e


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
        # CP-1 H.3: generic detail — no str(e) leak. Full trace stays in
        # server log via exc_info=True; clients correlate via X-Request-ID.
        logger.error("Failed to create/update file %s", scoped_path, exc_info=True)
        raise _map_provider_exception(e, "save file") from e

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
        # CP-1 H.4: do NOT convert every error into 404. Missing file →
        # 404 ; timeout → 504 ; other provider failure → 502. Prior
        # blanket 404 masked outages as "file not found" in the UI.
        logger.error("Failed to delete file %s", scoped_path, exc_info=True)
        raise _map_provider_exception(e, "delete file") from e

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
        # CP-1 H.5: merge-request listing has no natural "file absent"
        # semantics. A missing/unreachable repo must surface, not be
        # silently flattened to [].
        logger.error("Failed to list merge requests", exc_info=True)
        raise _map_provider_exception(e, "list merge requests") from e


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
        logger.error("Failed to create merge request", exc_info=True)
        raise _map_provider_exception(e, "create merge request") from e


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
        logger.error("Failed to merge MR !%s", mr_iid, exc_info=True)
        raise _map_provider_exception(e, "merge merge request") from e


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
        # CP-1 H.5: same rationale as list_merge_requests — branch
        # listing has no natural "missing path" case. Provider failure
        # must surface.
        logger.error("Failed to list branches", exc_info=True)
        raise _map_provider_exception(e, "list branches") from e


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
        logger.error("Failed to create branch %s", body.name, exc_info=True)
        raise _map_provider_exception(e, "create branch") from e
