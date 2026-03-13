"""Connector OAuth Service — handles the OAuth authorization flow for MCP connectors.

Flow:
1. initiate_authorize: build OAuth URL, save CSRF state in DB
2. handle_callback: exchange code for tokens, create ExternalMCPServer, store tokens in Vault
3. disconnect: remove server + Vault credentials
"""

import base64
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from hvac.exceptions import InvalidPath

from src.models.external_mcp_server import (
    ExternalMCPAuthType,
    ExternalMCPServer,
    ExternalMCPTransport,
)
from src.models.mcp_connector_template import MCPConnectorTemplate, OAuthPendingSession
from src.repositories.external_mcp_server import ExternalMCPServerRepository
from src.repositories.mcp_connector import (
    ConnectorServerRepository,
    ConnectorTemplateRepository,
    OAuthSessionRepository,
)
from src.services.vault_client import get_vault_client

logger = logging.getLogger(__name__)

# OAuth state token expires after 10 minutes
STATE_EXPIRY_MINUTES = 10


class ConnectorOAuthError(Exception):
    """Raised when the OAuth flow encounters an error."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ConnectorOAuthService:
    """Handles the full OAuth lifecycle for MCP connector integrations."""

    def __init__(
        self,
        template_repo: ConnectorTemplateRepository,
        session_repo: OAuthSessionRepository,
        connector_server_repo: ConnectorServerRepository,
        server_repo: ExternalMCPServerRepository,
    ):
        self.template_repo = template_repo
        self.session_repo = session_repo
        self.connector_server_repo = connector_server_repo
        self.server_repo = server_repo

    async def initiate_authorize(
        self,
        template: MCPConnectorTemplate,
        user_id: str,
        tenant_id: str | None,
        redirect_after: str | None = None,
        redirect_uri: str = "",
        client_secret: str | None = None,
    ) -> tuple[str, str]:
        """Build the OAuth authorize URL and save CSRF state.

        Args:
            template: The connector template to authorize
            user_id: Current user ID
            tenant_id: Tenant to connect for (None = platform-wide)
            redirect_after: UI URL to redirect after callback
            redirect_uri: The callback URL registered with the provider
            client_secret: Provider client_secret from setup dialog (non-DCR providers)

        Returns:
            Tuple of (authorize_url, state_token)

        Raises:
            ConnectorOAuthError: If already connected (409) or provider credentials missing
        """
        # Check not already connected
        existing = await self.connector_server_repo.get_by_template_and_tenant(template.id, tenant_id)
        if existing:
            raise ConnectorOAuthError(
                f"Connector '{template.slug}' is already connected for this tenant",
                status_code=409,
            )

        # Resolve provider client_id: DCR → template column → env var → Vault
        client_id = self._resolve_client_id(template)
        if not client_id and template.oauth_registration_url:
            # Dynamic Client Registration (RFC 7591) — one-click connect
            client_id = await self._dynamic_client_registration(
                registration_url=template.oauth_registration_url,
                redirect_uri=redirect_uri,
                client_name=f"STOA Platform ({template.slug})",
            )
            # Cache the DCR client_id in the template for future authorizations
            template.oauth_client_id = client_id
            self.template_repo.session.add(template)
            logger.info("DCR: registered client for '%s', client_id cached", template.slug)

        if not client_id:
            raise ConnectorOAuthError(
                f"Provider credentials not configured for '{template.slug}'. "
                "This connector requires manual OAuth app setup.",
                status_code=503,
            )

        # Generate CSRF state
        state = secrets.token_urlsafe(32)

        # Generate PKCE if required
        code_verifier = None
        code_challenge = None
        if template.oauth_pkce_required:
            code_verifier = secrets.token_urlsafe(96)[:128]
            code_challenge = self._generate_code_challenge(code_verifier)

        # Save pending session
        pending = OAuthPendingSession(
            id=uuid.uuid4(),
            state=state,
            connector_template_id=template.id,
            user_id=user_id,
            tenant_id=tenant_id,
            code_verifier=code_verifier,
            client_secret=client_secret,
            redirect_after=redirect_after,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=STATE_EXPIRY_MINUTES),
        )
        await self.session_repo.create(pending)

        # Build authorize URL
        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        if template.oauth_scopes:
            params["scope"] = template.oauth_scopes
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        authorize_url = f"{template.oauth_authorize_url}?{urlencode(params)}"

        # Cleanup expired sessions (piggyback, non-blocking)
        await self.session_repo.cleanup_expired()

        return authorize_url, state

    async def handle_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str = "",
    ) -> tuple[ExternalMCPServer, str | None]:
        """Exchange authorization code for tokens and create the MCP server.

        Args:
            code: Authorization code from the provider
            state: CSRF state token for validation
            redirect_uri: The callback URL used during authorize

        Returns:
            Tuple of (created_server, redirect_after_url)

        Raises:
            ConnectorOAuthError: On invalid/expired state, or token exchange failure
        """
        # Validate state
        pending = await self.session_repo.get_by_state(state)
        if not pending:
            raise ConnectorOAuthError("Invalid or expired state token")

        # Check expiry
        if datetime.utcnow() > pending.expires_at:
            await self.session_repo.delete(pending)
            raise ConnectorOAuthError("OAuth state has expired, please try again")

        # Get template
        template = await self.template_repo.get_by_id(pending.connector_template_id)
        if not template:
            await self.session_repo.delete(pending)
            raise ConnectorOAuthError("Connector template not found", status_code=404)

        redirect_after = pending.redirect_after
        code_verifier = pending.code_verifier
        pending_client_secret = pending.client_secret
        user_id = pending.user_id
        tenant_id = pending.tenant_id

        # Delete session immediately (single-use)
        await self.session_repo.delete(pending)

        # Resolve provider credentials: template/env → Vault → pending session fallback
        client_id = self._resolve_client_id(template)
        client_secret = self._resolve_client_secret(template)
        if not client_secret and pending_client_secret:
            client_secret = pending_client_secret

        # Exchange code for tokens
        tokens = await self._exchange_code_for_tokens(
            token_url=template.oauth_token_url,
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            slug=template.slug,
        )

        # Create ExternalMCPServer
        tenant_suffix = f"-{tenant_id[:8]}" if tenant_id else ""
        server_name = f"{template.slug}{tenant_suffix}"

        server = ExternalMCPServer(
            id=uuid.uuid4(),
            name=server_name,
            display_name=template.display_name,
            description=template.description,
            icon=template.icon_url,
            base_url=template.mcp_base_url,
            transport=ExternalMCPTransport(template.transport),
            auth_type=ExternalMCPAuthType.OAUTH2,
            tool_prefix=template.slug,
            tenant_id=tenant_id,
            created_by=user_id,
            connector_template_id=template.id,
        )

        # Store user tokens in Vault (separate from provider app credentials)
        vault_data = {
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": tokens.get("expires_at"),
            "token_url": template.oauth_token_url,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        try:
            vault = get_vault_client()
            vault_path = await vault.store_credential(str(server.id), vault_data)
            if vault_path:
                server.credential_vault_path = vault_path
            else:
                logger.warning("Vault unavailable — OAuth tokens not stored for connector '%s'", template.slug)
        except Exception as e:
            logger.warning("Vault error — OAuth tokens not stored for connector '%s': %s", template.slug, e)

        server = await self.server_repo.create(server)

        logger.info(
            f"Connected connector '{template.slug}' as server '{server.name}'",
            extra={"server_id": str(server.id), "user_id": user_id},
        )

        return server, redirect_after

    async def disconnect(
        self,
        template: MCPConnectorTemplate,
        tenant_id: str | None,
    ) -> uuid.UUID | None:
        """Disconnect a connector: delete server + Vault credentials.

        Returns:
            The deleted server's ID, or None if not found.
        """
        server = await self.connector_server_repo.get_by_template_and_tenant(template.id, tenant_id)
        if not server:
            return None

        server_id = server.id

        # Delete from Vault
        if server.credential_vault_path:
            try:
                vault = get_vault_client()
                await vault.delete_credential(str(server.id))
            except Exception as e:
                logger.warning(f"Failed to delete Vault credentials for connector '{template.slug}': {e}")

        # Delete server (cascades to tools)
        await self.server_repo.delete(server)

        logger.info(
            f"Disconnected connector '{template.slug}'",
            extra={"server_id": str(server_id)},
        )

        return server_id

    # ── Credential resolution (template → env → Vault fallback) ──

    @staticmethod
    def _resolve_client_id(template: MCPConnectorTemplate) -> str:
        """Resolve OAuth client_id for a connector.

        Priority:
        1. Template column (oauth_client_id) — set via migration seed or admin API
        2. Env var MCP_OAUTH_{SLUG}_CLIENT_ID — injected via Infisical → K8s Secret
        3. Vault at secret/data/mcp-connector-templates/{slug} (legacy fallback)
        """
        # 1. Template column (preferred — no external dependency)
        if template.oauth_client_id:
            return template.oauth_client_id

        # 2. Env var
        env_key = f"MCP_OAUTH_{template.slug.upper()}_CLIENT_ID"
        env_val = os.environ.get(env_key, "")
        if env_val:
            return env_val

        # 3. Vault fallback (legacy path)
        vault_creds = ConnectorOAuthService._get_vault_provider_credentials(template.slug)
        return vault_creds.get("client_id", "")

    @staticmethod
    def _resolve_client_secret(template: MCPConnectorTemplate) -> str:
        """Resolve OAuth client_secret for a connector.

        For PKCE-only providers (e.g. Linear), client_secret is not needed and
        this returns empty string — the token exchange works with code_verifier alone.

        Priority:
        1. Env var MCP_OAUTH_{SLUG}_CLIENT_SECRET — injected via Infisical → K8s Secret
        2. Vault at secret/data/mcp-connector-templates/{slug} (legacy fallback)
        """
        # 1. Env var (preferred — no Vault dependency for app-level secrets)
        env_key = f"MCP_OAUTH_{template.slug.upper()}_CLIENT_SECRET"
        env_val = os.environ.get(env_key, "")
        if env_val:
            return env_val

        # 2. Vault fallback
        vault_creds = ConnectorOAuthService._get_vault_provider_credentials(template.slug)
        return vault_creds.get("client_secret", "")

    @staticmethod
    def _get_vault_provider_credentials(slug: str) -> dict[str, Any]:
        """Legacy fallback: retrieve provider app credentials from Vault.

        Provider credentials are stored at: secret/data/mcp-connector-templates/{slug}
        """
        try:
            vault = get_vault_client()
            if not vault.enabled:
                return {}
            vault._ensure_unsealed()
            client = vault._get_client()
            path = f"mcp-connector-templates/{slug}"
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=vault.mount_point,
            )
            if response and "data" in response and "data" in response["data"]:
                return response["data"]["data"]
            return {}
        except InvalidPath:
            logger.debug("Provider credentials not found in Vault for '%s'", slug)
            return {}
        except Exception as e:
            logger.warning("Failed to retrieve provider credentials for '%s': %s", slug, e)
            return {}

    async def _dynamic_client_registration(
        self,
        registration_url: str,
        redirect_uri: str,
        client_name: str = "STOA Platform",
    ) -> str:
        """Register a client dynamically via RFC 7591 (MCP OAuth DCR).

        Used by providers like Linear and Sentry that expose a registration
        endpoint in their MCP OAuth metadata.

        Returns:
            The dynamically assigned client_id.
        """
        payload = {
            "client_name": client_name,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                registration_url,
                json=payload,
                headers={"Accept": "application/json"},
            )

        if response.status_code not in (200, 201):
            logger.error(
                "DCR failed at %s: %s %s",
                registration_url,
                response.status_code,
                response.text[:300],
            )
            raise ConnectorOAuthError(
                f"Dynamic client registration failed (HTTP {response.status_code})",
                status_code=502,
            )

        data = response.json()
        client_id = data.get("client_id")
        if not client_id:
            raise ConnectorOAuthError("DCR response missing client_id", status_code=502)

        logger.info(
            "DCR success at %s: client_id=%s",
            registration_url,
            client_id[:12] + "...",
        )
        return client_id

    async def _exchange_code_for_tokens(
        self,
        token_url: str,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        slug: str = "",
    ) -> dict[str, Any]:
        """Exchange an authorization code for access/refresh tokens.

        Most providers accept standard form POST with client_id/client_secret in the body.
        Notion requires HTTP Basic auth + JSON body (their API rejects form-encoded).
        """
        headers: dict[str, str] = {"Accept": "application/json"}

        # Notion uses Basic auth + JSON body (not standard form POST)
        if slug == "notion":
            import base64 as b64

            credentials = b64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            headers["Content-Type"] = "application/json"
            json_body: dict[str, str] = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(token_url, json=json_body, headers=headers)
        else:
            data: dict[str, str] = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
            }
            if client_secret:
                data["client_secret"] = client_secret
            if code_verifier:
                data["code_verifier"] = code_verifier
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(token_url, data=data, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Token exchange failed: {response.status_code} {response.text[:200]}",
                extra={"token_url": token_url},
            )
            raise ConnectorOAuthError(
                f"Failed to exchange authorization code (HTTP {response.status_code})",
                status_code=502,
            )

        tokens = response.json()

        # Compute expires_at if expires_in is present
        if "expires_in" in tokens and "expires_at" not in tokens:
            tokens["expires_at"] = (datetime.utcnow() + timedelta(seconds=int(tokens["expires_in"]))).isoformat()

        return tokens

    @staticmethod
    def _generate_code_challenge(code_verifier: str) -> str:
        """Generate a S256 PKCE code challenge from a code verifier."""
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
