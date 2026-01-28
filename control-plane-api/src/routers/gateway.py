# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Gateway router - Proxy to webMethods Gateway Admin API with OIDC token forwarding.

This router exposes Gateway administration operations through the Control-Plane API,
using the user's JWT token for authentication via the Gateway-Admin-API proxy.

Benefits:
- No Basic Auth credentials stored in Control-Plane API
- User's JWT token is forwarded for audit trail
- Role-based access control via Keycloak
- Centralized API management through Control-Plane
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from ..auth import get_current_user, User, Permission, require_permission
from ..services.gateway_service import gateway_service
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/gateway", tags=["Gateway"])

security = HTTPBearer(auto_error=True)


# ============================================================================
# Models
# ============================================================================

class GatewayAPIResponse(BaseModel):
    id: str
    apiName: str
    apiVersion: str
    type: Optional[str] = None
    isActive: bool = False
    systemVersion: Optional[int] = None


class GatewayApplicationResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    contactEmails: List[str] = []


class GatewayScopeResponse(BaseModel):
    scopeName: str
    scopeDescription: Optional[str] = None
    audience: Optional[str] = None


class ImportAPIRequest(BaseModel):
    """Request model for importing an API from OpenAPI spec.

    Uses Gateway-native field names for compatibility with existing playbooks.
    """
    apiName: str
    apiVersion: str
    url: Optional[str] = None  # URL to fetch OpenAPI spec from
    apiDefinition: Optional[Dict[str, Any]] = None  # Inline OpenAPI spec as JSON object
    type: str = "openapi"  # API type: openapi, swagger, raml, wsdl


class ImportAPIResponse(BaseModel):
    """Response model for imported API."""
    success: bool
    api_id: Optional[str] = None
    api_name: str
    api_version: str
    message: str = ""


class OIDCConfigRequest(BaseModel):
    tenant_id: str
    api_name: str
    api_version: str
    api_id: str
    client_id: str
    audience: str = "control-plane-api"
    auth_server_alias: str = "KeycloakOIDC"


class OIDCConfigResponse(BaseModel):
    success: bool
    strategy: Optional[dict] = None
    application: Optional[dict] = None
    scopes: List[dict] = []
    message: str = ""


# ============================================================================
# Helper to get raw JWT token
# ============================================================================

