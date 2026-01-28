# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Gateway Admin Service for webMethods API Gateway operations.

This service provides methods to manage APIs, applications, and policies
in the webMethods API Gateway. It supports two authentication modes:

1. OIDC Proxy (recommended): Uses the Gateway-Admin-API proxy with JWT token forwarding
2. Basic Auth (legacy): Direct connection to Gateway admin API with username/password

The OIDC proxy mode is preferred for production as it:
- Eliminates the need to store admin credentials in the Control-Plane API
- Leverages the user's JWT token for authentication
- Provides audit trail through Gateway logs
- Supports role-based access control via Keycloak
"""
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class GatewayAdminService:
    """Service for webMethods Gateway administration operations.

    Supports both OIDC proxy mode (token forwarding) and Basic Auth mode.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._use_proxy = settings.GATEWAY_USE_OIDC_PROXY

    async def connect(self):
        """Initialize Gateway connection (for Basic Auth mode only)."""
        if not self._use_proxy:
            # Basic Auth mode - create persistent client
            self._client = httpx.AsyncClient(
                base_url=f"{settings.GATEWAY_URL}/rest/apigateway",
                auth=(settings.GATEWAY_ADMIN_USER, settings.GATEWAY_ADMIN_PASSWORD),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
                verify=True,
            )
            logger.info(f"Connected to Gateway (Basic Auth) at {settings.GATEWAY_URL}")
        else:
            logger.info(f"Gateway service configured for OIDC proxy at {settings.GATEWAY_ADMIN_PROXY_URL}")

    async def disconnect(self):
        """Close Gateway connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @asynccontextmanager
    async def _get_client(self, auth_token: Optional[str] = None):
        """Get HTTP client based on authentication mode.

        Args:
            auth_token: JWT token for OIDC proxy mode (required if use_proxy=True)

        Yields:
            Configured httpx.AsyncClient
        """
        if self._use_proxy:
            if not auth_token:
                raise ValueError("JWT token required for OIDC proxy mode")

            # Create per-request client with Bearer token
            async with httpx.AsyncClient(
                base_url=settings.GATEWAY_ADMIN_PROXY_URL,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
                verify=True,
            ) as client:
                yield client
        else:
            # Use persistent Basic Auth client
            if not self._client:
                raise RuntimeError("Gateway not connected. Call connect() first.")
            yield self._client

    async def _request(
        self,
        method: str,
        path: str,
        auth_token: Optional[str] = None,
        **kwargs
    ) -> dict:
        """Make request to Gateway Admin API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., /apis, /applications)
            auth_token: JWT token for OIDC proxy mode
            **kwargs: Additional arguments passed to httpx.request

        Returns:
            JSON response as dict
        """
        async with self._get_client(auth_token) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()

            # Handle empty responses
            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

    # =========================================================================
    # API Operations
    # =========================================================================

    async def list_apis(self, auth_token: Optional[str] = None) -> List[dict]:
        """List all APIs in the Gateway.

        Args:
            auth_token: JWT token for OIDC proxy mode

        Returns:
            List of API objects
        """
        result = await self._request("GET", "/apis", auth_token=auth_token)
        return result.get("apiResponse", [])

    async def get_api(self, api_id: str, auth_token: Optional[str] = None) -> dict:
        """Get API by ID.

        Args:
            api_id: API identifier
            auth_token: JWT token for OIDC proxy mode

        Returns:
            API object
        """
        result = await self._request("GET", f"/apis/{api_id}", auth_token=auth_token)
        return result.get("apiResponse", {}).get("api", {})

    async def activate_api(self, api_id: str, auth_token: Optional[str] = None) -> dict:
        """Activate an API.

        Args:
            api_id: API identifier
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Activation response
        """
        result = await self._request("PUT", f"/apis/{api_id}/activate", auth_token=auth_token)
        logger.info(f"Activated API {api_id}")
        return result

    async def deactivate_api(self, api_id: str, auth_token: Optional[str] = None) -> dict:
        """Deactivate an API.

        Args:
            api_id: API identifier
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Deactivation response
        """
        result = await self._request("PUT", f"/apis/{api_id}/deactivate", auth_token=auth_token)
        logger.info(f"Deactivated API {api_id}")
        return result

    async def delete_api(self, api_id: str, auth_token: Optional[str] = None) -> bool:
        """Delete an API.

        Args:
            api_id: API identifier
            auth_token: JWT token for OIDC proxy mode

        Returns:
            True if successful
        """
        await self._request("DELETE", f"/apis/{api_id}", auth_token=auth_token)
        logger.info(f"Deleted API {api_id}")
        return True

    async def import_api(
        self,
        api_name: str,
        api_version: str,
        openapi_url: Optional[str] = None,
        openapi_spec: Optional[Dict[str, Any]] = None,
        api_type: str = "openapi",
        auth_token: Optional[str] = None
    ) -> dict:
        """Import an API from OpenAPI specification.

        Args:
            api_name: Name for the API
            api_version: Version of the API
            openapi_url: URL to fetch OpenAPI spec from (mutually exclusive with openapi_spec)
            openapi_spec: OpenAPI spec as dict object (mutually exclusive with openapi_url)
            api_type: API type (openapi, swagger, raml, wsdl)
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Created API object with id, apiName, apiVersion, etc.
        """
        if not openapi_url and not openapi_spec:
            raise ValueError("Either openapi_url or openapi_spec must be provided")

        payload = {
            "apiName": api_name,
            "apiVersion": api_version,
            "type": api_type,
        }

        if openapi_url:
            payload["url"] = openapi_url
        elif openapi_spec:
            # Gateway expects apiDefinition as a JSON object (not string)
            payload["apiDefinition"] = openapi_spec

        result = await self._request("POST", "/apis", auth_token=auth_token, json=payload)
        api_id = result.get("apiResponse", {}).get("api", {}).get("id", "")
        logger.info(f"Imported API {api_name} v{api_version} with ID {api_id}")
        return result

    # =========================================================================
    # Application Operations
    # =========================================================================

    async def list_applications(self, auth_token: Optional[str] = None) -> List[dict]:
        """List all applications in the Gateway.

        Args:
            auth_token: JWT token for OIDC proxy mode

        Returns:
            List of application objects
        """
        result = await self._request("GET", "/applications", auth_token=auth_token)
        return result.get("applications", [])

    async def get_application(self, app_id: str, auth_token: Optional[str] = None) -> dict:
        """Get application by ID.

        Args:
            app_id: Application identifier
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Application object
        """
        return await self._request("GET", f"/applications/{app_id}", auth_token=auth_token)

    async def create_application(
        self,
        name: str,
        description: str = "",
        contact_emails: List[str] = None,
        auth_token: Optional[str] = None
    ) -> dict:
        """Create a new application.

        Args:
            name: Application name
            description: Application description
            contact_emails: List of contact email addresses
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Created application object
        """
        payload = {
            "name": name,
            "description": description,
            "contactEmails": contact_emails or ["admin@cab-i.com"],
        }
        result = await self._request("POST", "/applications", auth_token=auth_token, json=payload)
        logger.info(f"Created application {name}")
        return result

    # =========================================================================
    # Alias Operations
    # =========================================================================

    async def list_aliases(self, auth_token: Optional[str] = None) -> List[dict]:
        """List all aliases in the Gateway.

        Args:
            auth_token: JWT token for OIDC proxy mode

        Returns:
            List of alias objects
        """
        result = await self._request("GET", "/alias", auth_token=auth_token)
        return result.get("alias", [])

    async def create_endpoint_alias(
        self,
        name: str,
        endpoint_uri: str,
        description: str = "",
        auth_token: Optional[str] = None
    ) -> dict:
        """Create an endpoint alias.

        Args:
            name: Alias name
            endpoint_uri: Backend endpoint URI
            description: Alias description
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Created alias object
        """
        payload = {
            "name": name,
            "description": description,
            "type": "endpoint",
            "endPointURI": endpoint_uri,
            "connectionTimeout": 30,
            "readTimeout": 60,
            "optimizationTechnique": "None",
            "passSecurityHeaders": True,
        }
        result = await self._request("POST", "/alias", auth_token=auth_token, json=payload)
        logger.info(f"Created endpoint alias {name} -> {endpoint_uri}")
        return result

    # =========================================================================
    # Scope Operations
    # =========================================================================

    async def list_scopes(self, auth_token: Optional[str] = None) -> List[dict]:
        """List all OAuth scopes in the Gateway.

        Args:
            auth_token: JWT token for OIDC proxy mode

        Returns:
            List of scope objects
        """
        result = await self._request("GET", "/scopes", auth_token=auth_token)
        return result.get("scopes", [])

    async def create_scope_mapping(
        self,
        scope_name: str,
        description: str,
        audience: str,
        api_ids: List[str],
        auth_server_alias: str = "KeycloakOIDC",
        keycloak_scope: str = "openid",
        auth_token: Optional[str] = None
    ) -> dict:
        """Create an OAuth scope mapping.

        Args:
            scope_name: Full scope name (e.g., KeycloakOIDC:tenant:api:version:scope)
            description: Scope description
            audience: JWT audience claim value
            api_ids: List of API IDs this scope applies to
            auth_server_alias: Authorization server alias name
            keycloak_scope: Keycloak scope name
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Created scope object
        """
        payload = {
            "scopeName": scope_name,
            "scopeDescription": description,
            "audience": audience,
            "apiScopes": api_ids,
            "requiredAuthScopes": [
                {
                    "authServerAlias": auth_server_alias,
                    "scopeName": keycloak_scope
                }
            ]
        }
        result = await self._request("POST", "/scopes", auth_token=auth_token, json=payload)
        logger.info(f"Created scope mapping {scope_name}")
        return result

    # =========================================================================
    # Strategy Operations
    # =========================================================================

    async def list_strategies(self, auth_token: Optional[str] = None) -> List[dict]:
        """List all authentication strategies in the Gateway.

        Args:
            auth_token: JWT token for OIDC proxy mode

        Returns:
            List of strategy objects
        """
        result = await self._request("GET", "/strategies", auth_token=auth_token)
        return result.get("strategies", [])

    async def create_oauth_strategy(
        self,
        name: str,
        auth_server_alias: str,
        client_id: str,
        audience: str,
        description: str = "",
        auth_token: Optional[str] = None
    ) -> dict:
        """Create an OAuth2 authentication strategy.

        Args:
            name: Strategy name
            auth_server_alias: Authorization server alias name
            client_id: Client ID for the strategy
            audience: Expected JWT audience
            description: Strategy description
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Created strategy object
        """
        payload = {
            "name": name,
            "description": description,
            "type": "OAUTH2",
            "authServerAlias": auth_server_alias,
            "clientId": client_id,
            "audience": audience,
        }
        result = await self._request("POST", "/strategies", auth_token=auth_token, json=payload)
        logger.info(f"Created OAuth strategy {name}")
        return result

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self, auth_token: Optional[str] = None) -> dict:
        """Check Gateway health status.

        Args:
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Health status response
        """
        return await self._request("GET", "/health", auth_token=auth_token)

    # =========================================================================
    # High-Level Operations
    # =========================================================================

    async def configure_api_oidc(
        self,
        tenant_id: str,
        api_name: str,
        api_version: str,
        api_id: str,
        client_id: str,
        audience: str = "control-plane-api",
        auth_server_alias: str = "KeycloakOIDC",
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Configure OIDC authentication for an API.

        Creates strategy, application, associates them, and creates scope mappings.
        Uses the standardized naming pattern: {AuthServer}:{Tenant}:{ApiName}:{Version}:{Scope}

        Args:
            tenant_id: Tenant identifier
            api_name: API name
            api_version: API version
            api_id: API identifier in Gateway
            client_id: Keycloak client ID
            audience: Expected JWT audience
            auth_server_alias: Authorization server alias name
            auth_token: JWT token for OIDC proxy mode

        Returns:
            Configuration result with created resources
        """
        result = {
            "strategy": None,
            "application": None,
            "scopes": [],
        }

        # 1. Create OAuth strategy
        strategy_name = f"OIDC-{tenant_id}-{api_name}"
        try:
            strategy = await self.create_oauth_strategy(
                name=strategy_name,
                auth_server_alias=auth_server_alias,
                client_id=client_id,
                audience=audience,
                description=f"OIDC strategy for {api_name} - Tenant {tenant_id}",
                auth_token=auth_token,
            )
            result["strategy"] = strategy
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 409:  # 409 = already exists
                raise
            logger.info(f"Strategy {strategy_name} already exists")

        # 2. Create application
        app_name = f"{tenant_id}-{api_name}"
        try:
            app = await self.create_application(
                name=app_name,
                description=f"Application for {api_name} - Tenant {tenant_id}",
                auth_token=auth_token,
            )
            result["application"] = app
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 409:
                raise
            logger.info(f"Application {app_name} already exists")

        # 3. Create scope mappings with standardized naming
        scope_prefix = f"{auth_server_alias}:{tenant_id}:{api_name}:{api_version}"
        scopes_to_create = ["openid", "profile", "email", "roles"]

        for scope in scopes_to_create:
            scope_name = f"{scope_prefix}:{scope}"
            try:
                scope_obj = await self.create_scope_mapping(
                    scope_name=scope_name,
                    description=f"{scope.capitalize()} scope for {api_name} v{api_version} - Tenant {tenant_id}",
                    audience=audience,
                    api_ids=[api_id],
                    auth_server_alias=auth_server_alias,
                    keycloak_scope=scope,
                    auth_token=auth_token,
                )
                result["scopes"].append(scope_obj)
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 409:
                    raise
                logger.info(f"Scope {scope_name} already exists")

        logger.info(f"Configured OIDC for API {api_name} (tenant: {tenant_id})")
        return result


# Global instance
gateway_service = GatewayAdminService()
