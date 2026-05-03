"""Ports and DTOs for the API lifecycle service.

The lifecycle core depends on these protocols, not directly on SQLAlchemy,
gateway clients, portal clients, or audit storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from src.models.catalog import APICatalog
from src.models.gateway_deployment import GatewayDeployment
from src.models.promotion import Promotion


@dataclass(frozen=True)
class LifecycleActor:
    actor_id: str | None
    email: str | None
    username: str | None
    actor_type: str = "user"


@dataclass(frozen=True)
class CreateApiDraftCommand:
    tenant_id: str
    name: str
    display_name: str
    version: str
    description: str
    backend_url: str
    openapi_spec: str | dict[str, Any] | None = None
    spec_reference: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    owner_team: str | None = None


@dataclass(frozen=True)
class ValidateApiDraftCommand:
    tenant_id: str
    api_id: str
    reason: str | None = None


@dataclass(frozen=True)
class DeployApiCommand:
    tenant_id: str
    api_id: str
    environment: str
    gateway_instance_id: UUID | None = None
    force: bool = False


@dataclass(frozen=True)
class PublishApiCommand:
    tenant_id: str
    api_id: str
    environment: str
    gateway_instance_id: UUID | None = None
    force: bool = False


@dataclass(frozen=True)
class PromoteApiCommand:
    tenant_id: str
    api_id: str
    source_environment: str
    target_environment: str
    source_gateway_instance_id: UUID | None = None
    target_gateway_instance_id: UUID | None = None
    force: bool = False


@dataclass(frozen=True)
class DraftValidationResult:
    valid: bool
    code: str
    message: str
    spec_source: str
    spec_format: str | None = None
    spec_version: str | None = None
    title: str | None = None
    version: str | None = None
    path_count: int = 0
    operation_count: int = 0
    validated_at: datetime | None = None


@dataclass(frozen=True)
class ApiDraftValidationOutcome:
    tenant_id: str
    api_id: str
    status: str
    validation: DraftValidationResult
    lifecycle_state: ApiLifecycleState


@dataclass(frozen=True)
class GatewayTarget:
    id: UUID
    name: str
    display_name: str
    gateway_type: str
    environment: str
    tenant_id: str | None
    enabled: bool
    public_url: str | None = None


@dataclass(frozen=True)
class ApiDeploymentRequestOutcome:
    tenant_id: str
    api_id: str
    environment: str
    gateway_instance_id: UUID
    deployment_id: UUID
    deployment_status: str
    action: str
    lifecycle_state: ApiLifecycleState


@dataclass(frozen=True)
class PortalPublicationState:
    environment: str
    gateway_instance_id: UUID
    deployment_id: UUID
    publication_status: str
    result: str
    spec_hash: str
    published_at: datetime


@dataclass(frozen=True)
class PortalLifecycleState:
    published: bool = False
    status: str = "not_published"
    publications: list[PortalPublicationState] = field(default_factory=list)
    last_result: str | None = None
    last_environment: str | None = None
    last_gateway_instance_id: UUID | None = None
    last_deployment_id: UUID | None = None
    last_published_at: datetime | None = None


@dataclass(frozen=True)
class ApiPortalPublicationOutcome:
    tenant_id: str
    api_id: str
    environment: str
    gateway_instance_id: UUID
    deployment_id: UUID
    publication_status: str
    portal_published: bool
    result: str
    lifecycle_state: ApiLifecycleState


@dataclass(frozen=True)
class ApiPromotionRequestOutcome:
    tenant_id: str
    api_id: str
    promotion_id: UUID
    source_environment: str
    target_environment: str
    source_gateway_instance_id: UUID
    target_gateway_instance_id: UUID
    target_deployment_id: UUID
    promotion_status: str
    deployment_status: str
    result: str
    lifecycle_state: ApiLifecycleState


@dataclass(frozen=True)
class ApiSpecState:
    source: str
    has_openapi_spec: bool
    git_path: str | None = None
    git_commit_sha: str | None = None
    reference: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class GatewayDeploymentState:
    id: UUID
    environment: str
    gateway_instance_id: UUID
    gateway_name: str
    gateway_type: str
    sync_status: str
    desired_generation: int
    synced_generation: int
    gateway_resource_id: str | None = None
    public_url: str | None = None
    sync_error: str | None = None
    last_sync_success: datetime | None = None


@dataclass(frozen=True)
class PromotionState:
    id: UUID
    source_environment: str
    target_environment: str
    status: str
    message: str
    requested_by: str
    approved_by: str | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ApiLifecycleState:
    catalog_id: UUID
    tenant_id: str
    api_id: str
    api_name: str
    display_name: str
    version: str
    description: str
    backend_url: str
    catalog_status: str
    lifecycle_phase: str
    portal_published: bool
    tags: list[str]
    spec: ApiSpecState
    deployments: list[GatewayDeploymentState]
    promotions: list[PromotionState]
    last_error: str | None = None
    portal: PortalLifecycleState = field(default_factory=PortalLifecycleState)


@dataclass(frozen=True)
class GatewayDeploymentSnapshot:
    id: UUID
    environment: str
    gateway_instance_id: UUID
    gateway_name: str
    gateway_type: str
    sync_status: str
    desired_generation: int
    synced_generation: int
    gateway_resource_id: str | None = None
    public_url: str | None = None
    sync_error: str | None = None
    last_sync_success: datetime | None = None


@dataclass(frozen=True)
class PromotionSnapshot:
    id: UUID
    source_environment: str
    target_environment: str
    status: str
    message: str
    requested_by: str
    approved_by: str | None = None
    completed_at: datetime | None = None


class ApiLifecycleRepository(Protocol):
    async def get_api_by_id(self, tenant_id: str, api_id: str) -> APICatalog | None:
        """Return an active API catalog row."""

    async def get_api_by_name_version(self, tenant_id: str, api_name: str, version: str) -> APICatalog | None:
        """Return an active API catalog row by name and version."""

    async def create_api_catalog(self, api: APICatalog) -> APICatalog:
        """Persist a new API catalog row."""

    async def save_api_catalog(self, api: APICatalog) -> APICatalog:
        """Persist changes to an existing API catalog row."""

    async def list_gateway_deployments(self, api_catalog_id: UUID) -> list[GatewayDeploymentSnapshot]:
        """Return runtime deployment state for an API catalog row."""

    async def get_gateway_target(self, tenant_id: str, gateway_instance_id: UUID) -> GatewayTarget | None:
        """Return one visible gateway target for a tenant."""

    async def list_gateway_targets(self, tenant_id: str, environment: str) -> list[GatewayTarget]:
        """Return visible gateway targets for a tenant and environment."""

    async def get_gateway_deployment(self, api_catalog_id: UUID, gateway_instance_id: UUID) -> GatewayDeployment | None:
        """Return the runtime deployment row for one API/gateway target."""

    async def create_gateway_deployment(self, deployment: GatewayDeployment) -> GatewayDeployment:
        """Create a runtime deployment row."""

    async def save_gateway_deployment(self, deployment: GatewayDeployment) -> GatewayDeployment:
        """Persist changes to a runtime deployment row."""

    async def list_promotions(self, tenant_id: str, api_id: str) -> list[PromotionSnapshot]:
        """Return promotion state for an API."""

    async def get_active_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
    ) -> Promotion | None:
        """Return one active promotion for a source/target lane."""

    async def get_latest_promoted_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
    ) -> Promotion | None:
        """Return the most recent completed promotion for a source/target lane."""

    async def get_active_promotion_for_target_deployment(
        self,
        tenant_id: str,
        api_id: str,
        target_environment: str,
        target_deployment_id: UUID,
    ) -> Promotion | None:
        """Return the active promotion that owns a target GatewayDeployment."""

    async def create_promotion(self, promotion: Promotion) -> Promotion:
        """Create a promotion row."""

    async def save_promotion(self, promotion: Promotion) -> Promotion:
        """Persist promotion changes."""


class LifecycleAuditSink(Protocol):
    async def record_transition(
        self,
        *,
        tenant_id: str,
        actor: LifecycleActor,
        action: str,
        resource_id: str,
        resource_name: str,
        details: dict[str, Any],
        outcome: str = "success",
        status_code: int = 200,
        method: str = "POST",
        path: str | None = None,
    ) -> None:
        """Persist a lifecycle transition audit event."""


class PortalPublisherPort(Protocol):
    async def publish(
        self,
        *,
        api: APICatalog,
        publication: PortalPublicationState,
    ) -> APICatalog:
        """Persist the portal publication state for one API."""
