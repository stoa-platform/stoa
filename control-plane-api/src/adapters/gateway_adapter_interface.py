"""Abstract Gateway Adapter Interface for STOA Platform.

Defines the contract that any API gateway must implement to be fully
pilotable by STOA's GitOps reconciliation pipeline. The interface covers
the complete lifecycle: APIs, policies, applications, OIDC auth, aliases,
configuration, and backup/archive.

First implementation: webMethods API Gateway (see adapters/webmethods/).
Planned: Kong, Apigee, AWS API Gateway.

See ADR-027 for the architectural decision and CIR research context.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdapterResult:
    """Standardized result from any adapter operation."""

    success: bool
    resource_id: Optional[str] = None
    data: Optional[dict] = field(default_factory=dict)
    error: Optional[str] = None


class GatewayAdapterInterface(ABC):
    """Abstract interface for gateway orchestration.

    Any API gateway that implements this contract can be fully
    piloted by STOA's GitOps reconciliation pipeline. All operations
    MUST be idempotent: calling the same operation twice with the
    same input must produce the same result without side effects.
    """

    # --- Lifecycle ---

    @abstractmethod
    async def health_check(self) -> AdapterResult:
        """Verify gateway connectivity and readiness."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to the gateway (if needed)."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up gateway connection resources."""
        ...

    # --- APIs ---

    @abstractmethod
    async def sync_api(
        self, api_spec: dict, tenant_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create or update an API from its specification."""
        ...

    @abstractmethod
    async def delete_api(
        self, api_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Delete an API by its gateway-side ID."""
        ...

    @abstractmethod
    async def list_apis(
        self, auth_token: Optional[str] = None
    ) -> list[dict]:
        """List all APIs currently registered in the gateway."""
        ...

    # --- Policies ---

    @abstractmethod
    async def upsert_policy(
        self, policy_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create or update a policy (CORS, rate-limit, logging, JWT, etc.)."""
        ...

    @abstractmethod
    async def delete_policy(
        self, policy_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Delete a policy by its gateway-side ID."""
        ...

    @abstractmethod
    async def list_policies(
        self, auth_token: Optional[str] = None
    ) -> list[dict]:
        """List all policies in the gateway."""
        ...

    # --- Applications (OAuth clients) ---

    @abstractmethod
    async def provision_application(
        self, app_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create an application and associate it with APIs."""
        ...

    @abstractmethod
    async def deprovision_application(
        self, app_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Remove an application from the gateway."""
        ...

    @abstractmethod
    async def list_applications(
        self, auth_token: Optional[str] = None
    ) -> list[dict]:
        """List all applications in the gateway."""
        ...

    # --- Auth / OIDC ---

    @abstractmethod
    async def upsert_auth_server(
        self, auth_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create or update an authentication server alias (e.g. Keycloak OIDC)."""
        ...

    @abstractmethod
    async def upsert_strategy(
        self, strategy_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create or update an authentication strategy."""
        ...

    @abstractmethod
    async def upsert_scope(
        self, scope_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create or update an OAuth scope mapping."""
        ...

    # --- Aliases ---

    @abstractmethod
    async def upsert_alias(
        self, alias_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Create or update a backend endpoint alias."""
        ...

    # --- Configuration ---

    @abstractmethod
    async def apply_config(
        self, config_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        """Apply global gateway configuration (error templates, JWT issuer, etc.)."""
        ...

    # --- Backup / Archive ---

    @abstractmethod
    async def export_archive(
        self, auth_token: Optional[str] = None
    ) -> bytes:
        """Export full gateway state as a portable archive (ZIP)."""
        ...
