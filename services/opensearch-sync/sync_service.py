"""
STOA Platform - OpenSearch Sync Service
========================================

Synchronizes tools catalog from PostgreSQL to OpenSearch for full-text search.

Features:
- Full sync: Complete re-index of all tools
- Incremental sync: Only changed tools since last sync
- Real-time sync: Listen to PostgreSQL NOTIFY events
- Bulk operations for performance
- Retry with exponential backoff
- Health checks and metrics

Usage:
    # Full sync
    python sync_service.py --mode full

    # Incremental sync (cron job)
    python sync_service.py --mode incremental

    # Real-time listener (daemon)
    python sync_service.py --mode realtime
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
from opensearchpy import AsyncOpenSearch, helpers
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("stoa.sync")


class Settings(BaseSettings):
    """Service configuration from environment variables."""

    # PostgreSQL
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="stoa", alias="POSTGRES_DB")
    postgres_user: str = Field(default="stoa", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")

    # OpenSearch
    opensearch_host: str = Field(
        default="https://opensearch.gostoa.dev", alias="OPENSEARCH_HOST"
    )
    opensearch_user: str = Field(default="admin", alias="OPENSEARCH_USER")
    opensearch_password: str = Field(default="", alias="OPENSEARCH_PASSWORD")
    opensearch_verify_certs: bool = Field(default=True, alias="OPENSEARCH_VERIFY_CERTS")  # CAB-838: Enable SSL verification by default
    opensearch_ca_certs: Optional[str] = Field(default=None, alias="OPENSEARCH_CA_CERTS")  # CAB-838: Custom CA certificate path

    # Sync settings
    batch_size: int = Field(default=100, alias="SYNC_BATCH_SIZE")
    retry_attempts: int = Field(default=3, alias="SYNC_RETRY_ATTEMPTS")
    retry_delay: float = Field(default=1.0, alias="SYNC_RETRY_DELAY")

    class Config:
        env_file = ".env"
        extra = "ignore"


class Tool(BaseModel):
    """Tool document model for OpenSearch."""

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    tenant_id: str
    visibility: str = "private"
    version: str = "1.0.0"
    schema_: Optional[dict] = Field(default=None, alias="schema")
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    endpoints: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    stats: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True


class SyncService:
    """PostgreSQL to OpenSearch sync service."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.os_client: Optional[AsyncOpenSearch] = None
        self._last_sync_time: Optional[datetime] = None

    async def connect(self) -> None:
        """Establish connections to PostgreSQL and OpenSearch."""
        logger.info("Connecting to PostgreSQL...")
        self.pg_pool = await asyncpg.create_pool(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            database=self.settings.postgres_db,
            user=self.settings.postgres_user,
            password=self.settings.postgres_password,
            min_size=2,
            max_size=10,
        )
        logger.info("PostgreSQL connected")

        logger.info("Connecting to OpenSearch...")
        self.os_client = AsyncOpenSearch(
            hosts=[self.settings.opensearch_host],
            http_auth=(
                self.settings.opensearch_user,
                self.settings.opensearch_password,
            ),
            verify_certs=self.settings.opensearch_verify_certs,
            ssl_show_warn=self.settings.opensearch_verify_certs,  # CAB-838: Only warn when verification enabled
            ca_certs=self.settings.opensearch_ca_certs,  # CAB-838: Custom CA support
        )
        # Test connection
        info = await self.os_client.info()
        logger.info(f"OpenSearch connected: {info['cluster_name']}")

    async def disconnect(self) -> None:
        """Close all connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL disconnected")
        if self.os_client:
            await self.os_client.close()
            logger.info("OpenSearch disconnected")

    async def fetch_tools(
        self, since: Optional[datetime] = None, limit: int = 1000, offset: int = 0
    ) -> list[dict]:
        """Fetch tools from PostgreSQL."""
        async with self.pg_pool.acquire() as conn:
            if since:
                query = """
                    SELECT 
                        t.id, t.name, t.description, t.category,
                        t.tags, t.tenant_id, t.visibility, t.version,
                        t.input_schema, t.output_schema, t.metadata,
                        t.created_at, t.updated_at,
                        COALESCE(s.call_count, 0) as call_count,
                        COALESCE(s.avg_latency_ms, 0) as avg_latency_ms,
                        COALESCE(s.success_rate, 0) as success_rate,
                        s.last_called_at
                    FROM tools t
                    LEFT JOIN tool_stats s ON t.id = s.tool_id
                    WHERE t.updated_at > $1 OR s.updated_at > $1
                    ORDER BY t.updated_at DESC
                    LIMIT $2 OFFSET $3
                """
                rows = await conn.fetch(query, since, limit, offset)
            else:
                query = """
                    SELECT 
                        t.id, t.name, t.description, t.category,
                        t.tags, t.tenant_id, t.visibility, t.version,
                        t.input_schema, t.output_schema, t.metadata,
                        t.created_at, t.updated_at,
                        COALESCE(s.call_count, 0) as call_count,
                        COALESCE(s.avg_latency_ms, 0) as avg_latency_ms,
                        COALESCE(s.success_rate, 0) as success_rate,
                        s.last_called_at
                    FROM tools t
                    LEFT JOIN tool_stats s ON t.id = s.tool_id
                    ORDER BY t.updated_at DESC
                    LIMIT $1 OFFSET $2
                """
                rows = await conn.fetch(query, limit, offset)

            return [dict(row) for row in rows]

    async def fetch_deleted_tools(self, since: datetime) -> list[str]:
        """Fetch IDs of tools deleted since given time."""
        async with self.pg_pool.acquire() as conn:
            query = """
                SELECT tool_id FROM tool_deletions
                WHERE deleted_at > $1
            """
            rows = await conn.fetch(query, since)
            return [row["tool_id"] for row in rows]

    def transform_tool(self, row: dict) -> dict:
        """Transform PostgreSQL row to OpenSearch document."""
        doc = {
            "id": str(row["id"]),
            "name": row["name"],
            "description": row.get("description"),
            "category": row.get("category"),
            "tags": row.get("tags") or [],
            "tenant_id": str(row["tenant_id"]),
            "visibility": row.get("visibility", "private"),
            "version": row.get("version", "1.0.0"),
            "input_schema": row.get("input_schema"),
            "output_schema": row.get("output_schema"),
            "metadata": row.get("metadata") or {},
            "stats": {
                "call_count": row.get("call_count", 0),
                "avg_latency_ms": float(row.get("avg_latency_ms", 0)),
                "success_rate": float(row.get("success_rate", 0)),
                "last_called_at": (
                    row["last_called_at"].isoformat()
                    if row.get("last_called_at")
                    else None
                ),
            },
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        return doc

    async def index_tools(self, tools: list[dict]) -> dict:
        """Bulk index tools to OpenSearch."""
        if not tools:
            return {"indexed": 0, "errors": 0}

        actions = []
        for tool in tools:
            doc = self.transform_tool(tool)
            actions.append(
                {
                    "_index": "tools",
                    "_id": doc["id"],
                    "_source": doc,
                }
            )

        success, errors = await helpers.async_bulk(
            self.os_client,
            actions,
            chunk_size=self.settings.batch_size,
            raise_on_error=False,
        )

        return {"indexed": success, "errors": len(errors) if errors else 0}

    async def delete_tools(self, tool_ids: list[str]) -> dict:
        """Delete tools from OpenSearch."""
        if not tool_ids:
            return {"deleted": 0, "errors": 0}

        actions = []
        for tool_id in tool_ids:
            actions.append(
                {
                    "_op_type": "delete",
                    "_index": "tools",
                    "_id": tool_id,
                }
            )

        success, errors = await helpers.async_bulk(
            self.os_client,
            actions,
            chunk_size=self.settings.batch_size,
            raise_on_error=False,
        )

        return {"deleted": success, "errors": len(errors) if errors else 0}

    async def full_sync(self) -> dict:
        """Perform a full sync of all tools."""
        logger.info("Starting full sync...")
        start_time = datetime.now(timezone.utc)

        total_indexed = 0
        total_errors = 0
        offset = 0

        while True:
            tools = await self.fetch_tools(limit=self.settings.batch_size, offset=offset)
            if not tools:
                break

            result = await self.index_tools(tools)
            total_indexed += result["indexed"]
            total_errors += result["errors"]
            offset += len(tools)

            logger.info(f"Indexed batch: {len(tools)} tools (total: {total_indexed})")

        # Refresh index
        await self.os_client.indices.refresh(index="tools")

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._last_sync_time = start_time

        result = {
            "mode": "full",
            "indexed": total_indexed,
            "errors": total_errors,
            "duration_seconds": duration,
            "timestamp": start_time.isoformat(),
        }

        logger.info(f"Full sync complete: {result}")
        return result

    async def incremental_sync(self) -> dict:
        """Perform an incremental sync since last sync."""
        if not self._last_sync_time:
            logger.info("No previous sync found, falling back to full sync")
            return await self.full_sync()

        logger.info(f"Starting incremental sync since {self._last_sync_time}...")
        start_time = datetime.now(timezone.utc)

        # Fetch and index updated tools
        tools = await self.fetch_tools(since=self._last_sync_time)
        index_result = await self.index_tools(tools)

        # Fetch and delete removed tools
        deleted_ids = await self.fetch_deleted_tools(self._last_sync_time)
        delete_result = await self.delete_tools(deleted_ids)

        # Refresh index
        await self.os_client.indices.refresh(index="tools")

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._last_sync_time = start_time

        result = {
            "mode": "incremental",
            "indexed": index_result["indexed"],
            "deleted": delete_result["deleted"],
            "errors": index_result["errors"] + delete_result["errors"],
            "duration_seconds": duration,
            "timestamp": start_time.isoformat(),
        }

        logger.info(f"Incremental sync complete: {result}")
        return result

    async def realtime_listener(self) -> None:
        """Listen to PostgreSQL NOTIFY events for real-time sync."""
        logger.info("Starting real-time listener...")

        async with self.pg_pool.acquire() as conn:
            await conn.add_listener("tool_changes", self._handle_notification)
            logger.info("Listening for tool_changes notifications...")

            # Keep running
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                await conn.remove_listener("tool_changes", self._handle_notification)
                logger.info("Real-time listener stopped")

    async def _handle_notification(
        self, connection: asyncpg.Connection, pid: int, channel: str, payload: str
    ) -> None:
        """Handle a PostgreSQL NOTIFY event."""
        try:
            data = json.loads(payload)
            operation = data.get("operation")
            tool_id = data.get("id")

            logger.info(f"Received notification: {operation} for tool {tool_id}")

            if operation in ("INSERT", "UPDATE"):
                tools = await self.fetch_tools(limit=1, offset=0)
                # Find the specific tool
                tool = next((t for t in tools if str(t["id"]) == tool_id), None)
                if tool:
                    await self.index_tools([tool])
                    logger.info(f"Indexed tool {tool_id}")
            elif operation == "DELETE":
                await self.delete_tools([tool_id])
                logger.info(f"Deleted tool {tool_id}")

        except Exception as e:
            logger.error(f"Error handling notification: {e}")

    async def health_check(self) -> dict:
        """Check service health."""
        health = {
            "status": "healthy",
            "postgres": "unknown",
            "opensearch": "unknown",
            "last_sync": self._last_sync_time.isoformat() if self._last_sync_time else None,
        }

        try:
            async with self.pg_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health["postgres"] = "connected"
        except Exception as e:
            health["postgres"] = f"error: {e}"
            health["status"] = "unhealthy"

        try:
            await self.os_client.cluster.health()
            health["opensearch"] = "connected"
        except Exception as e:
            health["opensearch"] = f"error: {e}"
            health["status"] = "unhealthy"

        return health


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="STOA OpenSearch Sync Service")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental", "realtime", "health"],
        default="incremental",
        help="Sync mode",
    )
    args = parser.parse_args()

    settings = Settings()
    service = SyncService(settings)

    try:
        await service.connect()

        if args.mode == "full":
            result = await service.full_sync()
            print(json.dumps(result, indent=2))
        elif args.mode == "incremental":
            result = await service.incremental_sync()
            print(json.dumps(result, indent=2))
        elif args.mode == "realtime":
            await service.realtime_listener()
        elif args.mode == "health":
            result = await service.health_check()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result["status"] == "healthy" else 1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await service.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
