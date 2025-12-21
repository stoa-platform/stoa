"""Configuration settings"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List

class Settings(BaseSettings):
    VERSION: str = "2.0.0"
    DEBUG: bool = False

    # Keycloak
    KEYCLOAK_URL: str = "https://keycloak.dev.apim.cab-i.com"
    KEYCLOAK_REALM: str = "apim-platform"
    KEYCLOAK_CLIENT_ID: str = "control-plane-api"
    KEYCLOAK_CLIENT_SECRET: str = ""

    # GitLab
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str = ""
    GITLAB_PROJECT_ID: str = ""
    GITLAB_WEBHOOK_SECRET: str = ""  # Secret token for webhook verification

    # Kafka (Redpanda)
    KAFKA_BOOTSTRAP_SERVERS: str = "redpanda:9092"

    # AWX
    AWX_URL: str = "https://awx.dev.apim.cab-i.com"
    AWX_TOKEN: str = ""

    # CORS - accepts comma-separated string or list
    CORS_ORIGINS: str = "https://devops.apim.cab-i.com,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list"""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"

settings = Settings()
