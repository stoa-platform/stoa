"""
Contracts and Protocol Bindings Router

Endpoints for managing Universal API Contracts (UAC) and their protocol bindings.
The Protocol Switcher UI uses these endpoints to enable/disable bindings.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.registry import AdapterRegistry
from src.auth.dependencies import User, get_current_user
from src.config import settings
from src.database import get_db
from src.logging_config import get_logger
from src.models.contract import (
    Contract,
    McpGeneratedTool,
    ProtocolBinding,
    ProtocolType,
)
from src.models.gateway_instance import (
    GatewayInstance,
    GatewayInstanceStatus,
    GatewayType,
)
from src.schemas.contract import (
    BindingsListResponse,
    ContractCreate,
    ContractDeprecationInfo,
    ContractListResponse,
    ContractResponse,
    ContractUpdate,
    ContractVersionsResponse,
    ContractVersionSummary,
    DeprecateContractRequest,
    DisableBindingResponse,
    EnableBindingRequest,
    EnableBindingResponse,
    McpToolDefinition,
    McpToolsGenerateResponse,
    McpToolsListResponse,
    ProtocolBindingResponse,
    TenantToolsResponse,
)
from src.services.cache_service import contract_cache
from src.services.uac_tool_generator import UacToolGenerator

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/contracts", tags=["Contracts"])


# ============ Helper Functions ============


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to the specified tenant."""
    if "cpi-admin" in (user.roles or []):
        return True
    return user.tenant_id == tenant_id


async def _get_or_create_default_bindings(
    db: AsyncSession, contract: Contract
) -> list[ProtocolBinding]:
    """Get existing bindings or create default disabled bindings for all protocols."""
    result = await db.execute(
        select(ProtocolBinding).where(ProtocolBinding.contract_id == contract.id)
    )
    bindings = list(result.scalars().all())

    # Check which protocols already have bindings
    existing_protocols = {b.protocol for b in bindings}

    # Create missing bindings for all protocol types
    for protocol in ProtocolType:
        if protocol not in existing_protocols:
            binding = ProtocolBinding(
                id=uuid.uuid4(),
                contract_id=contract.id,
                protocol=protocol,
                enabled=False,
            )
            db.add(binding)
            bindings.append(binding)

    if len(existing_protocols) < len(ProtocolType):
        await db.flush()

    return bindings


async def _get_traffic_24h(binding: ProtocolBinding) -> int | None:
    """Get traffic count for the last 24 hours.

    Returns None until Prometheus integration is available.
    Prometheus integration deferred — see CAB-1176.
    """
    if not binding.enabled:
        return None

    return None


def _generate_endpoint_info(contract: Contract, protocol: ProtocolType) -> dict:
    """
    Generate protocol-specific endpoint information.

    For REST and MCP: uses UAC transformer when an OpenAPI spec URL is available,
    otherwise generates base URLs from config. For GraphQL/gRPC/Kafka: stub endpoints.
    """
    base_url = (
        f"https://api.{settings.BASE_DOMAIN}"
        if hasattr(settings, "BASE_DOMAIN")
        else "https://api.stoa.example.com"
    )
    gateway_url = (
        f"https://mcp.{settings.BASE_DOMAIN}"
        if hasattr(settings, "BASE_DOMAIN")
        else "https://mcp.stoa.example.com"
    )
    contract_name = contract.name.replace("_", "-").lower()

    if protocol == ProtocolType.REST:
        return {
            "endpoint": f"{base_url}/apis/{contract.tenant_id}/{contract_name}",
            "playground_url": f"{base_url}/docs/{contract_name}",
        }

    if protocol == ProtocolType.MCP:
        tool_name = f"{contract.tenant_id}_{contract_name.replace('-', '_')}"
        return {
            "endpoint": f"{gateway_url}/mcp/v1/tools",
            "tool_name": tool_name,
            "playground_url": f"{gateway_url}/mcp/playground?tool={tool_name}",
        }

    if protocol == ProtocolType.GRAPHQL:
        return {
            "endpoint": f"{base_url}/graphql",
            "playground_url": f"{base_url}/graphql/playground?contract={contract_name}",
            "operations": ["query", "mutation"],
        }

    if protocol == ProtocolType.GRPC:
        return {
            "endpoint": f"grpc://{contract_name}.grpc.stoa.example.com:443",
            "proto_file_url": f"{base_url}/proto/{contract_name}.proto",
        }

    # Kafka
    return {
        "endpoint": f"kafka://{contract_name}.events.stoa.example.com:9092",
        "topic_name": f"stoa.{contract_name}.events",
    }


