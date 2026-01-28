#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
Initial catalog sync script (CAB-682).

Syncs all APIs from GitLab to the PostgreSQL cache.
Run this after applying the Alembic migration.

Usage:
    cd control-plane-api
    python scripts/initial_catalog_sync.py

Environment Variables:
    DATABASE_URL - PostgreSQL connection string
    GITLAB_URL - GitLab server URL
    GITLAB_TOKEN - GitLab API token
    GITLAB_PROJECT_ID - GitLab project ID
"""
import asyncio
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Run initial catalog sync."""
    logger.info("=" * 60)
    logger.info("STOA Platform - Initial Catalog Sync (CAB-682)")
    logger.info("=" * 60)

    # Import here to avoid issues with environment setup
    from src.config import settings
    from src.services.git_service import GitLabService
    from src.services.catalog_sync_service import CatalogSyncService

    # Create database engine
    logger.info(f"Connecting to database...")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
    )
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Connect to GitLab
    logger.info(f"Connecting to GitLab at {settings.GITLAB_URL}...")
    git_service = GitLabService()
    await git_service.connect()
    logger.info(f"Connected to GitLab project: {git_service._project.name}")

    # Run sync
    async with async_session() as db:
        sync_service = CatalogSyncService(db, git_service)

        logger.info("Starting full catalog sync...")
        result = await sync_service.sync_all()

        logger.info("=" * 60)
        logger.info("SYNC RESULTS")
        logger.info("=" * 60)
        logger.info(f"Status: {result.status}")
        logger.info(f"Items synced: {result.items_synced}")
        logger.info(f"Duration: {result.duration_seconds:.2f}s" if result.duration_seconds else "Duration: N/A")
        logger.info(f"Git commit: {result.git_commit_sha or 'N/A'}")

        if result.errors:
            logger.warning(f"Errors encountered: {len(result.errors)}")
            for error in result.errors:
                logger.warning(f"  - {error}")
        else:
            logger.info("No errors encountered")

        logger.info("=" * 60)

    # Cleanup
    await git_service.disconnect()
    await engine.dispose()

    logger.info("Initial catalog sync completed successfully!")
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
