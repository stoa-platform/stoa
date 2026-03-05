#!/usr/bin/env python3
"""Backfill oauth_client_id on existing subscriptions from PortalApplication.keycloak_client_id.

For each ACTIVE subscription that has api_key_hash but no oauth_client_id,
looks up the associated PortalApplication's keycloak_client_id and sets it.

Usage:
    cd control-plane-api
    python -m scripts.backfill_oauth_subscriptions              # Dry-run (default)
    python -m scripts.backfill_oauth_subscriptions --apply      # Apply changes
    python -m scripts.backfill_oauth_subscriptions --check      # Check current state

Requirements:
    - Database must be running and accessible
    - Tables must exist (run alembic migrations first)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.models.portal_application import PortalApplication
from src.models.subscription import Subscription, SubscriptionStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def get_session() -> AsyncSession:
    """Create a database session."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def check_state(session: AsyncSession) -> None:
    """Report current state of oauth_client_id backfill."""
    total = await session.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
    )
    with_oauth = await session.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.oauth_client_id.isnot(None),
        )
    )
    without_oauth = await session.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.oauth_client_id.is_(None),
            Subscription.api_key_hash.isnot(None),
        )
    )

    logger.info("Active subscriptions: %d", total or 0)
    logger.info("  With oauth_client_id: %d", with_oauth or 0)
    logger.info("  Without oauth_client_id (need backfill): %d", without_oauth or 0)


async def backfill(session: AsyncSession, *, dry_run: bool = True) -> None:
    """Backfill oauth_client_id from PortalApplication.keycloak_client_id."""
    mode = "DRY-RUN" if dry_run else "APPLY"
    logger.info("[%s] Starting oauth_client_id backfill...", mode)

    # Find subscriptions needing backfill
    result = await session.execute(
        select(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.oauth_client_id.is_(None),
            Subscription.api_key_hash.isnot(None),
        )
    )
    subscriptions = result.scalars().all()

    if not subscriptions:
        logger.info("No subscriptions need backfill. All done!")
        return

    logger.info("Found %d subscriptions to backfill.", len(subscriptions))

    updated = 0
    skipped = 0

    for sub in subscriptions:
        # Look up the PortalApplication by application_id
        if not sub.application_id:
            logger.warning(
                "Subscription %s has no application_id — skipping.",
                sub.id,
            )
            skipped += 1
            continue

        app = await session.get(PortalApplication, sub.application_id)
        if not app:
            logger.warning(
                "Subscription %s references application %s which does not exist — skipping.",
                sub.id,
                sub.application_id,
            )
            skipped += 1
            continue

        if not app.keycloak_client_id:
            logger.warning(
                "Subscription %s: PortalApplication %s has NULL keycloak_client_id — skipping.",
                sub.id,
                sub.application_id,
            )
            skipped += 1
            continue

        if dry_run:
            logger.info(
                "  [DRY-RUN] Would set subscription %s oauth_client_id = %s (from app %s)",
                sub.id,
                app.keycloak_client_id,
                app.name,
            )
        else:
            sub.oauth_client_id = app.keycloak_client_id
            logger.info(
                "  Set subscription %s oauth_client_id = %s (from app %s)",
                sub.id,
                app.keycloak_client_id,
                app.name,
            )
        updated += 1

    if not dry_run:
        await session.commit()

    logger.info("[%s] Complete: %d updated, %d skipped.", mode, updated, skipped)
    if dry_run and updated > 0:
        logger.info("Run with --apply to execute changes.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill oauth_client_id on subscriptions")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    group.add_argument("--check", action="store_true", help="Check current state only")
    args = parser.parse_args()

    session = await get_session()
    try:
        if args.check:
            await check_state(session)
        else:
            await backfill(session, dry_run=not args.apply)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