def _contract_to_response(
    contract: Contract, bindings: list[ProtocolBinding]
) -> ContractResponse:
    """Convert Contract model + bindings to response schema."""
    return ContractResponse(
        id=contract.id,
        tenant_id=contract.tenant_id,
        name=contract.name,
        display_name=contract.display_name,
        description=contract.description,
        version=contract.version,
        status=contract.status,
        openapi_spec_url=contract.openapi_spec_url,
        deprecated_at=contract.deprecated_at,
        sunset_at=contract.sunset_at,
        replacement_contract_id=contract.replacement_contract_id,
        deprecation_reason=contract.deprecation_reason,
        grace_period_days=contract.grace_period_days,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        created_by=contract.created_by,
        bindings=[_binding_to_response(b) for b in bindings],
    )


def _binding_to_response(
    binding: ProtocolBinding, traffic_24h: int | None = None
) -> ProtocolBindingResponse:
    """Convert ProtocolBinding model to response schema."""
    operations = None
    if binding.operations:
        operations = [op.strip() for op in binding.operations.split(",")]

    return ProtocolBindingResponse(
        protocol=binding.protocol,
        enabled=binding.enabled,
        endpoint=binding.endpoint,
        playground_url=binding.playground_url,
        tool_name=binding.tool_name,
        operations=operations,
        proto_file_url=binding.proto_file_url,
        topic_name=binding.topic_name,
        traffic_24h=traffic_24h,
        generated_at=binding.generated_at,
        generation_error=binding.generation_error,
    )


# ============ Contract Endpoints ============


@router.post("", response_model=ContractResponse, status_code=201)
async def create_contract(
    request: ContractCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new Universal API Contract.

    Creates the contract and initializes all protocol bindings as disabled.
    """
    tenant_id = user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User must belong to a tenant")

    # Check for duplicate name
    existing = await db.execute(
        select(Contract).where(
            and_(Contract.tenant_id == tenant_id, Contract.name == request.name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Contract '{request.name}' already exists in this tenant",
        )

    contract = Contract(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        version=request.version,
        openapi_spec_url=request.openapi_spec_url,
        status="draft",
        created_by=user.id,
    )
    db.add(contract)
    await db.flush()

    # Create default bindings (all disabled)
    bindings = await _get_or_create_default_bindings(db, contract)

    # Invalidate contract list cache for this tenant
    await contract_cache.delete_by_prefix(f"contracts:{tenant_id}")

    logger.info(
        "Contract created",
        contract_id=str(contract.id),
        tenant_id=tenant_id,
        name=request.name,
        user_id=user.id,
    )

    return _contract_to_response(contract, bindings)


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="Filter by status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List contracts for the user's tenant (cached, TTL 60s)."""
    tenant_id = user.tenant_id
    if not tenant_id and "cpi-admin" not in (user.roles or []):
        raise HTTPException(status_code=400, detail="User must belong to a tenant")

    # Check cache
    is_admin = "cpi-admin" in (user.roles or [])
    cache_key = f"contracts:{tenant_id}:{is_admin}:{page}:{page_size}:{status}"
    cached = await contract_cache.get(cache_key)
    if cached is not None:
        return cached

    query = select(Contract)
    count_query = select(func.count(Contract.id))

    # Filter by tenant unless admin
    if not is_admin:
        query = query.where(Contract.tenant_id == tenant_id)
        count_query = count_query.where(Contract.tenant_id == tenant_id)

    if status:
        query = query.where(Contract.status == status)
        count_query = count_query.where(Contract.status == status)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Contract.created_at.desc())

    result = await db.execute(query)
    contracts = result.scalars().all()

    items = []
    for contract in contracts:
        bindings = await _get_or_create_default_bindings(db, contract)
        items.append(_contract_to_response(contract, bindings))

    response = ContractListResponse(
        items=items, total=total, page=page, page_size=page_size
    )
    await contract_cache.set(cache_key, response)
    return response


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific contract by ID."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    bindings = await _get_or_create_default_bindings(db, contract)
    binding_responses = []
    for b in bindings:
        traffic = await _get_traffic_24h(b)
        binding_responses.append(_binding_to_response(b, traffic))

    return ContractResponse(
        id=contract.id,
        tenant_id=contract.tenant_id,
        name=contract.name,
        display_name=contract.display_name,
        description=contract.description,
        version=contract.version,
        status=contract.status,
        openapi_spec_url=contract.openapi_spec_url,
        deprecated_at=contract.deprecated_at,
        sunset_at=contract.sunset_at,
        replacement_contract_id=contract.replacement_contract_id,
        deprecation_reason=contract.deprecation_reason,
        grace_period_days=contract.grace_period_days,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        created_by=contract.created_by,
        bindings=binding_responses,
    )


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: uuid.UUID,
    request: ContractUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a contract."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    # Update fields
    if request.display_name is not None:
        contract.display_name = request.display_name
    if request.description is not None:
        contract.description = request.description
    if request.version is not None:
        contract.version = request.version
    if request.status is not None:
        contract.status = request.status.value
    if request.openapi_spec_url is not None:
        contract.openapi_spec_url = request.openapi_spec_url

    await db.flush()

    # Invalidate contract list cache for this tenant
    await contract_cache.delete_by_prefix(f"contracts:{contract.tenant_id}")

    bindings = await _get_or_create_default_bindings(db, contract)

    logger.info(
        "Contract updated",
        contract_id=str(contract_id),
        user_id=user.id,
    )

    return _contract_to_response(contract, bindings)


