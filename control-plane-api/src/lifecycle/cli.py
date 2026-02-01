"""
Tenant Lifecycle CLI
CAB-409: Entry point for CronJob and manual operations

Usage:
    python -m src.lifecycle.cli run-lifecycle-check
    python -m src.lifecycle.cli tenant-status <tenant_id>
    python -m src.lifecycle.cli force-cleanup <tenant_id>
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

# Configure structured logging for K8s
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("stoa.lifecycle.cli")


async def run_lifecycle_check():
    """Main cron entry point."""
    from .service import TenantLifecycleService
    from .notifications import NotificationService
    from .cleanup import CleanupService

    logger.info("Starting lifecycle check...")

    # TODO: Replace with actual implementation once DB deps are wired
    # async with get_db_session() as db:
    #     notification_service = NotificationService(db)
    #     cleanup_service = CleanupService(db)
    #     service = TenantLifecycleService(db, notification_service, cleanup_service)
    #     summary = await service.run_lifecycle_check()
    #     print(json.dumps(summary.model_dump(), default=str, indent=2))

    logger.info("Lifecycle check completed")


async def tenant_status(tenant_id: str):
    """Check a single tenant's lifecycle status."""
    logger.info(f"Checking status for tenant: {tenant_id}")
    # TODO: Wire and call service.get_status(tenant_id)


async def force_cleanup(tenant_id: str):
    """Force cleanup of a specific tenant (admin operation)."""
    logger.warning(f"Force cleanup requested for tenant: {tenant_id}")
    # TODO: Wire and call cleanup_service.cleanup_tenant(tenant_id)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.lifecycle.cli <command> [args]")
        print("Commands: run-lifecycle-check, tenant-status <id>, force-cleanup <id>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "run-lifecycle-check":
        asyncio.run(run_lifecycle_check())
    elif command == "tenant-status" and len(sys.argv) > 2:
        asyncio.run(tenant_status(sys.argv[2]))
    elif command == "force-cleanup" and len(sys.argv) > 2:
        asyncio.run(force_cleanup(sys.argv[2]))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
