from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    app_name: str = "APIM Control Plane API"
    environment: str = "dev"
    debug: bool = False

    # webMethods
    webmethods_url: str
    webmethods_username: str
    webmethods_password: str

    # AWS Cognito
    cognito_region: str = "eu-west-1"
    cognito_user_pool_id: str
    cognito_client_id: Optional[str] = None

    # AWS
    aws_region: str = "eu-west-1"
    dynamodb_tenants_table: str = "apim-tenants-dev"
    dynamodb_apis_table: str = "apim-apis-metadata-dev"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
