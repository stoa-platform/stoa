"""Deterministic demo reset/seed CLI entry point (CAB-2149).

Usage::

    DATABASE_URL=postgresql+asyncpg://... python -m scripts.demo.reset
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.demo.reset --check

Purges the four demo tenants (``tenant-a/b/c/d``) and re-seeds the neutral
Customer API fixtures. Two consecutive runs produce byte-identical catalogue
state — see ``tests/demo/test_reset_isolation.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="stoa-demo-reset",
        description="Deterministic demo reset/seed (multi-client UAC scenario).",
    )
    parser.add_argument("--check", action="store_true", help="Print snapshot and exit (no mutation).")
    parser.add_argument("--reset-only", action="store_true", help="Reset without re-seeding.")
    return parser.parse_args(argv)


async def _main(args: argparse.Namespace) -> int:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.db.reset_service import DemoResetService

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required", file=sys.stderr)
        return 1

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    start = time.perf_counter()
    try:
        async with factory() as session, session.begin():
            service = DemoResetService(session)
            if args.check:
                snapshot = await service.snapshot()
                print(f"demo snapshot: {len(snapshot)} rows across {len(service.bundle.tenant_ids)} tenants")
                for row in snapshot:
                    print(f"  {row['tenant_id']}/{row['api_id']}@{row['version']}")
                return 0
            if args.reset_only:
                result = await service.reset()
                print(f"demo reset: tenants_deleted={result.tenants_deleted} apis_deleted={result.apis_deleted}")
                return 0
            result = await service.run_cycle()
            elapsed = time.perf_counter() - start
            print(
                f"demo reset+seed: tenants_deleted={result.tenants_deleted} "
                f"apis_deleted={result.apis_deleted} "
                f"tenants_created={result.tenants_created} "
                f"apis_created={result.apis_created} "
                f"elapsed={elapsed:.2f}s"
            )
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()


def cli() -> None:
    sys.exit(asyncio.run(_main(parse_args())))


if __name__ == "__main__":
    cli()
