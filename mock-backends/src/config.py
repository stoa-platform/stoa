# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Configuration settings for Mock Backends service.

CAB-1018: Mock APIs for Central Bank Demo
Uses Pydantic Settings for environment-based configuration.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = Field(default="STOA Mock Backends", description="Application name")
    app_version: str = Field(default="0.2.0", description="Application version")
    environment: str = Field(default="demo", description="Environment: demo, dev, staging, prod")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8090, description="Server port")

    # Logging
    log_level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")
    log_format: str = Field(default="json", description="Log format: json, console")

    # Demo Mode
    demo_mode: bool = Field(default=True, description="Enable demo mode (synthetic data)")
    demo_scenarios_enabled: bool = Field(
        default=True, description="Enable /demo/trigger/* endpoints"
    )

    # Auth (bypass for demo)
    auth_enabled: bool = Field(default=False, description="Enable authentication")

    # Circuit Breaker Simulation (Fraud API)
    circuit_breaker_spike_probability: float = Field(
        default=0.1, description="Probability of latency spike (0.0-1.0)"
    )
    circuit_breaker_normal_latency_ms: int = Field(
        default=50, description="Normal latency in milliseconds"
    )
    circuit_breaker_spike_latency_ms: int = Field(
        default=2000, description="Spike latency in milliseconds"
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5, description="Failures before circuit opens"
    )
    circuit_breaker_recovery_timeout: int = Field(
        default=30, description="Seconds before attempting recovery"
    )

    # Idempotency Store (Settlement API)
    idempotency_ttl_seconds: int = Field(
        default=3600, description="Time-to-live for idempotency keys"
    )

    # Semantic Cache (Sanctions API)
    semantic_cache_enabled: bool = Field(default=True, description="Enable semantic cache")
    semantic_cache_ttl_seconds: int = Field(
        default=300, description="Time-to-live for cache entries"
    )

    # Data Generation
    faker_seed: int = Field(default=42, description="Seed for reproducible fake data")

    # Prometheus Metrics
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_prefix: str = Field(default="stoa", description="Metrics prefix")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience export
settings = get_settings()