@router.delete("/{contract_id}", status_code=204)
async def delete_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a contract and all its bindings."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    tenant_id = contract.tenant_id
    await db.delete(contract)  # Cascade deletes bindings

    # Invalidate contract list cache for this tenant
    await contract_cache.delete_by_prefix(f"contracts:{tenant_id}")

    logger.info(
        "Contract deleted",
        contract_id=str(contract_id),
        tenant_id=tenant_id,
        user_id=user.id,
    )


# ============ Lifecycle Endpoints (CAB-1335) ============


@router.post("/{contract_id}/deprecate", response_model=ContractDeprecationInfo)
async def deprecate_contract(
    contract_id: uuid.UUID,
    request: DeprecateContractRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deprecate a published contract with optional sunset date.

    Sets the contract status to 'deprecated' and records deprecation metadata
    including reason, sunset date (RFC 8594), and optional replacement contract.
    """
    from src.services.contract_lifecycle_service import (
        deprecate_contract as _deprecate,
    )

    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    try:
        contract = await _deprecate(
            db=db,
            contract=contract,
            reason=request.reason,
            sunset_at=request.sunset_at,
            replacement_contract_id=request.replacement_contract_id,
            grace_period_days=request.grace_period_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Invalidate cache
    await contract_cache.delete_by_prefix(f"contracts:{contract.tenant_id}")

    logger.info(
        "Contract deprecated via API",
        contract_id=str(contract_id),
        user_id=user.id,
    )

    return ContractDeprecationInfo(
        contract_id=contract.id,
        contract_name=contract.name,
        version=contract.version,
        status=contract.status,
        deprecated_at=contract.deprecated_at,
        sunset_at=contract.sunset_at,
        replacement_contract_id=contract.replacement_contract_id,
        deprecation_reason=contract.deprecation_reason,
        grace_period_days=contract.grace_period_days,
        is_sunset=contract.is_sunset,
    )


@router.post("/{contract_id}/reactivate", response_model=ContractResponse)
async def reactivate_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reactivate a deprecated contract (undo deprecation).

    Only allowed if the sunset date has not passed.
    """
    from src.services.contract_lifecycle_service import (
        reactivate_contract as _reactivate,
    )

    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    try:
        contract = await _reactivate(db=db, contract=contract)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Invalidate cache
    await contract_cache.delete_by_prefix(f"contracts:{contract.tenant_id}")

    bindings = await _get_or_create_default_bindings(db, contract)

    return _contract_to_response(contract, bindings)


@router.get("/{contract_id}/deprecation", response_model=ContractDeprecationInfo)
async def get_deprecation_info(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deprecation details for a contract."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    return ContractDeprecationInfo(
        contract_id=contract.id,
        contract_name=contract.name,
        version=contract.version,
        status=contract.status,
        deprecated_at=contract.deprecated_at,
        sunset_at=contract.sunset_at,
        replacement_contract_id=contract.replacement_contract_id,
        deprecation_reason=contract.deprecation_reason,
        grace_period_days=contract.grace_period_days,
        is_sunset=contract.is_sunset,
    )


@router.get(
    "/by-name/{contract_name}/versions",
    response_model=ContractVersionsResponse,
)
async def list_contract_versions(
    contract_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all versions of a contract by name.

    Returns version history including deprecation status, ordered by creation date
    (latest first).
    """
    from src.services.contract_lifecycle_service import (
        get_active_version,
        list_versions,
    )

    tenant_id = user.tenant_id
    if not tenant_id and "cpi-admin" not in (user.roles or []):
        raise HTTPException(status_code=400, detail="User must belong to a tenant")

    # For admin, we need a tenant context — use the first matching contract's tenant
    if not tenant_id:
        result = await db.execute(
            select(Contract).where(Contract.name == contract_name).limit(1)
        )
        first = result.scalar_one_or_none()
        if not first:
            raise HTTPException(status_code=404, detail=f"No contract found with name '{contract_name}'")
        tenant_id = first.tenant_id

    versions = await list_versions(db, tenant_id, contract_name)
    if not versions:
        raise HTTPException(
            status_code=404,
            detail=f"No contract found with name '{contract_name}'",
        )

    active = await get_active_version(db, tenant_id, contract_name)

    return ContractVersionsResponse(
        contract_name=contract_name,
        tenant_id=tenant_id,
        versions=[
            ContractVersionSummary(
                id=c.id,
                version=c.version,
                status=c.status,
                created_at=c.created_at,
                deprecated_at=c.deprecated_at,
                sunset_at=c.sunset_at,
            )
            for c in versions
        ],
        latest_version=active.version if active else None,
        active_count=sum(1 for c in versions if c.status == "published"),
    )


# ============ Bindings Endpoints ============


@router.get("/{contract_id}/bindings", response_model=BindingsListResponse)
async def list_bindings(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all protocol bindings for a contract.

    Returns all 5 protocols (REST, MCP, GraphQL, gRPC, Kafka) with their status.
    Used by the Protocol Switcher UI component.
    """
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    bindings = await _get_or_create_default_bindings(db, contract)

    binding_responses = []
    for binding in bindings:
        traffic = await _get_traffic_24h(binding)
        binding_responses.append(_binding_to_response(binding, traffic))

    return BindingsListResponse(
        contract_id=contract.id,
        contract_name=contract.name,
        bindings=binding_responses,
    )


@router.post("/{contract_id}/bindings", response_model=EnableBindingResponse)
async def enable_binding(
    contract_id: uuid.UUID,
    request: EnableBindingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Enable a protocol binding for a contract.

    This triggers the UAC engine to generate the binding (endpoint, tool, etc.).
    """
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    # Get or create the binding
    binding_result = await db.execute(
        select(ProtocolBinding).where(
            and_(
                ProtocolBinding.contract_id == contract_id,
                ProtocolBinding.protocol == request.protocol,
            )
        )
    )
    binding = binding_result.scalar_one_or_none()

    if not binding:
        binding = ProtocolBinding(
            id=uuid.uuid4(),
            contract_id=contract_id,
            protocol=request.protocol,
            enabled=False,
        )
        db.add(binding)

    if binding.enabled:
        raise HTTPException(
            status_code=409,
            detail=f"{request.protocol.value.upper()} binding is already enabled",
        )

    # Generate endpoint info
    endpoint_info = _generate_endpoint_info(contract, request.protocol)

    # Update binding
    binding.enabled = True
    binding.endpoint = endpoint_info.get("endpoint")
    binding.playground_url = endpoint_info.get("playground_url")
    binding.tool_name = endpoint_info.get("tool_name")
    binding.proto_file_url = endpoint_info.get("proto_file_url")
    binding.topic_name = endpoint_info.get("topic_name")
    if endpoint_info.get("operations"):
        binding.operations = ",".join(endpoint_info["operations"])
    binding.generated_at = datetime.utcnow()
    binding.generation_error = None

    await db.flush()

    # --- Best-effort UAC gateway dispatch ---
    # Deploy the contract to all online STOA gateways.  Failures are non-blocking:
    # the binding is already committed to the DB; generation_error stores the reason.
    _stoa_types = [
        GatewayType.STOA,
        GatewayType.STOA_EDGE_MCP,
        GatewayType.STOA_SIDECAR,
        GatewayType.STOA_PROXY,
        GatewayType.STOA_SHADOW,
    ]
    gw_result = await db.execute(
        select(GatewayInstance).where(
            and_(
                GatewayInstance.gateway_type.in_(_stoa_types),
                GatewayInstance.status == GatewayInstanceStatus.ONLINE,
                or_(
                    GatewayInstance.tenant_id == contract.tenant_id,
                    GatewayInstance.tenant_id.is_(None),
                ),
            )
        )
    )
    gateways = gw_result.scalars().all()

    contract_spec = {
        "name": contract.name,
        "version": contract.version,
        "tenant_id": str(contract.tenant_id),
        "endpoints": [],
    }

    dispatch_errors: list[str] = []
    for gw in gateways:
        try:
            adapter = AdapterRegistry.create(
                gw.gateway_type.value,
                config={"base_url": gw.base_url, "auth_config": gw.auth_config},
            )
            await adapter.connect()
            result = await adapter.deploy_contract(contract_spec)
            if not result.success:
                dispatch_errors.append(f"{gw.name}: {result.error}")
        except Exception as exc:
            dispatch_errors.append(f"{gw.name}: {exc}")

    if dispatch_errors:
        binding.generation_error = "; ".join(dispatch_errors)
        logger.warning(
            "UAC gateway dispatch partial failure",
            contract_id=str(contract_id),
            errors=dispatch_errors,
        )
    # --- end gateway dispatch ---

    # --- Auto-generate MCP tools when MCP binding is enabled (CAB-605) ---
    if request.protocol == ProtocolType.MCP and contract.openapi_spec_url:
        try:
            from src.services.uac_transformer import (
                fetch_openapi_spec,
                transform_openapi_to_uac,
            )

            openapi_spec = await fetch_openapi_spec(contract.openapi_spec_url)
            uac_spec = transform_openapi_to_uac(
                openapi_spec,
                tenant_id=contract.tenant_id,
                source_spec_url=contract.openapi_spec_url,
            )
            generator = UacToolGenerator(db)
            await generator.generate_tools(contract, uac_spec)
        except Exception as exc:
            logger.warning(
                "MCP tool generation failed (non-blocking)",
                contract_id=str(contract_id),
                error=str(exc),
            )

    logger.info(
        "Protocol binding enabled",
        contract_id=str(contract_id),
        protocol=request.protocol.value,
        endpoint=binding.endpoint,
        user_id=user.id,
    )

    return EnableBindingResponse(
        protocol=request.protocol,
        endpoint=binding.endpoint or "",
        playground_url=binding.playground_url,
        tool_name=binding.tool_name,
        status="active",
        generated_at=binding.generated_at,
    )


@router.delete(
    "/{contract_id}/bindings/{protocol}", response_model=DisableBindingResponse
)
async def disable_binding(
    contract_id: uuid.UUID,
    protocol: ProtocolType,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Disable a protocol binding for a contract.

    The binding is soft-disabled (keeps history). The endpoint becomes inactive.
    """
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contract")

    binding_result = await db.execute(
        select(ProtocolBinding).where(
            and_(
                ProtocolBinding.contract_id == contract_id,
                ProtocolBinding.protocol == protocol,
            )
        )
    )
    binding = binding_result.scalar_one_or_none()

    if not binding:
        raise HTTPException(
            status_code=404, detail=f"{protocol.value.upper()} binding not found"
        )

    if not binding.enabled:
        raise HTTPException(
            status_code=409,
            detail=f"{protocol.value.upper()} binding is already disabled",
        )

    binding.enabled = False

    await db.flush()

    logger.info(
        "Protocol binding disabled",
        contract_id=str(contract_id),
        protocol=protocol.value,
        user_id=user.id,
    )

    return DisableBindingResponse(
        protocol=protocol,
        status="disabled",
        disabled_at=datetime.utcnow(),
    )


# ============ MCP Tool Endpoints (CAB-605) ============


def _tool_to_response(tool: McpGeneratedTool) -> McpToolDefinition:
    """Convert ORM tool to response schema."""
    import json as _json

    return McpToolDefinition(
        tool_name=tool.tool_name,
        description=tool.description,
        input_schema=_json.loads(tool.input_schema) if tool.input_schema else None,
        output_schema=_json.loads(tool.output_schema) if tool.output_schema else None,
        backend_url=tool.backend_url,
        http_method=tool.http_method,
        path_pattern=tool.path_pattern,
        version=tool.version,
        spec_hash=tool.spec_hash,
        enabled=tool.enabled,
    )


@router.post(
    "/{contract_id}/mcp-tools/generate",
    response_model=McpToolsGenerateResponse,
    summary="Generate MCP tools from UAC contract",
)
async def generate_mcp_tools(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger MCP tool generation from a UAC contract's endpoints."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalars().first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    from src.schemas.uac import UacContractSpec

    spec = UacContractSpec(
        name=contract.name,
        version=contract.version,
        tenant_id=contract.tenant_id,
        display_name=contract.display_name,
        description=contract.description,
        endpoints=[],
        spec_hash=contract.schema_hash,
    )

    if contract.openapi_spec_url:
        try:
            from src.services.uac_transformer import (
                fetch_openapi_spec,
                transform_openapi_to_uac,
            )

            openapi_spec = await fetch_openapi_spec(contract.openapi_spec_url)
            spec = transform_openapi_to_uac(
                openapi_spec,
                tenant_id=contract.tenant_id,
                source_spec_url=contract.openapi_spec_url,
            )
        except Exception as exc:
            logger.warning("Failed to fetch OpenAPI spec", error=str(exc))

    generator = UacToolGenerator(db)
    tools = await generator.generate_tools(contract, spec)

    return McpToolsGenerateResponse(
        generated=len(tools),
        contract_id=contract.id,
        tools=[_tool_to_response(t) for t in tools],
    )


@router.get(
    "/{contract_id}/mcp-tools",
    response_model=McpToolsListResponse,
    summary="List MCP tools for a contract",
)
async def list_mcp_tools(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all generated MCP tools for a contract."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalars().first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not _has_tenant_access(user, contract.tenant_id):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    generator = UacToolGenerator(db)
    tools = await generator.get_tools_for_contract(contract_id)

    return McpToolsListResponse(
        contract_id=contract.id,
        contract_name=contract.name,
        tools=[_tool_to_response(t) for t in tools],
        spec_hash=contract.schema_hash,
    )


# ============ MCP Discovery Router (CAB-605) ============

discovery_router = APIRouter(prefix="/v1/mcp", tags=["MCP Discovery"])


@discovery_router.get(
    "/generated-tools",
    response_model=TenantToolsResponse,
    summary="Gateway discovery — list all tools for a tenant",
)
async def get_tenant_tools(
    tenant_id: str = Query(..., description="Tenant ID"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gateway discovery endpoint: list all enabled MCP tools for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    generator = UacToolGenerator(db)
    tools = await generator.get_tools_for_tenant(tenant_id)

    return TenantToolsResponse(
        tenant_id=tenant_id,
        tools=[_tool_to_response(t) for t in tools],
        total=len(tools),
    )
