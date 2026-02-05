"""Template Gateway Adapter — starting point for new adapter implementations.

Copy this directory, rename it, and implement the required methods.
See the README.md in this directory for the full guide.

Usage:
    1. cp -r src/adapters/template/ src/adapters/my_gateway/
    2. Rename TemplateGatewayAdapter to MyGatewayAdapter
    3. Implement the 6 REQUIRED methods
    4. Register in AdapterRegistry (see registry.py)
"""

from src.adapters.gateway_adapter_interface import AdapterResult, GatewayAdapterInterface


class TemplateGatewayAdapter(GatewayAdapterInterface):
    """Template adapter — copy and implement for your gateway.

    REQUIRED methods (must implement — currently raise NotImplementedError):
      - connect()       — Initialize connection to the gateway admin API
      - disconnect()    — Clean up connection resources
      - health_check()  — Verify gateway connectivity and readiness
      - sync_api()      — Create or update an API on the gateway
      - delete_api()    — Delete an API from the gateway
      - list_apis()     — List all APIs registered on the gateway

    OPTIONAL methods (return not-supported by default):
      - upsert_policy(), delete_policy(), list_policies()
      - provision_application(), deprovision_application(), list_applications()
      - upsert_auth_server(), upsert_strategy(), upsert_scope()
      - upsert_alias(), apply_config(), export_archive()
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        # TODO: Extract connection params from config
        # self._base_url = (config or {}).get("base_url", "")
        # self._admin_token = (config or {}).get("auth_config", {}).get("token", "")
        # self._client = None

    # --- REQUIRED: Lifecycle ---

    async def connect(self) -> None:
        """Initialize connection to the gateway admin API.

        Example: create an httpx.AsyncClient with base_url and auth headers.
        """
        raise NotImplementedError("Implement connect()")

    async def disconnect(self) -> None:
        """Clean up gateway connection resources.

        Example: close the httpx.AsyncClient.
        """
        raise NotImplementedError("Implement disconnect()")

    async def health_check(self) -> AdapterResult:
        """Verify gateway connectivity and readiness.

        Returns:
            AdapterResult(success=True, data={"status": "ok", ...}) if healthy
            AdapterResult(success=False, error="...") if not
        """
        raise NotImplementedError("Implement health_check()")

    # --- REQUIRED: APIs ---

    async def sync_api(
        self, api_spec: dict, tenant_id: str, auth_token: str | None = None
    ) -> AdapterResult:
        """Create or update an API from its specification.

        Args:
            api_spec: Dict from GatewayDeployment.desired_state containing:
                - spec_hash: SHA256 of the OpenAPI spec
                - version: API version string
                - api_name: Human-readable name
                - api_id: Unique identifier
                - tenant_id: Tenant owning this API
                - activated: Whether the API should accept traffic
            tenant_id: Tenant identifier
            auth_token: Optional auth token (gateway-specific)

        Returns:
            AdapterResult(success=True, resource_id="gateway-side-id")
            AdapterResult(success=False, error="...")

        MUST be idempotent: calling twice with same input = same result.
        """
        raise NotImplementedError("Implement sync_api()")

    async def delete_api(
        self, api_id: str, auth_token: str | None = None
    ) -> AdapterResult:
        """Delete an API by its gateway-side resource ID.

        Args:
            api_id: The gateway_resource_id returned by sync_api()
            auth_token: Optional auth token

        Returns:
            AdapterResult(success=True) if deleted or already absent
            AdapterResult(success=False, error="...") on failure
        """
        raise NotImplementedError("Implement delete_api()")

    async def list_apis(
        self, auth_token: str | None = None
    ) -> list[dict]:
        """List all APIs currently registered on the gateway.

        Returns:
            List of dicts, each containing at minimum:
                - id: Gateway-side resource ID
                - name: API name
                - spec_hash: Current spec hash (for drift detection)

        Used by the Sync Engine for drift detection.
        """
        raise NotImplementedError("Implement list_apis()")

    # --- OPTIONAL: Policies (default: not supported) ---

    async def upsert_policy(
        self, _policy_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def delete_policy(
        self, _policy_id: str, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def list_policies(
        self, _auth_token: str | None = None
    ) -> list[dict]:
        return []

    # --- OPTIONAL: Applications (OAuth clients) ---

    async def provision_application(
        self, _app_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def deprovision_application(
        self, _app_id: str, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def list_applications(
        self, _auth_token: str | None = None
    ) -> list[dict]:
        return []

    # --- OPTIONAL: Auth / OIDC ---

    async def upsert_auth_server(
        self, _auth_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def upsert_strategy(
        self, _strategy_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def upsert_scope(
        self, _scope_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    # --- OPTIONAL: Aliases / Config / Archive ---

    async def upsert_alias(
        self, _alias_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def apply_config(
        self, _config_spec: dict, _auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error="Not supported by this gateway")

    async def export_archive(
        self, _auth_token: str | None = None
    ) -> bytes:
        return b""
