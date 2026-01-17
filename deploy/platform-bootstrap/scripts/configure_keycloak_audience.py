#!/usr/bin/env python3
"""
Configure Keycloak Audience Mappers

This script configures Audience Mappers in Keycloak so that all client
applications emit tokens with `aud: control-plane-api` (the Resource Server)
instead of `aud: <client-id>`.

This follows OAuth2/OIDC best practices where:
- `aud` (audience) = the API/Resource Server that will consume the token
- `azp` (authorized party) = the client application that requested the token

Usage:
    python configure_keycloak_audience.py

Environment Variables:
    KEYCLOAK_URL        - Keycloak base URL (default: https://auth.stoa.cab-i.com)
    KEYCLOAK_REALM      - Realm name (default: stoa)
    KEYCLOAK_ADMIN_USER - Admin username (default: admin)
    KEYCLOAK_ADMIN_PASS - Admin password (required)
    RESOURCE_SERVER_ID  - Target audience client ID (default: control-plane-api)
    DRY_RUN             - Set to "true" to preview changes without applying
"""

import os
import sys
import json
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from requests.exceptions import RequestException

# =============================================================================
# Configuration
# =============================================================================


@dataclass
class Config:
    """Configuration settings."""

    keycloak_url: str
    realm: str
    admin_user: str
    admin_pass: str
    resource_server_id: str
    dry_run: bool
    clients_to_configure: list[str]

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        admin_pass = os.getenv("KEYCLOAK_ADMIN_PASS", "")
        if not admin_pass:
            raise ValueError("KEYCLOAK_ADMIN_PASS environment variable is required")

        clients = os.getenv(
            "CLIENTS_TO_CONFIGURE", "control-plane-ui stoa-portal mcp-gateway-client"
        )

        return cls(
            keycloak_url=os.getenv("KEYCLOAK_URL", "https://auth.stoa.cab-i.com"),
            realm=os.getenv("KEYCLOAK_REALM", "stoa"),
            admin_user=os.getenv("KEYCLOAK_ADMIN_USER", "admin"),
            admin_pass=admin_pass,
            resource_server_id=os.getenv("RESOURCE_SERVER_ID", "control-plane-api"),
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            clients_to_configure=clients.split(),
        )


