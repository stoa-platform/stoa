#!/usr/bin/env python3
"""Import APIs from a gateway into the Git catalog (CAB-2016).

One-shot bootstrap script for onboarding gateways that already have APIs.
Reads all APIs from a gateway via its adapter, generates api.yaml for each,
and commits them atomically to stoa-catalog.

Usage:
    python scripts/ops/import-gateway-to-catalog.py \
        --gateway-type kong \
        --gateway-url http://kong:8001 \
        --tenant-id acme \
        [--dry-run]
"""

import argparse
import asyncio
import json
import logging
import sys

import yaml

# Allow running from repo root
sys.path.insert(0, "control-plane-api")

from src.services.github_service import GitHubService  # noqa: E402

logger = logging.getLogger(__name__)


async def import_gateway(
    gateway_type: str,
    gateway_url: str,
    tenant_id: str,
    auth_config: dict | None = None,
    dry_run: bool = False,
) -> None:
    """Import all APIs from a gateway into the Git catalog."""
    from src.adapters.registry import AdapterRegistry

    adapter = AdapterRegistry.create(gateway_type, gateway_url, auth_config or {})
    await adapter.connect()

    try:
        apis = await adapter.list_apis()
    finally:
        await adapter.disconnect()

    if not apis:
        logger.info("No APIs found on %s gateway at %s", gateway_type, gateway_url)
        return

    logger.info("Found %d APIs on %s gateway", len(apis), gateway_type)

    actions: list[dict[str, str]] = []
    for api in apis:
        api_id = api.get("id") or api.get("apiId") or api.get("resource_id", "unknown")
        api_name = api.get("name") or api.get("apiName") or str(api_id)

        api_content = {
            "id": str(api_id),
            "name": api_name,
            "display_name": api.get("display_name", api_name),
            "version": api.get("version", "1.0.0"),
            "description": api.get("description", ""),
            "backend_url": api.get("backend_url") or api.get("backendUrl", ""),
            "spec_hash": api.get("spec_hash", ""),
            "tags": api.get("tags", []),
            "status": "active",
            "imported_from": gateway_type,
        }

        api_yaml = yaml.dump(api_content, default_flow_style=False, allow_unicode=True)
        file_path = f"tenants/{tenant_id}/apis/{api_name}/api.yaml"

        if dry_run:
            print(f"  [DRY-RUN] Would create: {file_path}")
            print(f"            API: {api_name} (id={api_id})")
        else:
            actions.append({"action": "create", "file_path": file_path, "content": api_yaml})

    if dry_run:
        print(f"\n  Total: {len(apis)} APIs would be imported for tenant '{tenant_id}'")
        return

    if not actions:
        return

    # Ensure tenant structure exists and commit all APIs atomically
    gh = GitHubService()
    await gh.connect()
    try:
        await gh._ensure_tenant_exists(tenant_id)
        project_id = gh._catalog_project_id()
        result = await gh.batch_commit(
            project_id,
            actions,
            f"Import {len(actions)} APIs from {gateway_type} for tenant {tenant_id}",
        )
        logger.info("Imported %d APIs (commit: %s)", len(actions), result["sha"][:8])
    finally:
        await gh.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import gateway APIs to Git catalog")
    parser.add_argument(
        "--gateway-type", required=True, help="Gateway type (kong, webmethods, gravitee, etc.)"
    )
    parser.add_argument("--gateway-url", required=True, help="Gateway admin URL")
    parser.add_argument("--tenant-id", required=True, help="Target tenant ID in catalog")
    parser.add_argument("--auth-config", default="{}", help="JSON auth config for the gateway")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    auth_config = json.loads(args.auth_config)

    asyncio.run(
        import_gateway(
            gateway_type=args.gateway_type,
            gateway_url=args.gateway_url,
            tenant_id=args.tenant_id,
            auth_config=auth_config,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
