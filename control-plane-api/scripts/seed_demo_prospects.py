#!/usr/bin/env python3
"""Seed demo prospects for Feb 26 demo (CAB-911).

Creates 12 demo prospects with various statuses, events, and NPS feedback
for testing the admin prospects dashboard.

Usage:
    cd control-plane-api
    python -m scripts.seed_demo_prospects

Requirements:
    - Database must be running and accessible
    - Tables must exist (run alembic migrations first)
"""

import asyncio
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Demo prospect data
DEMO_PROSPECTS = [
    # Nexora Energy - 3 prospects
    {
        "company": "Nexora Energy",
        "email": "pierre.martin@nexora-energy.com",
        "status": "converted",
        "nps_score": 9,
        "nps_comment": "Le MCP Gateway m'a bluffé ! Exactement ce qu'il nous faut.",
        "events": ["invite_opened", "page_viewed", "tool_called", "tool_called", "tool_called"],
    },
    {
        "company": "Nexora Energy",
        "email": "marie.dupont@nexora-energy.com",
        "status": "opened",
        "nps_score": None,
        "nps_comment": None,
        "events": ["invite_opened", "page_viewed"],
    },
    {
        "company": "Nexora Energy",
        "email": "jean.bernard@nexora-energy.com",
        "status": "pending",
        "nps_score": None,
        "nps_comment": None,
        "events": [],
    },
    # Maison Aurèle - 3 prospects
    {
        "company": "Maison Aurèle",
        "email": "sophie.laurent@maison-aurele.com",
        "status": "converted",
        "nps_score": 10,
        "nps_comment": "Excellent ! On passe en POC la semaine prochaine.",
        "events": ["invite_opened", "page_viewed", "tool_called", "tool_called", "error_encountered", "tool_called"],
    },
    {
        "company": "Maison Aurèle",
        "email": "paul.moreau@maison-aurele.com",
        "status": "converted",
        "nps_score": 8,
        "nps_comment": "Très prometteur, quelques ajustements à faire.",
        "events": ["invite_opened", "page_viewed", "tool_called"],
    },
    {
        "company": "Maison Aurèle",
        "email": "claire.petit@maison-aurele.com",
        "status": "expired",
        "nps_score": None,
        "nps_comment": None,
        "events": [],
    },
    # Helios Power - 2 prospects
    {
        "company": "Helios Power",
        "email": "marc.lefebvre@helios-power.com",
        "status": "converted",
        "nps_score": 9,
        "nps_comment": "Impressionnant la vitesse d'intégration.",
        "events": ["invite_opened", "page_viewed", "tool_called", "tool_called"],
    },
    {
        "company": "Helios Power",
        "email": "anne.robert@helios-power.com",
        "status": "opened",
        "nps_score": 7,
        "nps_comment": "Bien mais besoin de plus de documentation.",
        "events": ["invite_opened", "page_viewed", "page_viewed"],
    },
    # Atlas Finance - 2 prospects
    {
        "company": "Atlas Finance",
        "email": "thomas.girard@atlas-finance.com",
        "status": "converted",
        "nps_score": 6,
        "nps_comment": "Intéressant mais questions sur la sécurité.",
        "events": ["invite_opened", "page_viewed", "tool_called", "error_encountered"],
    },
    {
        "company": "Atlas Finance",
        "email": "julie.simon@atlas-finance.com",
        "status": "pending",
        "nps_score": None,
        "nps_comment": None,
        "events": [],
    },
    # Prism Telecom - 2 prospects
    {
        "company": "Prism Telecom",
        "email": "david.michel@prism-telecom.com",
        "status": "converted",
        "nps_score": 10,
        "nps_comment": "Fantastique ! On veut être early adopter.",
        "events": ["invite_opened", "page_viewed", "tool_called", "tool_called", "tool_called", "tool_called"],
    },
    {
        "company": "Prism Telecom",
        "email": "laura.blanc@prism-telecom.com",
        "status": "expired",
        "nps_score": None,
        "nps_comment": None,
        "events": ["invite_opened"],
    },
]


def generate_token() -> str:
    """Generate a secure invite token."""
    return secrets.token_urlsafe(32)


