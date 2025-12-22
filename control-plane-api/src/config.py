"""Configuration settings for Control-Plane API

All settings can be overridden via environment variables.
For Kubernetes deployments, set these in ConfigMaps/Secrets.
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import os

# Base domain - used to construct default URLs
_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "apim.cab-i.com")

class Settings(BaseSettings):
    # Application
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # dev, staging, production

    # Base domain for URL construction
    BASE_DOMAIN: str = _BASE_DOMAIN

    # Keycloak Authentication
    KEYCLOAK_URL: str = f"https://auth.{_BASE_DOMAIN}"
    KEYCLOAK_REALM: str = "apim"
    KEYCLOAK_CLIENT_ID: str = "control-plane-api"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_VERIFY_SSL: bool = True

    # GitLab Integration (apim-gitops repository)
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str = ""
    GITLAB_PROJECT_ID: str = "77260481"  # PotoMitan1/apim-gitops
    GITLAB_PROJECT_PATH: str = "PotoMitan1/apim-gitops"
    GITLAB_WEBHOOK_SECRET: str = ""
    GITLAB_DEFAULT_BRANCH: str = "main"

    # Kafka/Redpanda Event Streaming
    KAFKA_BOOTSTRAP_SERVERS: str = "redpanda.apim-system.svc.cluster.local:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"  # PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL
    KAFKA_SASL_MECHANISM: str = ""  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""

    # AWX Automation
    AWX_URL: str = f"https://awx.{_BASE_DOMAIN}"
    AWX_TOKEN: str = ""
    AWX_VERIFY_SSL: bool = True

    # API Gateway
    GATEWAY_URL: str = f"https://gateway.{_BASE_DOMAIN}"
    GATEWAY_ADMIN_USER: str = "Administrator"
    GATEWAY_ADMIN_PASSWORD: str = ""

    # Gateway Admin Proxy API (OIDC secured)
    # Uses the Gateway-Admin-API proxy instead of direct Basic Auth
    GATEWAY_ADMIN_PROXY_URL: str = f"https://apis.{_BASE_DOMAIN}/gateway/Gateway-Admin-API/1.0"
    GATEWAY_USE_OIDC_PROXY: bool = True  # Set to False to use Basic Auth directly

    # CORS - comma-separated list of allowed origins
    CORS_ORIGINS: str = f"https://devops.{_BASE_DOMAIN},http://localhost:3000,http://localhost:5173"

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json, text

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list"""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"

settings = Settings()
