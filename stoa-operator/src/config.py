"""Operator configuration via environment variables."""

from pydantic_settings import BaseSettings


class OperatorSettings(BaseSettings):
    """Settings loaded from STOA_OPERATOR_* environment variables."""

    CP_API_URL: str = "http://stoa-control-plane-api.stoa-system.svc.cluster.local:80"
    CP_API_KEY: str = ""
    NAMESPACE: str = "stoa-system"
    LOG_LEVEL: str = "INFO"
    RECONCILE_INTERVAL_SECONDS: int = 60
    MAX_RETRIES: int = 3

    model_config = {"env_prefix": "STOA_OPERATOR_"}


settings = OperatorSettings()
