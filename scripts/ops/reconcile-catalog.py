#!/usr/bin/env python3
"""
Catalog reconciliation script (CAB-2013).

One-shot script to reconcile the PostgreSQL database with the
stoa-catalog GitHub repository:

1. Fix obsolete environments/dev/config.yaml (apim.cab-i.com → gostoa.dev)
2. For each active API in DB absent from Git → create api.yaml + openapi.yaml
3. For each API in Git absent from DB → report as orphan (no delete)
4. For each tenant in DB absent from Git → create tenant.yaml
5. Report: N APIs added, M orphans, K already aligned, T tenants created

Usage:
    cd control-plane-api
    python ../scripts/ops/reconcile-catalog.py [--dry-run]

Environment Variables:
    DATABASE_URL - PostgreSQL connection string
    GITHUB_TOKEN - GitHub API token
    GITHUB_ORG   - GitHub organization (default: stoa-platform)
    GITHUB_CATALOG_REPO - Catalog repo name (default: stoa-catalog)
    BASE_DOMAIN  - Platform domain (default: gostoa.dev)
"""

import argparse
import asyncio
import logging
import os
import sys

# Add control-plane-api to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "control-plane-api"))

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def fix_environment_config(github_service, dry_run: bool) -> bool:
    """Fix environments/dev/config.yaml — replace obsolete apim.cab-i.com with gostoa.dev."""
    project_id = github_service._catalog_project_id()
    config_path = "environments/dev/config.yaml"

    config_content = yaml.dump(
        {
            "environment": "dev",
            "domain": "gostoa.dev",
            "api_url": "https://api.gostoa.dev",
            "auth_url": "https://auth.gostoa.dev",
            "gateway_url": "https://mcp.gostoa.dev",
            "portal_url": "https://portal.gostoa.dev",
            "console_url": "https://console.gostoa.dev",
        },
        default_flow_style=False,
        allow_unicode=True,
    )

    if dry_run:
        logger.info("[DRY-RUN] Would create/update %s", config_path)
        return True

    try:
        # Try to update existing file
        await github_service.update_file(
            project_id,
            config_path,
            config_content,
            "chore(catalog): fix dev config — replace apim.cab-i.com with gostoa.dev (CAB-2013)",
        )
        logger.info("Updated %s", config_path)
    except FileNotFoundError:
        # File doesn't exist, create it
        await github_service.create_file(
            project_id,
            config_path,
            config_content,
            "chore(catalog): create dev config with gostoa.dev domain (CAB-2013)",
        )
        logger.info("Created %s", config_path)

    return True


async def get_git_state(github_service) -> tuple[set[str], dict[str, set[str]]]:
    """Read current catalog state from GitHub.

    Returns:
        (git_tenants, git_apis) where git_apis maps tenant_id → set of api_ids
    """
    full_tree = await github_service.get_full_tree_recursive("tenants")
    tenant_apis = github_service.parse_tree_to_tenant_apis(full_tree)

    git_tenants: set[str] = set()
    git_apis: dict[str, set[str]] = {}

    # Extract tenants from tree (directories directly under tenants/)
    for item in full_tree:
        path = item.get("path", "")
        if path.count("/") == 0 and item.get("type") == "tree":
            git_tenants.add(path)

    for tenant_id, api_ids in tenant_apis.items():
        git_tenants.add(tenant_id)
        git_apis[tenant_id] = set(api_ids)

    return git_tenants, git_apis


async def get_db_state(db: AsyncSession) -> tuple:
    """Read current state from PostgreSQL.

    Returns:
        (db_tenants, db_apis) where:
        - db_tenants maps tenant_id → tenant dict
        - db_apis maps tenant_id → list of API dicts
    """
    from src.models.catalog import APICatalog
    from src.models.tenant import Tenant, TenantStatus

    # Active tenants
    result = await db.execute(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE.value))
    tenants = result.scalars().all()
    db_tenants = {
        t.id: {
            "name": t.name,
            "description": t.description or "",
            "status": t.status,
            "settings": t.settings or {},
        }
        for t in tenants
    }

    # Active APIs (not soft-deleted)
    result = await db.execute(select(APICatalog).where(APICatalog.deleted_at.is_(None)))
    apis = result.scalars().all()
    db_apis: dict[str, list[dict]] = {}
    for api in apis:
        if api.tenant_id not in db_apis:
            db_apis[api.tenant_id] = []
        db_apis[api.tenant_id].append(
            {
                "id": api.api_id,
                "name": api.api_name,
                "version": api.version or "1.0.0",
                "description": (api.api_metadata or {}).get("description", ""),
                "backend_url": (api.api_metadata or {}).get("backend_url", ""),
                "tags": api.tags or [],
                "status": api.status or "active",
                "category": api.category,
                "openapi_spec": api.openapi_spec,
                "api_metadata": api.api_metadata or {},
            }
        )

    return db_tenants, db_apis


