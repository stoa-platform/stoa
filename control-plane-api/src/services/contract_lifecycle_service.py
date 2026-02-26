"""
Contract Lifecycle Service — Deprecation and version management (CAB-1335).

Handles the contract lifecycle: draft → published → deprecated (with sunset).
Supports RFC 8594 Sunset header semantics and version history queries.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contract import Contract

logger = logging.getLogger(__name__)


async def deprecate_contract(
    db: AsyncSession,
    contract: Contract,
    reason: str,
    sunset_at: datetime | None = None,
    replacement_contract_id: UUID | None = None,
    grace_period_days: int | None = None,
) -> Contract:
    """Deprecate a contract with optional sunset date and replacement.

    Args:
        db: Database session.
        contract: Contract to deprecate.
        reason: Human-readable deprecation reason.
        sunset_at: When the contract will be fully removed.
        replacement_contract_id: ID of the replacement contract.
        grace_period_days: Days of grace before sunset enforcement.

    Returns:
        Updated contract.

    Raises:
        ValueError: If contract is already deprecated or in draft status.
    """
    if contract.status == "deprecated":
        raise ValueError(f"Contract '{contract.name}' v{contract.version} is already deprecated")

    if contract.status == "draft":
        raise ValueError("Cannot deprecate a draft contract — publish it first or delete it")

    # Validate replacement contract exists if provided
    if replacement_contract_id:
        result = await db.execute(
            select(Contract).where(Contract.id == replacement_contract_id)
        )
        replacement = result.scalar_one_or_none()
        if not replacement:
            raise ValueError(f"Replacement contract {replacement_contract_id} not found")
        if replacement.tenant_id != contract.tenant_id:
            raise ValueError("Replacement contract must belong to the same tenant")
        if replacement.status == "deprecated":
            raise ValueError("Replacement contract is itself deprecated")

    # Compute sunset_at from grace_period_days if not explicitly set
    now = datetime.utcnow()
    if not sunset_at and grace_period_days is not None:
        sunset_at = now + timedelta(days=grace_period_days)

    contract.status = "deprecated"
    contract.deprecated_at = now
    contract.sunset_at = sunset_at
    contract.deprecation_reason = reason
    contract.grace_period_days = grace_period_days
    if replacement_contract_id:
        contract.replacement_contract_id = str(replacement_contract_id)

    await db.flush()

    logger.info(
        "Contract deprecated",
        extra={
            "contract_id": str(contract.id),
            "contract_name": contract.name,
            "version": contract.version,
            "sunset_at": str(sunset_at) if sunset_at else "none",
            "replacement": str(replacement_contract_id) if replacement_contract_id else "none",
        },
    )

    return contract


async def reactivate_contract(
    db: AsyncSession,
    contract: Contract,
) -> Contract:
    """Reactivate a deprecated contract (undo deprecation).

    Only allowed if sunset date has not passed.

    Raises:
        ValueError: If contract is not deprecated or sunset has passed.
    """
    if contract.status != "deprecated":
        raise ValueError("Only deprecated contracts can be reactivated")

    if contract.is_sunset:
        raise ValueError("Cannot reactivate — sunset date has passed")

    contract.status = "published"
    contract.deprecated_at = None
    contract.sunset_at = None
    contract.replacement_contract_id = None
    contract.deprecation_reason = None
    contract.grace_period_days = None

    await db.flush()

    logger.info(
        "Contract reactivated",
        extra={
            "contract_id": str(contract.id),
            "contract_name": contract.name,
            "version": contract.version,
        },
    )

    return contract


async def list_versions(
    db: AsyncSession,
    tenant_id: str,
    contract_name: str,
) -> list[Contract]:
    """List all versions of a contract by name within a tenant.

    Returns contracts ordered by version descending (latest first).
    """
    result = await db.execute(
        select(Contract)
        .where(
            Contract.tenant_id == tenant_id,
            Contract.name == contract_name,
        )
        .order_by(Contract.created_at.desc())
    )
    return list(result.scalars().all())


async def get_active_version(
    db: AsyncSession,
    tenant_id: str,
    contract_name: str,
) -> Contract | None:
    """Get the latest non-deprecated version of a contract.

    Returns the most recently created published contract with the given name,
    or None if all versions are deprecated/draft.
    """
    result = await db.execute(
        select(Contract)
        .where(
            Contract.tenant_id == tenant_id,
            Contract.name == contract_name,
            Contract.status == "published",
        )
        .order_by(Contract.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_sunset_candidates(
    db: AsyncSession,
    before: datetime | None = None,
) -> list[Contract]:
    """Find deprecated contracts whose sunset date has passed or is approaching.

    Args:
        before: Find contracts with sunset_at before this date.
                Defaults to now (already sunset).
    """
    if before is None:
        before = datetime.utcnow()

    result = await db.execute(
        select(Contract)
        .where(
            Contract.status == "deprecated",
            Contract.sunset_at.isnot(None),
            Contract.sunset_at <= before,
        )
        .order_by(Contract.sunset_at.asc())
    )
    return list(result.scalars().all())