async def seed_prospects(database_url: str) -> None:
    """Insert demo prospects with events and feedback."""
    print(f"Connecting to database...")

    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Check if we already have demo data
            result = await session.execute(
                text("SELECT COUNT(*) FROM stoa.invites WHERE source = 'demo_seed'")
            )
            count = result.scalar_one()
            if count > 0:
                print(f"Found {count} existing demo prospects. Skipping seed.")
                print("To re-seed, first delete existing demo data:")
                print("  DELETE FROM stoa.prospect_events WHERE invite_id IN (SELECT id FROM stoa.invites WHERE source = 'demo_seed');")
                print("  DELETE FROM prospect_feedback WHERE invite_id IN (SELECT id FROM stoa.invites WHERE source = 'demo_seed');")
                print("  DELETE FROM stoa.invites WHERE source = 'demo_seed';")
                return

            print(f"Seeding {len(DEMO_PROSPECTS)} demo prospects...")

            now = datetime.now(timezone.utc)

            for i, prospect in enumerate(DEMO_PROSPECTS):
                invite_id = uuid4()

                # Calculate dates based on status
                created_at = now - timedelta(days=7 - i % 5, hours=i % 24)
                expires_at = created_at + timedelta(days=7)

                if prospect["status"] == "expired":
                    expires_at = now - timedelta(days=1)
                    opened_at = created_at + timedelta(hours=1) if prospect["events"] else None
                elif prospect["status"] in ("opened", "converted"):
                    opened_at = created_at + timedelta(hours=2 + i % 5)
                else:
                    opened_at = None

                # Insert invite
                await session.execute(
                    text("""
                        INSERT INTO stoa.invites (id, email, company, token, source, status, created_at, expires_at, opened_at)
                        VALUES (:id, :email, :company, :token, :source, :status, :created_at, :expires_at, :opened_at)
                    """),
                    {
                        "id": invite_id,
                        "email": prospect["email"],
                        "company": prospect["company"],
                        "token": generate_token(),
                        "source": "demo_seed",
                        "status": prospect["status"],
                        "created_at": created_at,
                        "expires_at": expires_at,
                        "opened_at": opened_at,
                    },
                )

                # Insert events
                event_time = opened_at or created_at
                for j, event_type in enumerate(prospect["events"]):
                    event_time = event_time + timedelta(minutes=5 + j * 3)

                    metadata = {}
                    if event_type == "tool_called":
                        metadata = {"tool": ["stoa_list_tools", "stoa_list_apis", "stoa_create_subscription"][j % 3]}
                    elif event_type == "page_viewed":
                        metadata = {"page": ["/console/dashboard", "/console/mcp-gateway", "/console/subscriptions"][j % 3]}
                    elif event_type == "error_encountered":
                        metadata = {"error": "403 Forbidden", "tool": "stoa_admin_users"}

                    await session.execute(
                        text("""
                            INSERT INTO stoa.prospect_events (id, invite_id, event_type, metadata, timestamp)
                            VALUES (:id, :invite_id, :event_type, :metadata::jsonb, :timestamp)
                        """),
                        {
                            "id": uuid4(),
                            "invite_id": invite_id,
                            "event_type": event_type,
                            "metadata": str(metadata).replace("'", '"'),  # Convert to JSON
                            "timestamp": event_time,
                        },
                    )

                # Insert feedback if provided
                if prospect["nps_score"] is not None:
                    await session.execute(
                        text("""
                            INSERT INTO prospect_feedback (id, invite_id, nps_score, comment, created_at)
                            VALUES (:id, :invite_id, :nps_score, :comment, :created_at)
                        """),
                        {
                            "id": uuid4(),
                            "invite_id": invite_id,
                            "nps_score": prospect["nps_score"],
                            "comment": prospect["nps_comment"],
                            "created_at": event_time + timedelta(hours=1) if opened_at else now,
                        },
                    )

                print(f"  [{i+1}/{len(DEMO_PROSPECTS)}] {prospect['company']} - {prospect['email']} ({prospect['status']})")

            await session.commit()
            print(f"\nSuccessfully seeded {len(DEMO_PROSPECTS)} demo prospects!")

            # Print summary
            print("\nSummary by status:")
            result = await session.execute(
                text("SELECT status, COUNT(*) FROM stoa.invites WHERE source = 'demo_seed' GROUP BY status ORDER BY status")
            )
            for row in result.all():
                print(f"  {row[0]}: {row[1]}")

            print("\nSummary by company:")
            result = await session.execute(
                text("SELECT company, COUNT(*) FROM stoa.invites WHERE source = 'demo_seed' GROUP BY company ORDER BY COUNT(*) DESC")
            )
            for row in result.all():
                print(f"  {row[0]}: {row[1]}")

        except Exception as e:
            await session.rollback()
            print(f"Error seeding prospects: {e}")
            raise


async def main():
    """Main entry point."""
    import os

    # Get database URL from environment or use default
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa"
    )

    # Convert to async driver if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await seed_prospects(database_url)


if __name__ == "__main__":
    asyncio.run(main())
