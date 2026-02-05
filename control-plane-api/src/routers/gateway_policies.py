"""API routes for gateway policy management (cpi-admin, tenant-admin)."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyScope, PolicyType
from src.repositories.gateway_policy import GatewayPolicyBindingRepository, GatewayPolicyRepository
from src.schemas.policy import (
    GatewayPolicyCreate,
    GatewayPolicyResponse,
    GatewayPolicyUpdate,
    PolicyBindingCreate,
    PolicyBindingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/policies",
    tags=["Gateway Policies"],
)


@router.post("", response_model=GatewayPolicyResponse, status_code=201)
async def create_policy(
    data: GatewayPolicyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Create a new gateway policy."""
    repo = GatewayPolicyRepository(db)
    policy = GatewayPolicy(
        name=data.name,
        description=data.description,
        policy_type=PolicyType(data.policy_type),
        tenant_id=data.tenant_id,
        scope=PolicyScope(data.scope),
        config=data.config,
        priority=data.priority,
        enabled=data.enabled,
    )
    policy = await repo.create(policy)
    await db.commit()
    await db.refresh(policy, attribute_names=["bindings"])
    return _to_response(policy)


@router.get("", response_model=list[GatewayPolicyResponse])
async def list_policies(
    tenant_id: str | None = Query(None, description="Filter by tenant"),
    policy_type: str | None = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """List gateway policies."""
    repo = GatewayPolicyRepository(db)
    pt = PolicyType(policy_type) if policy_type else None
    policies = await repo.list_all(tenant_id=tenant_id, policy_type=pt)
    return [_to_response(p) for p in policies]


@router.get("/{policy_id}", response_model=GatewayPolicyResponse)
async def get_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Get policy details."""
    repo = GatewayPolicyRepository(db)
    policy = await repo.get_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return _to_response(policy)


@router.put("/{policy_id}", response_model=GatewayPolicyResponse)
async def update_policy(
    policy_id: UUID,
    data: GatewayPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Update a gateway policy."""
    repo = GatewayPolicyRepository(db)
    policy = await repo.get_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if data.name is not None:
        policy.name = data.name
    if data.description is not None:
        policy.description = data.description
    if data.config is not None:
        policy.config = data.config
    if data.priority is not None:
        policy.priority = data.priority
    if data.enabled is not None:
        policy.enabled = data.enabled

    await repo.update(policy)
    await db.commit()
    await db.refresh(policy, attribute_names=["bindings"])
    return _to_response(policy)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Delete a policy (cascades to bindings)."""
    repo = GatewayPolicyRepository(db)
    policy = await repo.get_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    await repo.delete(policy)
    await db.commit()


@router.post("/bindings", response_model=PolicyBindingResponse, status_code=201)
async def create_binding(
    data: PolicyBindingCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Create a policy binding."""
    # Verify policy exists
    policy_repo = GatewayPolicyRepository(db)
    policy = await policy_repo.get_by_id(data.policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    binding_repo = GatewayPolicyBindingRepository(db)
    binding = GatewayPolicyBinding(
        policy_id=data.policy_id,
        api_catalog_id=data.api_catalog_id,
        gateway_instance_id=data.gateway_instance_id,
        tenant_id=data.tenant_id,
        enabled=data.enabled,
    )
    binding = await binding_repo.create(binding)
    await db.commit()
    await db.refresh(binding)
    return binding


@router.delete("/bindings/{binding_id}", status_code=204)
async def delete_binding(
    binding_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Remove a policy binding."""
    binding_repo = GatewayPolicyBindingRepository(db)
    binding = await binding_repo.get_by_id(binding_id)
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    await binding_repo.delete(binding)
    await db.commit()


@router.get("/{policy_id}/bindings", response_model=list[PolicyBindingResponse])
async def list_bindings(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """List bindings for a policy."""
    # Verify policy exists
    policy_repo = GatewayPolicyRepository(db)
    policy = await policy_repo.get_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    binding_repo = GatewayPolicyBindingRepository(db)
    bindings = await binding_repo.list_by_policy(policy_id)
    return bindings


def _to_response(policy: GatewayPolicy) -> GatewayPolicyResponse:
    """Convert a GatewayPolicy model to response schema with binding count."""
    return GatewayPolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        policy_type=policy.policy_type.value if policy.policy_type else "",
        tenant_id=policy.tenant_id,
        scope=policy.scope.value if policy.scope else "api",
        config=policy.config or {},
        priority=policy.priority,
        enabled=policy.enabled,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        binding_count=len(policy.bindings) if policy.bindings else 0,
    )
