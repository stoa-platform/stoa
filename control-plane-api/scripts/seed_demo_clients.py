#!/usr/bin/env python3
"""Seed 100 demo mTLS clients for CAB-870 dashboard demo.

Creates clients with realistic certificate expiration distribution:
- 60 active (healthy, > 30 days)
- 15 expiring soon (7-30 days)
- 10 critical (< 7 days)
- 10 recently rotated (in grace period)
- 5 revoked

Usage:
    cd control-plane-api
    python -m scripts.seed_demo_clients

Requirements:
    - Database must be running and accessible
    - Tables must exist (run alembic migrations first)
"""

import asyncio
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TENANT_ID = "acme"

# Naming pools for realistic French enterprise clients
SECTORS = ["banque", "assurance", "logistique", "industrie", "telecom", "energie", "sante", "retail"]
COMPANIES = [
    "bnp", "axa", "geodis", "airbus", "orange", "engie", "sanofi", "carrefour",
    "socgen", "allianz", "dhl", "safran", "sfr", "edf", "pfizer", "auchan",
]
SERVICES = [
    "paiement", "sinistre", "tracking", "inventory", "billing", "pricing",
    "kyc", "compliance", "analytics", "reporting", "notification", "scoring",
]

DISTRIBUTION = [
    ("active", 60),
    ("expiring_soon", 15),
    ("critical", 10),
    ("grace_period", 10),
    ("revoked", 5),
]


def _make_name(index: int) -> tuple[str, str]:
    """Generate a realistic client name and CN."""
    sector = SECTORS[index % len(SECTORS)]
    company = COMPANIES[index % len(COMPANIES)]
    service = SERVICES[index % len(SERVICES)]
    name = f"{sector}-{company}-{service}-{index:03d}"
    cn = f"{name}.client.stoa.internal"
    return name, cn


def _make_cert_pem(cn: str) -> str:
    return (
        "-----BEGIN CERTIFICATE-----\n"
        f"MIID...MOCK...{cn[:20]}...\n"
        "-----END CERTIFICATE-----"
    )


def _generate(client_type: str, index: int) -> dict:
    """Generate mock certificate data for a given distribution type."""
    now = datetime.now(timezone.utc)
    name, cn = _make_name(index)

    not_before = now - timedelta(days=30 + index % 90)
    serial = secrets.token_hex(16)
    fingerprint = secrets.token_hex(32)
    cert_pem = _make_cert_pem(cn)

    rotation_count = 0
    last_rotated = None
    fp_prev = None
    prev_expires = None

    if client_type == "active":
        not_after = now + timedelta(days=60 + index % 300)
        status = "active"
    elif client_type == "expiring_soon":
        not_after = now + timedelta(days=7 + index % 23)
        status = "active"
    elif client_type == "critical":
        not_after = now + timedelta(days=index % 7)
        status = "active"
    elif client_type == "grace_period":
        not_after = now + timedelta(days=60 + index % 300)
        status = "active"
        fp_prev = secrets.token_hex(32)
        prev_expires = now + timedelta(hours=6 + index % 18)
        rotation_count = 1 + index % 3
        last_rotated = now - timedelta(hours=1 + index % 12)
    else:  # revoked
        not_after = now + timedelta(days=60)
        status = "revoked"

    created_at = now - timedelta(days=90 - index % 90)

    return {
        "id": str(uuid4()),
        "tenant_id": TENANT_ID,
        "name": name,
        "cn": cn,
        "serial": serial,
        "fingerprint": fingerprint,
        "cert_pem": cert_pem,
        "not_before": not_before,
        "not_after": not_after,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "fp_prev": fp_prev,
        "prev_expires": prev_expires,
        "last_rotated": last_rotated,
        "rotation_count": rotation_count,
    }


async def seed_clients(database_url: str) -> None:
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        try:
            result = await session.execute(
                text("SELECT COUNT(*) FROM clients WHERE tenant_id = :tid"),
                {"tid": TENANT_ID},
            )
            count = result.scalar_one()
            if count >= 50:
                print(f"Found {count} existing clients for '{TENANT_ID}'. Skipping seed.")
                return

            print("Seeding 100 demo clients...")
            idx = 0
            for client_type, n in DISTRIBUTION:
                for i in range(n):
                    row = _generate(client_type, idx)
                    await session.execute(
                        text("""
                            INSERT INTO clients (
                                id, tenant_id, name, certificate_cn,
                                certificate_serial, certificate_fingerprint, certificate_pem,
                                certificate_not_before, certificate_not_after,
                                status, created_at, updated_at,
                                certificate_fingerprint_previous, previous_cert_expires_at,
                                last_rotated_at, rotation_count
                            ) VALUES (
                                :id, :tenant_id, :name, :cn,
                                :serial, :fingerprint, :cert_pem,
                                :not_before, :not_after,
                                :status, :created_at, :updated_at,
                                :fp_prev, :prev_expires,
                                :last_rotated, :rotation_count
                            )
                        """),
                        row,
                    )
                    idx += 1
                    if idx % 25 == 0:
                        print(f"  [{idx}/100] ...")

            await session.commit()
            print(f"\nSeeded 100 demo clients for tenant '{TENANT_ID}'.")

            # Summary
            result = await session.execute(
                text("""
                    SELECT status, COUNT(*)
                    FROM clients WHERE tenant_id = :tid
                    GROUP BY status
                """),
                {"tid": TENANT_ID},
            )
            print("\nDistribution:")
            for row in result.all():
                print(f"  {row[0]}: {row[1]}")

        except Exception as e:
            await session.rollback()
            print(f"Error: {e}")
            raise


async def main():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa",
    )
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    await seed_clients(database_url)


if __name__ == "__main__":
    asyncio.run(main())
