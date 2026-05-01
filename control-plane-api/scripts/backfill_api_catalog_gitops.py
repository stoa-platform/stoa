#!/usr/bin/env python3
"""Backfill active API catalog rows into ``stoa-catalog``.

Run from the control-plane-api environment so ``DATABASE_URL`` and the GitHub
catalog credentials come from the same settings used by production.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill DB-only APIs into stoa-catalog GitOps files")
    parser.add_argument("--tenant", default=None, help="Restrict to one tenant_id")
    parser.add_argument("--api-id", default=None, help="Restrict to one api_id")
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to process")
    parser.add_argument("--dry-run", action="store_true", help="Read DB/Git and report only")
    parser.add_argument(
        "--include-git-tracked",
        action="store_true",
        help="Also re-project rows that already have git_path, git_commit_sha and catalog_content_hash",
    )
    parser.add_argument(
        "--overwrite-conflicts",
        action="store_true",
        help="Update an existing remote api.yaml when it differs from the DB projection",
    )
    args = parser.parse_args()

    from src.config import settings
    from src.services.catalog_git_client.github_contents import GitHubContentsCatalogClient
    from src.services.github_service import GitHubService
    from src.services.gitops_writer.backfill import GitOpsCatalogBackfill

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    github_service = GitHubService()
    await github_service.connect()
    try:
        git_client = GitHubContentsCatalogClient(github_service=github_service)
        async with session_factory() as session:
            backfill = GitOpsCatalogBackfill(
                catalog_git_client=git_client,
                db_session=session,
                actor="catalog-backfill-script",
                overwrite_conflicts=args.overwrite_conflicts,
            )
            results = await backfill.backfill(
                tenant_id=args.tenant,
                api_id=args.api_id,
                include_git_tracked=args.include_git_tracked,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()

        counts = Counter(result.status for result in results)
        logger.info("Processed %d API rows", len(results))
        for status, count in sorted(counts.items()):
            logger.info("%s: %d", status, count)
        for result in results:
            logger.info(
                "%s/%s status=%s git_path=%s commit=%s detail=%s",
                result.tenant_id,
                result.api_id,
                result.status,
                result.git_path or "-",
                result.git_commit_sha or "-",
                result.detail or "-",
            )

        blocking_statuses = {
            "invalid_committed_yaml",
            "read_after_commit_failed",
            "remote_conflict",
            "skipped_invalid_row",
            "skipped_uuid_hard_drift",
        }
        if any(result.status in blocking_statuses for result in results):
            logger.error("Backfill completed with blocking statuses; inspect rows above")
            return 2
        return 0
    finally:
        await github_service.disconnect()
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
