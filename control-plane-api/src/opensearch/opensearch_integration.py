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
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI
from opensearchpy import AsyncOpenSearch
from pydantic_settings import BaseSettings

from .audit_middleware import AuditLogger, AuditMiddleware

logger = logging.getLogger("stoa.opensearch")


class OpenSearchSettings(BaseSettings):
    """OpenSearch configuration."""
    
    opensearch_host: str = "https://opensearch.stoa.cab-i.com"
    opensearch_user: str = "admin"
    opensearch_password: str = ""
    opensearch_verify_certs: bool = False
    opensearch_timeout: int = 30
    
    # Audit settings
    audit_enabled: bool = True
    audit_buffer_size: int = 100
    audit_flush_interval: float = 5.0
    
    class Config:
        env_prefix = ""
        env_file = ".env"


@lru_cache()
def get_settings() -> OpenSearchSettings:
    """Get cached settings."""
    return OpenSearchSettings()


class OpenSearchService:
    """OpenSearch service manager."""
    
    _instance: Optional["OpenSearchService"] = None
    
    def __init__(self, settings: OpenSearchSettings):
        self.settings = settings
        self.client: Optional[AsyncOpenSearch] = None
        self.audit_logger: Optional[AuditLogger] = None
    
    @classmethod
    def get_instance(cls) -> "OpenSearchService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(get_settings())
        return cls._instance
    
    async def connect(self) -> None:
        """Initialize OpenSearch connection."""
        logger.info(f"Connecting to OpenSearch at {self.settings.opensearch_host}")
        
        self.client = AsyncOpenSearch(
            hosts=[self.settings.opensearch_host],
            http_auth=(
                self.settings.opensearch_user,
                self.settings.opensearch_password,
            ),
            verify_certs=self.settings.opensearch_verify_certs,
            ssl_show_warn=False,
            timeout=self.settings.opensearch_timeout,
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
    settings = get_settings()
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


# Example usage in main.py:
"""
from fastapi import FastAPI
from opensearch_integration import opensearch_lifespan, setup_opensearch

app = FastAPI(lifespan=opensearch_lifespan)
setup_opensearch(app)
"""
