"""
HTTP Client for Core API calls - ADR-001 Compliance.

Ce client remplace l'accès direct PostgreSQL dans le MCP Gateway.
Toutes les données doivent transiter par Core API.
"""
import httpx
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class CoreAPIClient:
    """Client HTTP pour appeler Core API.

    Remplace l'accès direct PostgreSQL selon ADR-001.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """
        Args:
            base_url: URL de base de Core API (ex: https://api.stoa.cab-i.com)
            timeout: Timeout en secondes pour les requêtes
        """
        if not base_url:
            raise ValueError("base_url must be configured")

        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        logger.info(f"CoreAPIClient initialized with base_url: {self.base_url}")

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None
    ) -> dict:
        """Make authenticated request to Core API."""
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Core API error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Core API request failed: {e}")
                raise

    # =========================================================================
    # TENANTS
    # =========================================================================

    async def get_tenant(self, tenant_id: str, token: str) -> dict:
        """Get tenant by ID."""
        return await self._request("GET", f"/v1/tenants/{tenant_id}", token)

    async def list_tenants(self, token: str) -> List[dict]:
        """List all accessible tenants."""
        result = await self._request("GET", "/v1/tenants", token)
        return result.get("items", result) if isinstance(result, dict) else result

    async def get_tenant_by_slug(self, slug: str, token: str) -> Optional[dict]:
        """Get tenant by slug."""
        tenants = await self.list_tenants(token)
        for tenant in tenants:
            if tenant.get("slug") == slug:
                return tenant
        return None

    # =========================================================================
    # MCP SUBSCRIPTIONS
    # =========================================================================

    async def list_mcp_subscriptions(
        self,
        token: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[dict]:
        """List MCP subscriptions with optional filters."""
        params = {}
        if user_id:
            params["user_id"] = user_id
        if tenant_id:
            params["tenant_id"] = tenant_id
        if status:
            params["status"] = status

        result = await self._request("GET", "/v1/mcp/subscriptions", token, params=params)
        return result.get("items", result) if isinstance(result, dict) else result

    async def get_mcp_subscription(self, subscription_id: str, token: str) -> dict:
        """Get MCP subscription by ID."""
        return await self._request("GET", f"/v1/mcp/subscriptions/{subscription_id}", token)

    async def create_mcp_subscription(self, data: dict, token: str) -> dict:
        """Create MCP subscription."""
        return await self._request("POST", "/v1/mcp/subscriptions", token, json=data)

    async def delete_mcp_subscription(self, subscription_id: str, token: str) -> dict:
        """Delete MCP subscription."""
        return await self._request("DELETE", f"/v1/mcp/subscriptions/{subscription_id}", token)

    async def reveal_api_key(
        self,
        subscription_id: str,
        token: str,
        totp_code: Optional[str] = None
    ) -> dict:
        """Reveal API key (requires 2FA if configured)."""
        data = {"totp_code": totp_code} if totp_code else {}
        return await self._request(
            "POST",
            f"/v1/mcp/subscriptions/{subscription_id}/reveal-key",
            token,
            json=data
        )

    async def rotate_api_key(
        self,
        subscription_id: str,
        token: str,
        grace_period_hours: int = 24
    ) -> dict:
        """Rotate API key with grace period."""
        return await self._request(
            "POST",
            f"/v1/mcp/subscriptions/{subscription_id}/rotate-key",
            token,
            json={"grace_period_hours": grace_period_hours}
        )

    # =========================================================================
    # MCP SERVERS
    # =========================================================================

    async def list_mcp_servers(
        self,
        token: str,
        tenant_id: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[dict]:
        """List available MCP servers."""
        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id
        if category:
            params["category"] = category

        result = await self._request("GET", "/v1/mcp/servers", token, params=params)
        return result.get("items", result) if isinstance(result, dict) else result

    async def get_mcp_server(self, server_id: str, token: str) -> dict:
        """Get MCP server by ID."""
        return await self._request("GET", f"/v1/mcp/servers/{server_id}", token)

    # =========================================================================
    # MCP TOOLS (via proxy)
    # =========================================================================

    async def list_tools(
        self,
        token: str,
        tenant_id: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[dict]:
        """List available MCP tools."""
        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id
        if category:
            params["category"] = category

        result = await self._request("GET", "/v1/mcp/tools", token, params=params)
        return result.get("items", result) if isinstance(result, dict) else result

    async def get_tool(self, tool_name: str, token: str) -> dict:
        """Get tool by name."""
        return await self._request("GET", f"/v1/mcp/tools/{tool_name}", token)

    # =========================================================================
    # CATALOG (APIs)
    # =========================================================================

    async def list_apis(
        self,
        token: str,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[dict]:
        """List APIs from catalog."""
        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id
        if status:
            params["status"] = status
        if category:
            params["category"] = category

        result = await self._request("GET", "/v1/catalog/apis", token, params=params)
        return result.get("items", result) if isinstance(result, dict) else result

    async def get_api(self, api_id: str, token: str) -> dict:
        """Get API by ID."""
        return await self._request("GET", f"/v1/catalog/apis/{api_id}", token)

    async def get_api_spec(self, api_id: str, token: str) -> dict:
        """Get OpenAPI spec for an API."""
        return await self._request("GET", f"/v1/catalog/apis/{api_id}/spec", token)

    # =========================================================================
    # USERS
    # =========================================================================

    async def get_user(self, user_id: str, token: str) -> dict:
        """Get user by ID."""
        return await self._request("GET", f"/v1/users/{user_id}", token)

    async def get_current_user(self, token: str) -> dict:
        """Get current authenticated user."""
        return await self._request("GET", "/v1/users/me", token)

    # =========================================================================
    # AUDIT
    # =========================================================================

    async def create_audit_log(self, data: dict, token: str) -> dict:
        """Create audit log entry."""
        return await self._request("POST", "/v1/audit/logs", token, json=data)

    # =========================================================================
    # HEALTH
    # =========================================================================

    async def health_check(self) -> bool:
        """Check if Core API is healthy (no auth required)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


# =============================================================================
# SINGLETON
# =============================================================================

_client: Optional[CoreAPIClient] = None


def init_core_api_client(base_url: str, timeout: float = 30.0) -> CoreAPIClient:
    """Initialize the CoreAPIClient singleton."""
    global _client
    _client = CoreAPIClient(base_url, timeout)
    return _client


def get_core_api_client() -> CoreAPIClient:
    """Get the CoreAPIClient singleton.

    Raises:
        RuntimeError: If client not initialized
    """
    if _client is None:
        raise RuntimeError(
            "CoreAPIClient not initialized. "
            "Call init_core_api_client() first or check CONTROL_PLANE_API_URL config."
        )
    return _client


def shutdown_core_api_client() -> None:
    """Shutdown the CoreAPIClient (cleanup)."""
    global _client
    if _client:
        logger.info("CoreAPIClient shutdown")
    _client = None
