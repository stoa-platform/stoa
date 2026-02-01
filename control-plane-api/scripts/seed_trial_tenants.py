"""
Seed existing tenants with trial lifecycle data.
CAB-409 / COUNCIL #3: Standalone -- does NOT require CAB-408 (Self-Onboarding).

Usage:
    python scripts/seed_trial_tenants.py                    # All non-system tenants
    python scripts/seed_trial_tenants.py --tenant-id abc123 # Specific tenant
    python scripts/seed_trial_tenants.py --days-offset -10  # Simulate 10-day-old trial
    python scripts/seed_trial_tenants.py --dry-run          # Preview without changes
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent dir to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


async def seed_tenants(
    database_url: str,
    tenant_id: str | None = None,
    days_offset: int = 0,
    dry_run: bool = False,
):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Find tenants without lifecycle data
        from src.models.tenant import Tenant

        conditions = [Tenant.trial_expires_at.is_(None)]
        if tenant_id:
            conditions.append(Tenant.id == tenant_id)

        stmt = select(Tenant).where(*conditions)
        result = await session.execute(stmt)
        tenants = result.scalars().all()

        if not tenants:
            print("No tenants to seed.")
            return

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=14 + days_offset)

        for t in tenants:
            print(f"  {'[DRY RUN] ' if dry_run else ''}Seeding {t.id}: "
                  f"lifecycle_state=active, trial_expires_at={expires_at.isoformat()}")
            if not dry_run:
                t.lifecycle_state = "active"
                t.trial_expires_at = expires_at
                t.lifecycle_changed_at = now

        if not dry_run:
            await session.commit()
            print(f"Seeded {len(tenants)} tenant(s).")
        else:
            print(f"[DRY RUN] Would seed {len(tenants)} tenant(s).")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Seed trial lifecycle data on existing tenants")
    parser.add_argument("--tenant-id", type=str, default=None, help="Specific tenant ID")
    parser.add_argument("--days-offset", type=int, default=0, help="Offset in days (negative = older trial)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        from src.config import settings
        database_url = settings.DATABASE_URL

    print(f"Seeding tenants (offset={args.days_offset}d, dry_run={args.dry_run})")
    asyncio.run(seed_tenants(database_url, args.tenant_id, args.days_offset, args.dry_run))


if __name__ == "__main__":
    main()
