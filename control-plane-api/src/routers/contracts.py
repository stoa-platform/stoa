"""
Contracts and Protocol Bindings Router

Endpoints for managing Universal API Contracts (UAC) and their protocol bindings.
The Protocol Switcher UI uses these endpoints to enable/disable bindings.
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from src.database import get_db
from src.auth.dependencies import get_current_user, User
from src.models.contract import Contract, ProtocolBinding, ProtocolType
from src.schemas.contract import (
    ContractCreate,
    ContractUpdate,
    ContractResponse,
    ContractListResponse,
    BindingsListResponse,
    EnableBindingRequest,
    EnableBindingResponse,
    DisableBindingResponse,
    ProtocolBindingResponse,
)
from src.logging_config import get_logger
from src.config import settings

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


async def _get_traffic_24h(binding: ProtocolBinding) -> Optional[int]:
    """
    Get traffic count for the last 24 hours.

    TODO: Integrate with Prometheus/metrics storage for real data.
    Currently returns mock data for UI development.
    """
    if not binding.enabled:
        return None

    # Mock implementation - replace with actual metrics query
    import random
    return random.randint(0, 2000)


def _generate_endpoint_info(contract: Contract, protocol: ProtocolType) -> dict:
    """
    Generate protocol-specific endpoint information.

    TODO: Integrate with UAC engine for real binding generation.
    Currently returns mock endpoints for UI development.
    """
    base_url = f"https://api.{settings.BASE_DOMAIN}" if hasattr(settings, 'BASE_DOMAIN') else "https://api.stoa.example.com"
    contract_name = contract.name.replace("_", "-").lower()

    generators = {
        ProtocolType.REST: lambda: {
            "endpoint": f"{base_url}/v1/{contract_name}",
            "playground_url": f"{base_url}/docs/{contract_name}",
        },
        ProtocolType.GRAPHQL: lambda: {
            "endpoint": f"{base_url}/graphql",
            "playground_url": f"{base_url}/graphql/playground?contract={contract_name}",
            "operations": ["query", "mutation"],
        },
        ProtocolType.GRPC: lambda: {
            "endpoint": f"grpc://{contract_name}.grpc.stoa.example.com:443",
            "proto_file_url": f"{base_url}/proto/{contract_name}.proto",
        },
        ProtocolType.MCP: lambda: {
            "endpoint": f"{base_url}/mcp/v1/tools",
            "tool_name": f"{contract_name.replace('-', '_')}_tool",
            "playground_url": f"{base_url}/mcp/playground?tool={contract_name}",
        },
        ProtocolType.KAFKA: lambda: {
            "endpoint": f"kafka://{contract_name}.events.stoa.example.com:9092",
            "topic_name": f"stoa.{contract_name}.events",
        },
    }

    return generators[protocol]()


def _binding_to_response(binding: ProtocolBinding, traffic_24h: Optional[int] = None) -> ProtocolBindingResponse:
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
            status_code=409, detail=f"Contract '{request.name}' already exists in this tenant"
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

    logger.info(
        "Contract created",
        contract_id=str(contract.id),
        tenant_id=tenant_id,
        name=request.name,
        user_id=user.id,
    )

    return ContractResponse(
        id=contract.id,
        tenant_id=contract.tenant_id,
        name=contract.name,
        display_name=contract.display_name,
        description=contract.description,
        version=contract.version,
        status=contract.status,
        openapi_spec_url=contract.openapi_spec_url,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        created_by=contract.created_by,
        bindings=[_binding_to_response(b) for b in bindings],
    )


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List contracts for the user's tenant."""
    tenant_id = user.tenant_id
    if not tenant_id and "cpi-admin" not in (user.roles or []):
        raise HTTPException(status_code=400, detail="User must belong to a tenant")

    query = select(Contract)
    count_query = select(func.count(Contract.id))

    # Filter by tenant unless admin
    if "cpi-admin" not in (user.roles or []):
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
        items.append(
            ContractResponse(
                id=contract.id,
                tenant_id=contract.tenant_id,
                name=contract.name,
                display_name=contract.display_name,
                description=contract.description,
                version=contract.version,
                status=contract.status,
                openapi_spec_url=contract.openapi_spec_url,
                created_at=contract.created_at,
                updated_at=contract.updated_at,
                created_by=contract.created_by,
                bindings=[_binding_to_response(b) for b in bindings],
            )
        )

    return ContractListResponse(items=items, total=total, page=page, page_size=page_size)


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

    bindings = await _get_or_create_default_bindings(db, contract)

    logger.info(
        "Contract updated",
        contract_id=str(contract_id),
        user_id=user.id,
    )

    return ContractResponse(
        id=contract.id,
        tenant_id=contract.tenant_id,
        name=contract.name,
        display_name=contract.display_name,
        description=contract.description,
        version=contract.version,
        status=contract.status,
        openapi_spec_url=contract.openapi_spec_url,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        created_by=contract.created_by,
        bindings=[_binding_to_response(b) for b in bindings],
    )


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

    await db.delete(contract)  # Cascade deletes bindings

    logger.info(
        "Contract deleted",
        contract_id=str(contract_id),
        tenant_id=contract.tenant_id,
        user_id=user.id,
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
            status_code=409, detail=f"{request.protocol.value.upper()} binding is already enabled"
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


@router.delete("/{contract_id}/bindings/{protocol}", response_model=DisableBindingResponse)
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
        raise HTTPException(status_code=404, detail=f"{protocol.value.upper()} binding not found")

    if not binding.enabled:
        raise HTTPException(
            status_code=409, detail=f"{protocol.value.upper()} binding is already disabled"
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
