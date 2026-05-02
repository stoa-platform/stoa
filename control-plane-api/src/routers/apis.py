"""APIs router - API lifecycle management via database catalog"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    Permission,
    User,
    get_current_user,
    require_permission,
    require_tenant_access,
    require_writable_environment,
)
from ..config import settings
from ..database import get_db
from ..models.catalog import APICatalog
from ..repositories.catalog import CatalogRepository
from ..repositories.tenant import TenantRepository
from ..schemas.pagination import PaginatedResponse
from ..services import git_service
from ..services.catalog_git_client.github_contents import GitHubContentsCatalogClient
from ..services.gitops_writer import (
    ApiCreatePayload,
    GitOpsConflictError,
    GitOpsRaceExhaustedError,
    GitOpsWriter,
    InfrastructureBugError,
    InvalidApiNameError,
    LegacyCollisionError,
)
from ..services.gitops_writer.eligibility import is_gitops_create_eligible
from ..services.kafka_service import kafka_service

# CAB-2159 BUG-4 — keep in sync with src/models/catalog.py:AudienceEnum
AudienceLiteral = Literal["public", "internal", "partner"]

logger = logging.getLogger(__name__)


def _build_catalog_git_client() -> GitHubContentsCatalogClient:
    """Construct the :class:`CatalogGitClient` used by the GitOps create path.

    Extracted so tests can patch it (E2E mocked tests inject an in-memory
    fake client without touching PyGithub). Production deployments wire
    ``GIT_PROVIDER=github`` and the module-level ``git_service`` is the
    same connected :class:`GitHubService` the catalog reconciler consumes
    — sharing one singleton across the create path and the reconciler
    ensures both observe the same connection state.
    """
    from ..services.github_service import GitHubService

    if not isinstance(git_service, GitHubService):
        raise RuntimeError(f"GitOps create path requires GIT_PROVIDER=github; got {type(git_service).__name__}.")
    return GitHubContentsCatalogClient(github_service=git_service)


router = APIRouter(prefix="/v1/tenants/{tenant_id}/apis", tags=["APIs"])


class APICreate(BaseModel):
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    backend_url: str
    openapi_spec: str | None = None
    tags: list[str] = []  # Tags for categorization and portal promotion


class APIUpdate(BaseModel):
    display_name: str | None = None
    version: str | None = None
    description: str | None = None
    backend_url: str | None = None
    openapi_spec: str | None = None
    tags: list[str] | None = None  # Tags for categorization and portal promotion


class APIResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    display_name: str
    version: str
    description: str
    backend_url: str
    status: str = "draft"
    deployed_dev: bool = False
    deployed_staging: bool = False
    tags: list[str] = []
    portal_promoted: bool = False  # True if API has portal:published tag
    audience: AudienceLiteral = "public"
    catalog_release_id: str | None = None
    catalog_release_tag: str | None = None
    catalog_pr_url: str | None = None
    catalog_pr_number: int | None = None
    catalog_source_branch: str | None = None
    catalog_merge_commit_sha: str | None = None
    # CAB-2159 BUG-4: APICatalog currently has no true created_at column; we surface
    # ``synced_at`` as both timestamps so UI can render them uniformly with other
    # entities. Adding real ``created_at``/``updated_at`` DB columns is tracked
    # separately (migration scope).
    created_at: datetime | None = None
    updated_at: datetime | None = None


class APIOpenAPISpecResponse(BaseModel):
    spec: dict[str, Any]
    source: Literal["git", "db_cache", "generated_fallback"]
    git_path: str
    git_commit_sha: str | None = None
    format: Literal["openapi", "swagger", "unknown"] = "unknown"
    is_authoritative: bool = False


class APIVersionEntry(BaseModel):
    """A single version entry from git history."""

    sha: str
    message: str
    author: str
    date: str


def _slugify(value: str) -> str:
    """Generate URL-safe slug from a name (CAB-1938)."""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s-]+", "-", value).strip("-")
    return value or "api"


def _validate_openapi_spec(spec_str: str) -> None:
    """Validate that a string is a parseable OpenAPI 3.x spec (CAB-1917)."""
    import json

    import yaml

    try:
        spec = json.loads(spec_str) if spec_str.strip().startswith("{") else yaml.safe_load(spec_str)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid OpenAPI spec: unable to parse — {e}")

    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail="Invalid OpenAPI spec: must be a JSON/YAML object")

    version = spec.get("openapi", spec.get("swagger", ""))
    if not version:
        raise HTTPException(
            status_code=400,
            detail="Invalid OpenAPI spec: missing 'openapi' or 'swagger' version field",
        )
    if not str(version).startswith("3") and not str(version).startswith("2"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported OpenAPI version: {version}. Supported: 2.x and 3.x",
        )


def _parse_openapi_spec(spec_str: str | None) -> dict | None:
    """Parse JSON/YAML OpenAPI input into the DB/event shape."""
    if not spec_str:
        return None
    import yaml

    try:
        parsed = json.loads(spec_str) if spec_str.strip().startswith("{") else yaml.safe_load(spec_str)
    except (json.JSONDecodeError, yaml.YAMLError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _detect_spec_format(spec: dict[str, Any]) -> Literal["openapi", "swagger", "unknown"]:
    if spec.get("openapi"):
        return "openapi"
    if spec.get("swagger"):
        return "swagger"
    return "unknown"


def _is_usable_openapi_spec(value: Any) -> bool:
    return isinstance(value, dict) and _detect_spec_format(value) != "unknown" and isinstance(value.get("paths"), dict)


def _canonical_openapi_git_path(tenant_id: str, api_id: str, api: APICatalog | None = None) -> str:
    raw_path = getattr(api, "git_path", None) if api is not None else None
    if isinstance(raw_path, str) and raw_path:
        base = raw_path.removesuffix("/api.yaml").rstrip("/")
        if base.endswith(f"/apis/{api_id}"):
            return f"{base}/openapi.yaml"
    return f"tenants/{tenant_id}/apis/{api_id}/openapi.yaml"


def _generated_openapi_fallback(api: APICatalog) -> dict[str, Any]:
    metadata = api.api_metadata or {}
    title = metadata.get("display_name") or api.api_name or api.api_id
    version = api.version or metadata.get("version") or "1.0.0"
    description = metadata.get("description") or "Generated fallback because no Git OpenAPI file was found."
    backend_url = metadata.get("backend_url")
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": version,
            "description": description,
        },
        "paths": {
            "/": {
                "get": {
                    "summary": "Fallback operation",
                    "responses": {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {"schema": {"type": "object"}}
                            },
                        }
                    },
                }
            }
        },
    }
    if isinstance(backend_url, str) and backend_url:
        spec["servers"] = [{"url": backend_url}]
    return spec


def _api_from_catalog(api: APICatalog) -> APIResponse:
    """Convert APICatalog DB model to APIResponse."""
    metadata = api.api_metadata or {}
    tags = api.tags or []
    promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
    portal_promoted = any(tag.lower() in promotion_tags for tag in tags)
    deployments = metadata.get("deployments", {})
    # CAB-2159 BUG-4 — audience column has a non-null default in the DB; coerce
    # any unexpected stored value back into the Literal set so Pydantic validation
    # never trips on legacy rows.
    raw_audience = (api.audience or "public") if isinstance(api.audience, str) else "public"
    audience: AudienceLiteral = raw_audience if raw_audience in ("public", "internal", "partner") else "public"

    def _optional_str_attr(name: str) -> str | None:
        value = getattr(api, name, None)
        return value if isinstance(value, str) else None

    catalog_pr_number = getattr(api, "catalog_pr_number", None)
    if not isinstance(catalog_pr_number, int):
        catalog_pr_number = None

    return APIResponse(
        id=api.api_id,
        tenant_id=api.tenant_id,
        name=api.api_id,
        display_name=metadata.get("display_name") or api.api_name or api.api_id,
        version=api.version or "1.0.0",
        description=metadata.get("description", ""),
        backend_url=metadata.get("backend_url", ""),
        status=api.status or "draft",
        deployed_dev=deployments.get("dev", False),
        deployed_staging=deployments.get("staging", False),
        tags=tags,
        portal_promoted=portal_promoted,
        audience=audience,
        catalog_release_id=_optional_str_attr("catalog_release_id"),
        catalog_release_tag=_optional_str_attr("catalog_release_tag"),
        catalog_pr_url=_optional_str_attr("catalog_pr_url"),
        catalog_pr_number=catalog_pr_number,
        catalog_source_branch=_optional_str_attr("catalog_source_branch"),
        catalog_merge_commit_sha=_optional_str_attr("catalog_merge_commit_sha"),
        created_at=api.synced_at,
        updated_at=api.synced_at,
    )


@router.get("", response_model=PaginatedResponse[APIResponse])
@require_tenant_access
async def list_apis(
    tenant_id: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    environment: str | None = Query(default=None, description="Filter by environment (dev, staging, prod)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List APIs for a tenant from database catalog (paginated).

    Optionally filter by environment — only returns APIs deployed to that environment.
    """
    try:
        repo = CatalogRepository(db)
        apis, total = await repo.get_portal_apis(
            tenant_id=tenant_id,
            include_unpublished=True,
            page=page,
            page_size=page_size,
        )
        all_items = [_api_from_catalog(api) for api in apis]
        # Filter by environment if specified (post-filter since catalog doesn't support this natively)
        if environment:
            if environment == "dev":
                all_items = [
                    api for api in all_items if api.deployed_dev or (not api.deployed_dev and not api.deployed_staging)
                ]
            elif environment == "staging":
                all_items = [api for api in all_items if api.deployed_staging]
            elif environment == "prod":
                all_items = [api for api in all_items if api.deployed_dev and api.deployed_staging]
            total = len(all_items)
        return PaginatedResponse(items=all_items, total=total, page=page, page_size=page_size)
    except Exception as e:
        logger.error(f"Failed to list APIs for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="API listing temporarily unavailable. Please try again later.",
        )