async def reconcile(github_service, db: AsyncSession, dry_run: bool) -> dict:
    """Run the full reconciliation."""
    stats = {
        "apis_added": 0,
        "apis_orphan": 0,
        "apis_aligned": 0,
        "tenants_created": 0,
        "tenants_aligned": 0,
        "orphan_details": [],
    }

    logger.info("Reading DB state...")
    db_tenants, db_apis = await get_db_state(db)
    logger.info("Found %d tenants, %d APIs in DB", len(db_tenants), sum(len(v) for v in db_apis.values()))

    logger.info("Reading Git state...")
    git_tenants, git_apis = await get_git_state(github_service)
    logger.info("Found %d tenants, %d APIs in Git", len(git_tenants), sum(len(v) for v in git_apis.values()))

    # --- Tenant reconciliation ---
    for tenant_id, tenant_data in db_tenants.items():
        if tenant_id in git_tenants:
            stats["tenants_aligned"] += 1
            continue

        logger.info("Tenant '%s' in DB but not in Git — creating", tenant_id)
        if not dry_run:
            await github_service.create_tenant_structure(tenant_id, tenant_data)
        stats["tenants_created"] += 1

    # --- API reconciliation: DB → Git ---
    all_db_api_keys: set[tuple[str, str]] = set()
    for tenant_id, apis in db_apis.items():
        git_api_ids = git_apis.get(tenant_id, set())

        for api in apis:
            api_id = api["id"]
            all_db_api_keys.add((tenant_id, api_id))

            if api_id in git_api_ids:
                stats["apis_aligned"] += 1
                continue

            logger.info("API '%s/%s' in DB but not in Git — creating", tenant_id, api_id)
            if not dry_run:
                api_data = {
                    "name": api["name"],
                    "id": api["id"],
                    "display_name": api.get("api_metadata", {}).get("display_name", api["name"]),
                    "version": api["version"],
                    "description": api["description"],
                    "backend_url": api["backend_url"],
                    "tags": api["tags"],
                }
                if api.get("openapi_spec"):
                    api_data["openapi_spec"] = yaml.dump(
                        api["openapi_spec"],
                        default_flow_style=False,
                        allow_unicode=True,
                    )
                try:
                    await github_service.create_api(tenant_id, api_data)
                except ValueError as exc:
                    logger.warning("Skipped API %s/%s: %s", tenant_id, api_id, exc)
                    continue
            stats["apis_added"] += 1

    # --- API reconciliation: Git → DB (orphan detection) ---
    for tenant_id, api_ids in git_apis.items():
        for api_id in api_ids:
            if (tenant_id, api_id) not in all_db_api_keys:
                stats["apis_orphan"] += 1
                stats["orphan_details"].append(f"{tenant_id}/{api_id}")
                logger.warning("API '%s/%s' in Git but not in DB — ORPHAN", tenant_id, api_id)

    return stats


async def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile stoa-catalog Git ↔ PostgreSQL (CAB-2013)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't modify Git")
    parser.add_argument("--skip-config-fix", action="store_true", help="Skip environments/dev/config.yaml fix")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("STOA Platform — Catalog Reconciliation (CAB-2013)")
    logger.info("Mode: %s", "DRY-RUN" if args.dry_run else "LIVE")
    logger.info("=" * 60)

    from src.config import settings
    from src.services.github_service import GitHubService

    # Connect to GitHub
    github_service = GitHubService()
    await github_service.connect()
    logger.info("Connected to GitHub (%s/%s)", settings.GITHUB_ORG, settings.GITHUB_CATALOG_REPO)

    # Connect to database
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # Step 1: Fix obsolete environment config
        if not args.skip_config_fix:
            logger.info("")
            logger.info("--- Step 1: Fix environment config ---")
            await fix_environment_config(github_service, args.dry_run)

        # Step 2+3: Reconcile APIs + Tenants
        logger.info("")
        logger.info("--- Step 2: Reconcile DB ↔ Git ---")
        async with session_factory() as db:
            stats = await reconcile(github_service, db, args.dry_run)

        # Report
        logger.info("")
        logger.info("=" * 60)
        logger.info("RECONCILIATION REPORT")
        logger.info("=" * 60)
        logger.info("Tenants created in Git : %d", stats["tenants_created"])
        logger.info("Tenants already aligned: %d", stats["tenants_aligned"])
        logger.info("APIs added to Git      : %d", stats["apis_added"])
        logger.info("APIs already aligned   : %d", stats["apis_aligned"])
        logger.info("APIs orphan (Git only) : %d", stats["apis_orphan"])
        if stats["orphan_details"]:
            logger.info("Orphan details:")
            for orphan in stats["orphan_details"]:
                logger.info("  - %s", orphan)
        logger.info("=" * 60)

        divergence = stats["apis_added"] + stats["apis_orphan"]
        if divergence == 0:
            logger.info("DB ↔ Git divergence: 0 — fully aligned")
        else:
            logger.info(
                "DB ↔ Git divergence: %d (added=%d, orphans=%d)", divergence, stats["apis_added"], stats["apis_orphan"]
            )

        return 0

    finally:
        await github_service.disconnect()
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
