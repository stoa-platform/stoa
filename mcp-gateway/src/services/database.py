# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Database Service for MCP Gateway.

Provides async database connection and session management.
Uses the shared Control-Plane PostgreSQL database.

Reference: CAB-XXX - Secure API Key Management with Vault & 2FA
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from ..config import get_settings
from ..models.subscription import Base

logger = structlog.get_logger(__name__)

# Global engine and session factory
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Get the database URL from environment or settings.

    Uses the shared Control-Plane PostgreSQL database.
    """
    # First, check for explicit DATABASE_URL (support both STOA_ prefixed and plain)
    database_url = os.environ.get("STOA_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url:
        # Convert postgresql:// to postgresql+asyncpg://
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return database_url

    # Build from individual components
    settings = get_settings()

    db_host = os.environ.get("DB_HOST", f"control-plane-db.stoa-system.svc.cluster.local")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME", "stoa")
    db_user = os.environ.get("DB_USER", "stoa")
    db_password = os.environ.get("DB_PASSWORD", "")

    return f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


async def init_database() -> None:
    """Initialize database connection and create tables."""
    global _engine, _session_factory

    database_url = get_database_url()

    # Mask password in logs
    safe_url = database_url
    if "@" in database_url:
        parts = database_url.split("@")
        if ":" in parts[0]:
            user_part = parts[0].rsplit(":", 1)[0]
            safe_url = f"{user_part}:***@{parts[1]}"

    logger.info("Initializing database connection", url=safe_url)

    _engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool,  # Use NullPool for serverless-friendly connections
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Note: Tables are created via Alembic migrations, not here
    # This avoids conflicts with existing tables that have different schemas
    logger.info("Database initialized successfully")


async def shutdown_database() -> None:
    """Close database connection."""
    global _engine, _session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection closed")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session context manager.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    Usage:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