# =============================================================================
# Logging Setup
# =============================================================================


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors."""

    COLORS = {
        "DEBUG": "\033[0;36m",  # Cyan
        "INFO": "\033[0;34m",  # Blue
        "WARNING": "\033[1;33m",  # Yellow
        "ERROR": "\033[0;31m",  # Red
        "SUCCESS": "\033[0;32m",  # Green
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}[{record.levelname}]{self.RESET}"
        return super().format(record)


# Add SUCCESS level
logging.SUCCESS = 25
logging.addLevelName(logging.SUCCESS, "SUCCESS")


def success(self, message, *args, **kwargs):
    if self.isEnabledFor(logging.SUCCESS):
        self._log(logging.SUCCESS, message, args, **kwargs)


logging.Logger.success = success

# Configure logger
logger = logging.getLogger("keycloak-audience")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter("%(levelname)s %(message)s"))
logger.addHandler(handler)


# =============================================================================
# Keycloak Client
# =============================================================================


class KeycloakAdmin:
    """Keycloak Admin API client."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"{config.keycloak_url}/admin/realms/{config.realm}"
        self.token: Optional[str] = None
        self.session = requests.Session()

    def authenticate(self) -> bool:
        """Authenticate and obtain admin token."""
        token_url = f"{self.config.keycloak_url}/realms/master/protocol/openid-connect/token"

        try:
            response = self.session.post(
                token_url,
                data={
                    "username": self.config.admin_user,
                    "password": self.config.admin_pass,
                    "grant_type": "password",
                    "client_id": "admin-cli",
                },
            )
            response.raise_for_status()
            self.token = response.json().get("access_token")

            if not self.token:
                logger.error("No access token in response")
                return False

            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            logger.success(f"Authenticated as {self.config.admin_user}")
            return True

        except RequestException as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def get_client_by_id(self, client_id: str) -> Optional[dict]:
        """Get client by client_id."""
        try:
            response = self.session.get(
                f"{self.base_url}/clients", params={"clientId": client_id}
            )
            response.raise_for_status()
            clients = response.json()
            return clients[0] if clients else None
        except RequestException as e:
            logger.error(f"Failed to get client {client_id}: {e}")
            return None

    def get_dedicated_scope(self, client_id: str, client_uuid: str) -> Optional[dict]:
        """Get the dedicated client scope for a client."""
        try:
            response = self.session.get(
                f"{self.base_url}/clients/{client_uuid}/default-client-scopes"
            )
            response.raise_for_status()
            scopes = response.json()

            dedicated_name = f"{client_id}-dedicated"
            for scope in scopes:
                if scope.get("name") == dedicated_name:
                    return scope
            return None
        except RequestException as e:
            logger.error(f"Failed to get dedicated scope for {client_id}: {e}")
            return None

    def get_scope_mappers(self, scope_id: str) -> list[dict]:
        """Get protocol mappers for a client scope."""
        try:
            response = self.session.get(
                f"{self.base_url}/client-scopes/{scope_id}/protocol-mappers/models"
            )
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Failed to get scope mappers: {e}")
            return []

    def get_client_mappers(self, client_uuid: str) -> list[dict]:
        """Get protocol mappers for a client."""
        try:
            response = self.session.get(
                f"{self.base_url}/clients/{client_uuid}/protocol-mappers/models"
            )
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Failed to get client mappers: {e}")
            return []

    def create_scope_mapper(self, scope_id: str, mapper: dict) -> bool:
        """Create a protocol mapper in a client scope."""
        try:
            response = self.session.post(
                f"{self.base_url}/client-scopes/{scope_id}/protocol-mappers/models",
                json=mapper,
            )
            response.raise_for_status()
            return True
        except RequestException as e:
            logger.error(f"Failed to create scope mapper: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False

    def create_client_mapper(self, client_uuid: str, mapper: dict) -> bool:
        """Create a protocol mapper directly on a client."""
        try:
            response = self.session.post(
                f"{self.base_url}/clients/{client_uuid}/protocol-mappers/models",
                json=mapper,
            )
            response.raise_for_status()
            return True
        except RequestException as e:
            logger.error(f"Failed to create client mapper: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False


# =============================================================================
# Main Logic
# =============================================================================


def configure_audience_mappers(config: Config) -> tuple[int, int, int]:
    """
    Configure audience mappers for all specified clients.

    Returns:
        Tuple of (configured_count, skipped_count, failed_count)
    """
    keycloak = KeycloakAdmin(config)

    if not keycloak.authenticate():
        logger.error("Failed to authenticate with Keycloak")
        sys.exit(1)

    # Mapper configuration
    mapper_name = "api-audience-mapper"
    mapper_config = {
        "name": mapper_name,
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": {
            "included.client.audience": config.resource_server_id,
            "id.token.claim": "false",
            "access.token.claim": "true",
        },
    }

    logger.info(f"Target Resource Server: {config.resource_server_id}")
    logger.info(f"Mapper configuration:\n{json.dumps(mapper_config, indent=2)}")

    configured = 0
    skipped = 0
    failed = 0

    for client_id in config.clients_to_configure:
        logger.info(f"\n==> Processing client: {client_id}")

        # Get client
        client = keycloak.get_client_by_id(client_id)
        if not client:
            logger.warning(f"Client '{client_id}' not found - skipping")
            skipped += 1
            continue

        client_uuid = client["id"]
        logger.info(f"Found client UUID: {client_uuid}")

        # Try dedicated scope first
        scope = keycloak.get_dedicated_scope(client_id, client_uuid)

        if scope:
            scope_id = scope["id"]
            logger.info(f"Found dedicated scope: {client_id}-dedicated ({scope_id})")

            # Check if mapper already exists
            mappers = keycloak.get_scope_mappers(scope_id)
            if any(m.get("name") == mapper_name for m in mappers):
                logger.success(f"Mapper '{mapper_name}' already exists in scope - skipping")
                skipped += 1
                continue

            if config.dry_run:
                logger.warning(f"[DRY RUN] Would create mapper in scope {client_id}-dedicated")
                continue

            # Create mapper in scope
            logger.info("Creating mapper in dedicated scope...")
            if keycloak.create_scope_mapper(scope_id, mapper_config):
                logger.success("Mapper created successfully in scope")
                configured += 1
            else:
                failed += 1

        else:
            logger.warning(f"No dedicated scope found for '{client_id}' - using client-level mapper")

            # Check if mapper already exists on client
            mappers = keycloak.get_client_mappers(client_uuid)
            if any(m.get("name") == mapper_name for m in mappers):
                logger.success(f"Mapper '{mapper_name}' already exists on client - skipping")
                skipped += 1
                continue

            if config.dry_run:
                logger.warning(f"[DRY RUN] Would create mapper directly on client {client_id}")
                continue

            # Create mapper on client
            logger.info("Creating mapper directly on client...")
            if keycloak.create_client_mapper(client_uuid, mapper_config):
                logger.success("Mapper created successfully on client")
                configured += 1
            else:
                failed += 1

    return configured, skipped, failed


def print_verification_instructions(config: Config):
    """Print verification instructions."""
    print(f"""
\033[0;34m==> Verification\033[0m

To verify the configuration, obtain a token and decode it:

\033[0;34m# Get a token (example with password grant for testing)\033[0m
TOKEN=$(curl -s -X POST '{config.keycloak_url}/realms/{config.realm}/protocol/openid-connect/token' \\
    -d 'grant_type=password' \\
    -d 'client_id=control-plane-ui' \\
    -d 'username=<user>' \\
    -d 'password=<pass>' \\
    -d 'scope=openid' | jq -r '.access_token')

\033[0;34m# Decode and check audience\033[0m
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq '{{aud, azp, iss}}'

\033[0;34m# Expected output:\033[0m
{{
  "aud": "{config.resource_server_id}",    \033[0;32m<-- Should be the API\033[0m
  "azp": "control-plane-ui",               \033[0;32m<-- Should be the client\033[0m
  "iss": "{config.keycloak_url}/realms/{config.realm}"
}}
""")


def main():
    """Main entry point."""
    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"Keycloak URL: {config.keycloak_url}")
    logger.info(f"Realm: {config.realm}")
    logger.info(f"Clients to configure: {', '.join(config.clients_to_configure)}")

    if config.dry_run:
        logger.warning("DRY RUN mode - no changes will be made")

    configured, skipped, failed = configure_audience_mappers(config)

    # Summary
    print(f"""
\033[0;34m==> Summary\033[0m
\033[0;32mConfigured:\033[0m {configured}
\033[1;33mSkipped:\033[0m {skipped}
\033[0;31mFailed:\033[0m {failed}
""")

    if config.dry_run:
        logger.warning("This was a dry run - no changes were made")
        logger.info("Set DRY_RUN=false to apply changes")

    print_verification_instructions(config)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