async def get_auth_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Extract raw JWT token from Authorization header."""
    return credentials.credentials


# ============================================================================
# API Operations
# ============================================================================

@router.get("/apis", response_model=List[GatewayAPIResponse])
@require_permission(Permission.APIS_READ)
async def list_gateway_apis(
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """List all APIs registered in the Gateway.

    Requires: cpi-admin or devops role
    """
    try:
        apis = await gateway_service.list_apis(auth_token=token)
        return [
            GatewayAPIResponse(
                id=api.get("api", {}).get("id", api.get("id", "")),
                apiName=api.get("api", {}).get("apiName", api.get("apiName", "")),
                apiVersion=api.get("api", {}).get("apiVersion", api.get("apiVersion", "")),
                type=api.get("api", {}).get("type", api.get("type")),
                isActive=api.get("api", {}).get("isActive", api.get("isActive", False)),
                systemVersion=api.get("api", {}).get("systemVersion", api.get("systemVersion")),
            )
            for api in apis
        ]
    except Exception as e:
        logger.error(f"Failed to list Gateway APIs: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@router.post("/apis", response_model=ImportAPIResponse)
@require_permission(Permission.APIS_CREATE)
async def import_gateway_api(
    request: ImportAPIRequest,
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Import an API from OpenAPI specification into the Gateway.

    Requires: cpi-admin or devops role with create permission

    Args:
        apiName: Name for the API
        apiVersion: Version of the API
        url: URL to fetch OpenAPI spec from
        apiDefinition: OpenAPI spec content as string (alternative to url)
        type: API type (openapi, swagger, raml, wsdl)
    """
    try:
        if not request.url and not request.apiDefinition:
            raise HTTPException(
                status_code=400,
                detail="Either url or apiDefinition must be provided"
            )

        result = await gateway_service.import_api(
            api_name=request.apiName,
            api_version=request.apiVersion,
            openapi_url=request.url,
            openapi_spec=request.apiDefinition,
            api_type=request.type,
            auth_token=token,
        )

        api_id = result.get("apiResponse", {}).get("api", {}).get("id", "")
        logger.info(f"User {user.username} imported API {request.apiName} v{request.apiVersion} (ID: {api_id})")

        return ImportAPIResponse(
            success=True,
            api_id=api_id,
            api_name=request.apiName,
            api_version=request.apiVersion,
            message=f"API {request.apiName} v{request.apiVersion} imported successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import API {request.apiName}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@router.get("/apis/{api_id}")
@require_permission(Permission.APIS_READ)
async def get_gateway_api(
    api_id: str,
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Get API details from Gateway.

    Requires: cpi-admin or devops role
    """
    try:
        api = await gateway_service.get_api(api_id, auth_token=token)
        if not api:
            raise HTTPException(status_code=404, detail="API not found in Gateway")
        return api
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Gateway API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@router.put("/apis/{api_id}/activate")
@require_permission(Permission.APIS_PROMOTE)
async def activate_gateway_api(
    api_id: str,
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Activate an API in the Gateway.

    Requires: cpi-admin or devops role with promote permission
    """
    try:
        result = await gateway_service.activate_api(api_id, auth_token=token)
        logger.info(f"User {user.username} activated API {api_id}")
        return {"success": True, "message": f"API {api_id} activated", "result": result}
    except Exception as e:
        logger.error(f"Failed to activate Gateway API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@router.put("/apis/{api_id}/deactivate")
@require_permission(Permission.APIS_PROMOTE)
async def deactivate_gateway_api(
    api_id: str,
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Deactivate an API in the Gateway.

    Requires: cpi-admin or devops role with promote permission
    """
    try:
        result = await gateway_service.deactivate_api(api_id, auth_token=token)
        logger.info(f"User {user.username} deactivated API {api_id}")
        return {"success": True, "message": f"API {api_id} deactivated", "result": result}
    except Exception as e:
        logger.error(f"Failed to deactivate Gateway API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@router.delete("/apis/{api_id}")
@require_permission(Permission.APIS_DELETE)
async def delete_gateway_api(
    api_id: str,
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Delete an API from the Gateway.

    Requires: cpi-admin role
    """
    try:
        await gateway_service.delete_api(api_id, auth_token=token)
        logger.info(f"User {user.username} deleted API {api_id}")
        return {"success": True, "message": f"API {api_id} deleted"}
    except Exception as e:
        logger.error(f"Failed to delete Gateway API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


# ============================================================================
# Application Operations
# ============================================================================

@router.get("/applications", response_model=List[GatewayApplicationResponse])
@require_permission(Permission.APIS_READ)
async def list_gateway_applications(
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """List all applications registered in the Gateway.

    Requires: cpi-admin or tenant-admin role
    """
    try:
        apps = await gateway_service.list_applications(auth_token=token)
        return [
            GatewayApplicationResponse(
                id=app.get("id", ""),
                name=app.get("name", ""),
                description=app.get("description"),
                contactEmails=app.get("contactEmails", []),
            )
            for app in apps
        ]
    except Exception as e:
        logger.error(f"Failed to list Gateway applications: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


# ============================================================================
# Scope Operations
# ============================================================================

@router.get("/scopes", response_model=List[GatewayScopeResponse])
@require_permission(Permission.APIS_READ)
async def list_gateway_scopes(
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """List all OAuth scopes configured in the Gateway.

    Requires: cpi-admin role
    """
    try:
        scopes = await gateway_service.list_scopes(auth_token=token)
        return [
            GatewayScopeResponse(
                scopeName=scope.get("scopeName", scope.get("name", "")),
                scopeDescription=scope.get("scopeDescription", scope.get("description")),
                audience=scope.get("audience"),
            )
            for scope in scopes
        ]
    except Exception as e:
        logger.error(f"Failed to list Gateway scopes: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


# ============================================================================
# High-Level OIDC Configuration
# ============================================================================

@router.post("/configure-oidc", response_model=OIDCConfigResponse)
@require_permission(Permission.APIS_CREATE)
async def configure_api_oidc(
    config: OIDCConfigRequest,
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Configure OIDC authentication for an API in the Gateway.

    This high-level operation:
    1. Creates an OAuth strategy for the API
    2. Creates an application for the tenant
    3. Creates scope mappings with standardized naming

    Naming pattern: {AuthServer}:{TenantId}:{ApiName}:{Version}:{Scope}

    Requires: cpi-admin role
    """
    try:
        result = await gateway_service.configure_api_oidc(
            tenant_id=config.tenant_id,
            api_name=config.api_name,
            api_version=config.api_version,
            api_id=config.api_id,
            client_id=config.client_id,
            audience=config.audience,
            auth_server_alias=config.auth_server_alias,
            auth_token=token,
        )

        logger.info(
            f"User {user.username} configured OIDC for API {config.api_name} "
            f"(tenant: {config.tenant_id})"
        )

        return OIDCConfigResponse(
            success=True,
            strategy=result.get("strategy"),
            application=result.get("application"),
            scopes=result.get("scopes", []),
            message=f"OIDC configured for {config.api_name} v{config.api_version}",
        )

    except Exception as e:
        logger.error(f"Failed to configure OIDC for API {config.api_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def gateway_health(
    user: User = Depends(get_current_user),
    token: str = Depends(get_auth_token)
):
    """Check Gateway health status via OIDC proxy.

    This validates that:
    1. The Gateway-Admin-API proxy is accessible
    2. The user's JWT token is valid for Gateway operations
    """
    try:
        health = await gateway_service.health_check(auth_token=token)
        return {
            "status": "healthy",
            "proxy_mode": settings.GATEWAY_USE_OIDC_PROXY,
            "proxy_url": settings.GATEWAY_ADMIN_PROXY_URL if settings.GATEWAY_USE_OIDC_PROXY else None,
            "gateway_health": health,
        }
    except Exception as e:
        logger.error(f"Gateway health check failed: {e}")
        return {
            "status": "unhealthy",
            "proxy_mode": settings.GATEWAY_USE_OIDC_PROXY,
            "error": str(e),
        }
