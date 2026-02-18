"""Federation router — enterprise MCP multi-account orchestration (CAB-1313/CAB-1361/CAB-1370)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.federation import MasterAccountStatus, SubAccountStatus
from ..schemas.federation import (
    DelegationTokenRequest,
    DelegationTokenResponse,
    FederationBulkRevokeResponse,
    MasterAccountCreate,
    MasterAccountListResponse,
    MasterAccountResponse,
    MasterAccountUpdate,
    SubAccountCreate,
    SubAccountCreatedResponse,
    SubAccountListResponse,
    SubAccountResponse,
    SubAccountUpdate,
    ToolAllowListResponse,
    ToolAllowListUpdate,
    UsageResponse,
    UsageStat,
)
from ..services.federation_service import FederationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/federation/accounts", tags=["Federation"])


# ============== RBAC Helpers ==============


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _require_write_access(user: User, tenant_id: str) -> None:
    """Require write access (tenant-admin or cpi-admin)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Write access requires tenant-admin or cpi-admin role")


def _require_admin_only(user: User) -> None:
    """Require cpi-admin role."""
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="This operation requires cpi-admin role")


def _to_master_response(master, sub_account_count: int = 0) -> MasterAccountResponse:
    """Convert MasterAccount model to response."""
    return MasterAccountResponse(
        id=master.id,
        tenant_id=master.tenant_id,
        name=master.name,
        display_name=master.display_name,
        description=master.description,
        status=master.status,
        max_sub_accounts=master.max_sub_accounts,
        quota_config=master.quota_config,
        sub_account_count=sub_account_count,
        created_at=master.created_at,
        updated_at=master.updated_at,
        created_by=master.created_by,
    )


# ============== Master Account Endpoints ==============


