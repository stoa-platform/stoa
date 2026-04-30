"""
STOA Platform - OpenSearch Integration
======================================

FastAPI integration module for OpenSearch services.

Provides:
- OpenSearch client initialization
- Audit logger dependency
- Search service dependency
- Health checks
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from opensearchpy import AsyncOpenSearch

from src.config import OpenSearchAuditConfig, settings

from .audit_middleware import AuditLogger

logger = logging.getLogger("stoa.opensearch")


def get_settings() -> OpenSearchAuditConfig:
    """Return the OpenSearch audit-endpoint config (CAB-2199 / INFRA-1a S3).

    Backward-compatible accessor: legacy callers used to import
    ``get_settings`` from this module to receive the standalone
    ``OpenSearchSettings`` Pydantic class. After CAB-2199 consolidation,
    OpenSearch audit config lives in main ``Settings.opensearch_audit``
    (a sub-model hydrated from the same flat env vars). This function
    returns that sub-model to keep call-sites that use it unchanged.
    """
    return settings.opensearch_audit


class OpenSearchService:
    """OpenSearch service manager."""

    _instance: Optional["OpenSearchService"] = None

    def __init__(self, settings: OpenSearchAuditConfig):
        self.settings = settings
        self.client: AsyncOpenSearch | None = None
        self.audit_logger: AuditLogger | None = None

    @classmethod
    def get_instance(cls) -> "OpenSearchService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(get_settings())
        return cls._instance

    async def connect(self) -> None:
        """Initialize OpenSearch connection."""
        logger.info(f"Connecting to OpenSearch at {self.settings.host}")

        self.client = AsyncOpenSearch(
            hosts=[self.settings.host],
            http_auth=(
                self.settings.user,
                # CAB-2199 §3.1: password is now SecretStr; unwrap at the
                # boundary for the OpenSearch client which needs the raw value.
                self.settings.password.get_secret_value(),
            ),
            verify_certs=self.settings.verify_certs,
            ssl_show_warn=self.settings.verify_certs,  # CAB-838: Only warn when verification enabled
            ca_certs=self.settings.ca_certs,  # CAB-838: Custom CA support
            timeout=self.settings.timeout,
        )

        # Test connection
        try:
            info = await self.client.info()
            logger.info(f"Connected to OpenSearch cluster: {info['cluster_name']}")
        except Exception as e:
            logger.error(f"Failed to connect to OpenSearch: {e}")
            raise

        # Initialize audit logger
        if self.settings.audit_enabled:
            self.audit_logger = AuditLogger(
                client=self.client,
                buffer_size=self.settings.audit_buffer_size,
                flush_interval=self.settings.audit_flush_interval,
            )
            logger.info("Audit logger initialized")

    async def disconnect(self) -> None:
        """Close OpenSearch connection."""
        if self.audit_logger:
            await self.audit_logger.flush()
            logger.info("Audit logger flushed")

        if self.client:
            await self.client.close()
            logger.info("OpenSearch connection closed")

    async def health_check(self) -> dict:
        """Check OpenSearch health."""
        try:
            health = await self.client.cluster.health()
            return {
                "status": health["status"],
                "cluster_name": health["cluster_name"],
                "number_of_nodes": health["number_of_nodes"],
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }


# FastAPI lifespan manager
@asynccontextmanager
async def opensearch_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage OpenSearch connection lifecycle."""
    service = OpenSearchService.get_instance()
    await service.connect()
    yield
    await service.disconnect()


# Dependency injection
async def get_opensearch_client() -> AsyncOpenSearch:
    """Get OpenSearch client dependency."""
    service = OpenSearchService.get_instance()
    if not service.client:
        raise RuntimeError("OpenSearch not initialized")
    return service.client


async def get_audit_logger() -> AuditLogger:
    """Get audit logger dependency."""
    service = OpenSearchService.get_instance()
    if not service.audit_logger:
        raise RuntimeError("Audit logger not initialized")
    return service.audit_logger


async def setup_opensearch(app: FastAPI) -> None:
    """Setup OpenSearch integration for FastAPI app."""
    get_settings()
    service = OpenSearchService.get_instance()

    # Connect to OpenSearch
    try:
        await service.connect()
        logger.info("OpenSearch service connected")
    except Exception as e:
        logger.warning(f"OpenSearch connection failed (non-fatal): {e}")
        return  # Continue without OpenSearch

    # Add health check endpoint
    @app.get("/health/opensearch", include_in_schema=False)
    async def opensearch_health():
        return await service.health_check()

    if service.audit_logger:
        logger.info("Audit logger ready — middleware uses lazy lookup via OpenSearchService")
