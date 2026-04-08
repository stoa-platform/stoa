"""CLI entrypoint for the STOA seeder.

Usage:
    python -m scripts.seeder --profile dev
    python -m scripts.seeder --profile staging --dry-run
    python -m scripts.seeder --profile prod
    python -m scripts.seeder --profile dev --check
    python -m scripts.seeder --profile dev --reset
    python -m scripts.seeder --profile dev --step tenants
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure control-plane-api root is on sys.path
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="stoa-seeder",
        description="STOA Platform — Unified Database Seeder",
    )
    parser.add_argument(
        "--profile",
        choices=["dev", "staging", "prod"],
        default=os.environ.get("SEED_PROFILE", "dev"),
        help="Seed profile (default: dev or $SEED_PROFILE)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log planned operations without writing to the database",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify expected data exists (exit 0 if complete, 1 if missing)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete seed data before re-creating (blocked in prod profile)",
    )
    parser.add_argument(
        "--step",
        type=str,
        default=None,
        help="Run only this step (e.g., --step tenants)",
    )
    return parser.parse_args(argv)


async def main(args: argparse.Namespace) -> int:
    """Run the seeder."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from scripts.seeder.runner import SeederRunner

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required", file=sys.stderr)
        return 1

    print(f"STOA Seeder — profile={args.profile}", flush=True)

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            async with session.begin():
                runner = SeederRunner(
                    session=session,
                    profile=args.profile,
                    dry_run=args.dry_run,
                    check_only=args.check,
                    reset=args.reset,
                    step=args.step,
                )
                result = await runner.run()

            if result.exit_code == 0 and not args.dry_run and not args.check:
                # Commit was done by the context manager
                pass

            if args.check and result.missing:
                print(f"\nMissing entities ({len(result.missing)}):")
                for m in result.missing:
                    print(f"  - {m}")

            if result.error:
                print(f"\nERROR: {result.error}", file=sys.stderr)

            return result.exit_code

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()


def cli() -> None:
    """CLI entry point."""
    args = parse_args()

    try:
        from scripts.seeder.runner import VALID_PROFILES

        if args.profile not in VALID_PROFILES:
            print(
                f"Unknown profile: {args.profile}. Valid: {', '.join(VALID_PROFILES)}",
                file=sys.stderr,
            )
            sys.exit(1)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
