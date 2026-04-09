"""APIs router - API lifecycle management via database catalog"""

import json
import logging
import re
from datetime import UTC, datetime

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
from ..database import get_db
from ..models.catalog import APICatalog
from ..repositories.catalog import CatalogRepository
from ..repositories.tenant import TenantRepository
from ..schemas.pagination import PaginatedResponse
from ..services.git_provider import git_provider_factory
from ..services.kafka_service import kafka_service

logger = logging.getLogger(__name__)

# Backward-compat shim for test patching (see conftest.py _git_di_bridge)
git_service = git_provider_factory()

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


def _api_from_catalog(api: APICatalog) -> APIResponse:
    """Convert APICatalog DB model to APIResponse."""
    metadata = api.api_metadata or {}
    tags = api.tags or []
    promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
    portal_promoted = any(tag.lower() in promotion_tags for tag in tags)
    deployments = metadata.get("deployments", {})
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
        current_apis, _ = await catalog_repo.get_portal_apis(
            tenant_id=tenant_id, include_unpublished=True
        )
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

    openapi_spec = None
    if api.openapi_spec:
        try:
            openapi_spec = json.loads(api.openapi_spec)
        except (json.JSONDecodeError, TypeError):
            openapi_spec = None

    try:
        stmt = (
            insert(APICatalog)
            .values(
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
        )
        await db.execute(stmt)
        await db.commit()

        # Emit Kafka event
        await kafka_service.emit_api_created(
            tenant_id=tenant_id,
            api_data={
                "id": api_id,
                "name": api.name,
                "version": api.version,
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
            try:
                current.openapi_spec = json.loads(updates["openapi_spec"]) if updates["openapi_spec"] else None
            except (json.JSONDecodeError, TypeError):
                current.openapi_spec = None

        current.api_metadata = metadata
        current.synced_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(current)

        # Emit Kafka event
        await kafka_service.emit_api_updated(
            tenant_id=tenant_id,
            api_data={"id": api_id, **updates},
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