@router.get("/{api_id}", response_model=APIResponse)
@require_tenant_access
async def get_api(
    tenant_id: str,
    api_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get API by ID from database catalog"""
    try:
        repo = CatalogRepository(db)
        api = await repo.get_api_by_id(tenant_id, api_id)
        if not api:
            raise HTTPException(status_code=404, detail="API not found")
        return _api_from_catalog(api)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get API {api_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve API")


@router.get("/{api_id}/openapi", response_model=APIOpenAPISpecResponse)
@require_tenant_access
async def get_api_openapi_spec(
    tenant_id: str,
    api_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the API description document, preferring Git over DB cache.

    Git is the configuration source of truth. ``api_catalog.openapi_spec`` is
    treated only as a compatibility cache for legacy rows and never overrides a
    readable ``tenants/{tenant}/apis/{api}/openapi.yaml`` file.
    """
    try:
        repo = CatalogRepository(db)
        api = await repo.get_api_by_id(tenant_id, api_id)
        if not api:
            raise HTTPException(status_code=404, detail="API not found")

        git_path = _canonical_openapi_git_path(tenant_id, api_id, api)
        try:
            git_spec = await git_service.get_api_openapi_spec(tenant_id, api_id)
        except Exception as exc:
            logger.warning(
                "api_openapi_git_read_failed",
                extra={"tenant_id": tenant_id, "api_id": api_id, "error": str(exc)},
            )
            git_spec = None

        if _is_usable_openapi_spec(git_spec):
            return APIOpenAPISpecResponse(
                spec=git_spec,
                source="git",
                git_path=git_path,
                git_commit_sha=getattr(api, "git_commit_sha", None),
                format=_detect_spec_format(git_spec),
                is_authoritative=True,
            )

        db_spec = getattr(api, "openapi_spec", None)
        if _is_usable_openapi_spec(db_spec):
            return APIOpenAPISpecResponse(
                spec=db_spec,
                source="db_cache",
                git_path=git_path,
                git_commit_sha=getattr(api, "git_commit_sha", None),
                format=_detect_spec_format(db_spec),
                is_authoritative=False,
            )

        fallback = _generated_openapi_fallback(api)
        return APIOpenAPISpecResponse(
            spec=fallback,
            source="generated_fallback",
            git_path=git_path,
            git_commit_sha=getattr(api, "git_commit_sha", None),
            format="openapi",
            is_authoritative=False,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get OpenAPI spec for {api_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve OpenAPI specification")


@router.post("", response_model=APIResponse, dependencies=[Depends(require_writable_environment)])
@require_permission(Permission.APIS_CREATE)
@require_tenant_access
async def create_api(
    tenant_id: str,
    api: APICreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API in the database catalog and emit event.

    Trial tenants are subject to limits (CAB-1549):
    - Max 3 APIs (configurable via tenant.settings.max_apis)
    - 402 after 30-day trial expires

    GitOps create rewrite (CAB-2185 B-FLOW): when ``GITOPS_CREATE_API_ENABLED``
    is True AND ``tenant_id`` is in ``GITOPS_ELIGIBLE_TENANTS``, the request is
    routed through :class:`GitOpsWriter` (Git-first, no Kafka emit, spec §6.13).
    Otherwise the legacy DB-first path runs unchanged. Default flag value is
    ``False`` and the eligible-tenant list is empty by default — production
    behaviour is unchanged until Phase 6 strangler.
    """
    if is_gitops_create_eligible(
        enabled=settings.GITOPS_CREATE_API_ENABLED,
        tenant_id=tenant_id,
        eligible_tenants=settings.GITOPS_ELIGIBLE_TENANTS,
    ):
        return await _create_api_gitops(tenant_id=tenant_id, api=api, user=user, db=db)

    return await _create_api_legacy(tenant_id=tenant_id, api=api, user=user, db=db)


async def _create_api_legacy(
    *,
    tenant_id: str,
    api: APICreate,
    user: User,
    db: AsyncSession,
) -> APIResponse:
    """Legacy DB-first path: INSERT api_catalog + emit Kafka event.

    Behaviour preserved verbatim from before the GitOps rewrite (CAB-2185).
    """
    # Trial limits enforcement (CAB-1549)
    from ..routers.tenants import get_tenant_limits
    from ..services.trial_service import check_trial_expiry

    catalog_repo = CatalogRepository(db)
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant:
        settings = tenant.settings or {}
        check_trial_expiry(settings)
        max_apis, _ = get_tenant_limits(tenant)
        current_apis, _ = await catalog_repo.get_portal_apis(tenant_id=tenant_id, include_unpublished=True)
        if len(current_apis) >= max_apis:
            raise HTTPException(status_code=429, detail=f"API limit reached ({max_apis})")

    # Validate OpenAPI spec if provided (CAB-1917)
    if api.openapi_spec:
        _validate_openapi_spec(api.openapi_spec)

    tags = api.tags or []
    promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
    portal_promoted = any(tag.lower() in promotion_tags for tag in tags)

    # Generate URL-safe slug from name (CAB-1938)
    api_id = _slugify(api.name)

    api_metadata = {
        "name": api.name,
        "display_name": api.display_name,
        "version": api.version,
        "description": api.description,
        "backend_url": api.backend_url,
        "tags": tags,
        "status": "draft",
        "deployments": {"dev": False, "staging": False},
    }

    openapi_spec = _parse_openapi_spec(api.openapi_spec)

    try:
        stmt = insert(APICatalog).values(
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api.name,
            version=api.version,
            status="draft",
            tags=tags,
            portal_published=portal_promoted,
            api_metadata=api_metadata,
            openapi_spec=openapi_spec,
            synced_at=datetime.now(UTC),
        )
        await db.execute(stmt)
        await db.commit()

        # Emit Kafka event
        await kafka_service.emit_api_created(
            tenant_id=tenant_id,
            api_data={
                "id": api_id,
                "name": api_id,
                "display_name": api.display_name,
                "version": api.version,
                "description": api.description,
                "backend_url": api.backend_url,
                "tags": tags,
                "openapi_spec": openapi_spec,
            },
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="create",
            resource_type="api",
            resource_id=api_id,
            user_id=user.id,
            details={"name": api.name, "version": api.version},
        )

        logger.info(f"Created API {api_id} ({api.name}) for tenant {tenant_id} by {user.username}")

        return APIResponse(
            id=api_id,
            tenant_id=tenant_id,
            name=api_id,
            display_name=api.display_name,
            version=api.version,
            description=api.description,
            backend_url=api.backend_url,
            status="draft",
            deployed_dev=False,
            deployed_staging=False,
            tags=tags,
            portal_promoted=portal_promoted,
        )

    except Exception as e:
        await db.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            logger.warning(f"API creation conflict for {api.name} v{api.version}: {e}")
            raise HTTPException(
                status_code=409,
                detail=f"API '{api.name}' version '{api.version}' already exists in this tenant",
            )
        logger.error(f"Failed to create API {api.name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create API. Please try again or contact support.")


async def _create_api_gitops(
    *,
    tenant_id: str,
    api: APICreate,
    user: User,
    db: AsyncSession,
) -> APIResponse:
    """GitOps Git-first path (CAB-2185 B-FLOW + spec §6.5).

    Steps:

    * Build :class:`ApiCreatePayload` from the HTTP body
    * Resolve a :class:`CatalogGitClient` from the configured Git provider
    * Run ``GitOpsWriter.create_api`` (18-step flow §6.5)
    * Read the projected ``api_catalog`` row back to build the response

    The Kafka ``stoa.api.lifecycle`` event is intentionally NOT emitted on
    this path (spec §6.13). Audit events are also skipped here so the
    legacy and new paths cannot double-emit during the strangler.
    """
    if api.openapi_spec:
        _validate_openapi_spec(api.openapi_spec)

    api_name = _slugify(api.name)
    payload = ApiCreatePayload(
        api_name=api_name,
        display_name=api.display_name,
        version=api.version,
        backend_url=api.backend_url,
        description=api.description,
        tags=tuple(api.tags or ()),
        openapi_spec=_parse_openapi_spec(api.openapi_spec),
    )

    try:
        catalog_git_client = _build_catalog_git_client()
    except RuntimeError as exc:
        logger.error(
            "gitops_create_api_client_unavailable",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc))
    writer = GitOpsWriter(
        catalog_git_client=catalog_git_client,
        db_session=db,
        catalog_write_mode=settings.GITOPS_CATALOG_WRITE_MODE,
    )

    try:
        result = await writer.create_api(
            tenant_id=tenant_id,
            contract_payload=payload,
            actor=user.username or user.id,
        )
    except InvalidApiNameError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LegacyCollisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except GitOpsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except GitOpsRaceExhaustedError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except InfrastructureBugError:
        logger.exception("gitops_writer.infrastructure_bug")
        raise HTTPException(status_code=500, detail="internal error: read-after-commit returned 404")

    await db.commit()

    repo = CatalogRepository(db)
    persisted = await repo.get_api_by_id(tenant_id, result.api_id)
    if persisted is None:
        logger.error(
            "gitops_create_api_projection_missing",
            extra={"tenant_id": tenant_id, "api_id": result.api_id},
        )
        raise HTTPException(status_code=500, detail="internal error: api_catalog projection missing")

    return _api_from_catalog(persisted)


@router.put("/{api_id}", response_model=APIResponse, dependencies=[Depends(require_writable_environment)])
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def update_api(
    tenant_id: str,
    api_id: str,
    api: APIUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update API in database catalog"""
    try:
        repo = CatalogRepository(db)
        current = await repo.get_api_by_id(tenant_id, api_id)
        if not current:
            raise HTTPException(status_code=404, detail="API not found")

        # Build update dict (only non-None fields)
        updates = {k: v for k, v in api.model_dump().items() if v is not None}

        if not updates:
            return _api_from_catalog(current)

        # Apply updates to model fields
        metadata = dict(current.api_metadata or {})
        if "display_name" in updates:
            current.api_name = updates["display_name"]
            metadata["display_name"] = updates["display_name"]
        if "version" in updates:
            current.version = updates["version"]
            metadata["version"] = updates["version"]
        if "description" in updates:
            metadata["description"] = updates["description"]
        if "backend_url" in updates:
            metadata["backend_url"] = updates["backend_url"]
        if "tags" in updates:
            current.tags = updates["tags"]
            metadata["tags"] = updates["tags"]
            promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
            current.portal_published = any(tag.lower() in promotion_tags for tag in updates["tags"])
        if "openapi_spec" in updates:
            current.openapi_spec = _parse_openapi_spec(updates["openapi_spec"])

        current.api_metadata = metadata
        current.synced_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(current)

        # Emit Kafka event
        await kafka_service.emit_api_updated(
            tenant_id=tenant_id,
            api_data={
                "id": api_id,
                "name": current.api_id,
                "display_name": current.api_name,
                "version": current.version,
                "description": metadata.get("description", ""),
                "backend_url": metadata.get("backend_url", ""),
                "tags": current.tags or [],
                "openapi_spec": current.openapi_spec,
            },
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="update",
            resource_type="api",
            resource_id=api_id,
            user_id=user.id,
            details=updates,
        )

        logger.info(f"Updated API {api_id} for tenant {tenant_id} by {user.username}")

        return _api_from_catalog(current)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update API {api_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update API. Please try again or contact support.")


@router.delete("/{api_id}", dependencies=[Depends(require_writable_environment)])
@require_permission(Permission.APIS_DELETE)
@require_tenant_access
async def delete_api(
    tenant_id: str,
    api_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete API from database catalog"""
    try:
        repo = CatalogRepository(db)
        api = await repo.get_api_by_id(tenant_id, api_id)
        if not api:
            raise HTTPException(status_code=404, detail="API not found")

        # Soft delete
        api.deleted_at = datetime.now(UTC)
        await db.commit()

        # Emit Kafka event
        await kafka_service.emit_api_deleted(
            tenant_id=tenant_id,
            api_id=api_id,
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="delete",
            resource_type="api",
            resource_id=api_id,
            user_id=user.id,
            details={"name": api.api_id},
        )

        logger.info(f"Deleted API {api_id} for tenant {tenant_id} by {user.username}")

        return {"message": "API deleted", "id": api_id}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete API {api_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete API. Please try again or contact support.")


@router.get("/{api_id}/versions", response_model=list[APIVersionEntry])
@require_tenant_access
async def list_api_versions(
    tenant_id: str,
    api_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max commits to return"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List version history for a specific API.

    Git history unavailable — returns empty list pending GitHub migration (CAB-1890).
    """
    repo = CatalogRepository(db)
    api = await repo.get_api_by_id(tenant_id, api_id)
    if not api:
        raise HTTPException(status_code=404, detail="API not found")
    return []  # Git history unavailable — GitLab migration pending (CAB-1890)