@router.post("", response_model=MasterAccountResponse, status_code=201)
async def create_master_account(
    tenant_id: str,
    request: MasterAccountCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a federation master account."""
    _require_write_access(user, tenant_id)
    svc = FederationService(db)

    try:
        master = await svc.create_master_account(
            tenant_id=tenant_id,
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            max_sub_accounts=request.max_sub_accounts,
            quota_config=request.quota_config,
            created_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    logger.info("Federation master account created: %s/%s by %s", tenant_id, request.name, user.id)
    return _to_master_response(master, sub_account_count=0)


@router.get("", response_model=MasterAccountListResponse)
async def list_master_accounts(
    tenant_id: str,
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List federation master accounts for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    status_filter = MasterAccountStatus(status) if status else None
    items, total = await svc.list_master_accounts(tenant_id, status=status_filter, page=page, page_size=page_size)

    responses = []
    for master in items:
        count = await svc.count_sub_accounts(master.id)
        responses.append(_to_master_response(master, sub_account_count=count))

    return MasterAccountListResponse(items=responses, total=total, page=page, page_size=page_size)


@router.get("/{account_id}", response_model=MasterAccountResponse)
async def get_master_account(
    tenant_id: str,
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a federation master account by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    count = await svc.count_sub_accounts(master.id)
    return _to_master_response(master, sub_account_count=count)


@router.patch("/{account_id}", response_model=MasterAccountResponse)
async def update_master_account(
    tenant_id: str,
    account_id: UUID,
    request: MasterAccountUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a federation master account."""
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    updates = request.model_dump(exclude_unset=True)
    master = await svc.update_master_account(master, updates)
    await db.commit()

    count = await svc.count_sub_accounts(master.id)
    logger.info("Federation master account updated: %s/%s by %s", tenant_id, master.name, user.id)
    return _to_master_response(master, sub_account_count=count)


@router.delete("/{account_id}", status_code=204)
async def delete_master_account(
    tenant_id: str,
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a federation master account (cpi-admin only, cascades sub-accounts)."""
    _require_admin_only(user)
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    await svc.delete_master_account(master)
    await db.commit()
    logger.info("Federation master account deleted: %s/%s by %s", tenant_id, master.name, user.id)


# ============== Sub-Account Endpoints ==============


@router.post("/{account_id}/sub-accounts", response_model=SubAccountCreatedResponse, status_code=201)
async def create_sub_account(
    tenant_id: str,
    account_id: UUID,
    request: SubAccountCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a federation sub-account. The API key is returned only once."""
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    try:
        sub, plaintext_key = await svc.create_sub_account(
            master=master,
            name=request.name,
            display_name=request.display_name,
            account_type=request.account_type,
            created_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    logger.info("Federation sub-account created: %s/%s/%s by %s", tenant_id, master.name, request.name, user.id)
    return SubAccountCreatedResponse(
        id=sub.id,
        name=sub.name,
        api_key=plaintext_key,
        api_key_prefix=sub.api_key_prefix,
    )


@router.get("/{account_id}/sub-accounts", response_model=SubAccountListResponse)
async def list_sub_accounts(
    tenant_id: str,
    account_id: UUID,
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sub-accounts for a federation master account."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    status_filter = SubAccountStatus(status) if status else None
    items, total = await svc.list_sub_accounts(master.id, status=status_filter, page=page, page_size=page_size)

    return SubAccountListResponse(
        items=[SubAccountResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{account_id}/sub-accounts/{sub_id}", response_model=SubAccountResponse)
async def get_sub_account(
    tenant_id: str,
    account_id: UUID,
    sub_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a sub-account by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    sub = await svc.get_sub_account(sub_id)
    if not sub or sub.master_account_id != account_id or sub.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sub-account not found")

    return SubAccountResponse.model_validate(sub)


@router.patch("/{account_id}/sub-accounts/{sub_id}", response_model=SubAccountResponse)
async def update_sub_account(
    tenant_id: str,
    account_id: UUID,
    sub_id: UUID,
    request: SubAccountUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a sub-account."""
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    sub = await svc.get_sub_account(sub_id)
    if not sub or sub.master_account_id != account_id or sub.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sub-account not found")

    updates = request.model_dump(exclude_unset=True)
    sub = await svc.update_sub_account(sub, updates)
    await db.commit()

    logger.info("Federation sub-account updated: %s by %s", sub.name, user.id)
    return SubAccountResponse.model_validate(sub)


@router.post("/{account_id}/sub-accounts/{sub_id}/revoke", response_model=SubAccountResponse)
async def revoke_sub_account(
    tenant_id: str,
    account_id: UUID,
    sub_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a sub-account -- clears API key and sets status to revoked."""
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    sub = await svc.get_sub_account(sub_id)
    if not sub or sub.master_account_id != account_id or sub.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sub-account not found")

    sub = await svc.revoke_sub_account(sub)
    await db.commit()

    logger.info("Federation sub-account revoked: %s by %s", sub.name, user.id)
    return SubAccountResponse.model_validate(sub)


# ============== CAB-1370: Delegation Token + Usage + Bulk Ops ==============


@router.post("/{account_id}/delegate-token", response_model=DelegationTokenResponse)
async def delegate_token(
    tenant_id: str,
    account_id: UUID,
    request: DelegationTokenRequest,
    sub_account_id: UUID | None = Query(None, description="Target sub-account ID (defaults to first active)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a delegation token for a sub-account with a KC client.

    If sub_account_id is provided, targets that specific sub-account.
    Otherwise falls back to the first active sub-account with a Keycloak client.
    """
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    target_sub = None
    if sub_account_id:
        # Target a specific sub-account
        sub = await svc.get_sub_account(sub_account_id)
        if not sub or sub.master_account_id != account_id or sub.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Sub-account not found")
        if sub.status != SubAccountStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Sub-account is not active")
        if not sub.kc_client_id:
            raise HTTPException(status_code=400, detail="Sub-account has no Keycloak client configured")
        target_sub = sub
    else:
        # Fallback: first active sub-account with a KC client
        items, _ = await svc.list_sub_accounts(master.id, status=SubAccountStatus.ACTIVE, page=1, page_size=100)
        target_sub = next((s for s in items if s.kc_client_id), None)
    if not target_sub:
        raise HTTPException(status_code=404, detail="No active sub-account with Keycloak client found")

    try:
        token_data = await svc.delegate_token(target_sub, request.scopes, request.ttl_seconds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DelegationTokenResponse(
        access_token=token_data["access_token"],
        token_type=token_data.get("token_type", "Bearer"),
        expires_in=token_data.get("expires_in", request.ttl_seconds),
        scope=token_data.get("scope", " ".join(request.scopes)),
        sub_account_id=target_sub.id,
        sub_account_name=target_sub.name,
    )


@router.get("/{account_id}/usage", response_model=UsageResponse)
async def get_usage(
    tenant_id: str,
    account_id: UUID,
    days: int = Query(7, ge=1, le=90, description="Usage period in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated usage statistics for a master account's sub-accounts."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    usage_data = await svc.get_usage_aggregation(master.id, period_days=days)
    sub_stats = [UsageStat(**entry) for entry in usage_data]

    return UsageResponse(
        master_account_id=master.id,
        period_days=days,
        total_requests=sum(s.request_count for s in sub_stats),
        total_tokens=sum(s.token_count for s in sub_stats),
        sub_accounts=sub_stats,
    )


@router.post("/{account_id}/bulk-revoke", response_model=FederationBulkRevokeResponse)
async def bulk_revoke(
    tenant_id: str,
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all active/suspended sub-accounts under a master account."""
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    master = await svc.get_master_account(account_id)
    if not master or master.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Master account not found")

    newly_revoked, already_revoked, total = await svc.bulk_revoke(master.id)
    await db.commit()

    logger.info(
        "Federation bulk revoke: %s/%s by %s — %d revoked",
        tenant_id,
        master.name,
        user.id,
        newly_revoked,
    )
    return FederationBulkRevokeResponse(revoked_count=newly_revoked, already_revoked=already_revoked, total=total)


@router.put("/{account_id}/sub-accounts/{sub_id}/tools", response_model=ToolAllowListResponse)
async def set_tool_allow_list(
    tenant_id: str,
    account_id: UUID,
    sub_id: UUID,
    request: ToolAllowListUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the tool allow-list for a sub-account."""
    _require_write_access(user, tenant_id)

    svc = FederationService(db)
    sub = await svc.get_sub_account(sub_id)
    if not sub or sub.master_account_id != account_id or sub.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sub-account not found")

    tools = await svc.set_tool_allow_list(sub_id, request.tools)
    await db.commit()

    logger.info("Federation tool allow-list updated: %s/%s by %s", sub.name, sub_id, user.id)
    return ToolAllowListResponse(sub_account_id=sub_id, tools=tools)


@router.get("/{account_id}/sub-accounts/{sub_id}/tools", response_model=ToolAllowListResponse)
async def get_tool_allow_list(
    tenant_id: str,
    account_id: UUID,
    sub_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the tool allow-list for a sub-account."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    svc = FederationService(db)
    sub = await svc.get_sub_account(sub_id)
    if not sub or sub.master_account_id != account_id or sub.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sub-account not found")

    tools = await svc.get_tool_allow_list(sub_id)
    return ToolAllowListResponse(sub_account_id=sub_id, tools=tools)
