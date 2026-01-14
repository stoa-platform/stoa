"""Alembic environment configuration"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import sys
import os
from pathlib import Path

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Base from database - this no longer creates async engine at import time
from src.database import Base

# Import all models to register them with Base.metadata
from src.models.subscription import Subscription
from src.models.mcp_subscription import MCPServer, MCPServerTool, MCPServerSubscription, MCPToolAccess

# this is the Alembic Config object
config = context.config


def get_database_url():
    """Get sync database URL for migrations"""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Convert async URL to sync URL
        return database_url.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
    # Fallback to config
    from src.config import settings
    return settings.database_url_sync


# Set the database URL
config.set_main_option("sqlalchemy.url", get_database_url())

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
