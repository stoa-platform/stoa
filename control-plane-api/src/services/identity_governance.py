"""Identity Governance service — SCIM→Roles mapping + DCR automation (CAB-1483).

Orchestrates:
1. SCIM group→product_roles resolution from roles-matrix config
2. Keycloak client creation with protocol mappers for JWT claims
3. Vault secret path generation (secret storage delegated to Vault)
4. Signed audit events for NIS2/DORA compliance
"""

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.oauth_client import OAuthClient, OAuthClientStatus
from ..repositories.oauth_client import OAuthClientRepository
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)

# Default SCIM group→product_roles mapping (can be overridden per-tenant)
DEFAULT_ROLES_MATRIX: dict[str, list[str]] = {
    "api-readers": ["api:read"],
    "api-writers": ["api:read", "api:write"],
    "api-admins": ["api:read", "api:write", "api:admin"],
    "billing-users": ["billing:read"],
    "billing-admins": ["billing:read", "billing:write", "billing:admin"],
}

# Allowed grant types for DCR validation
ALLOWED_GRANT_TYPES = {"client_credentials", "authorization_code", "refresh_token"}


def resolve_product_roles(scim_groups: list[str], roles_matrix: dict[str, list[str]] | None = None) -> list[str]:
    """Resolve SCIM groups to a deduplicated list of product roles.

    Args:
        scim_groups: SCIM group names from the IdP
        roles_matrix: Optional custom mapping (defaults to DEFAULT_ROLES_MATRIX)

    Returns:
        Sorted, deduplicated list of product role strings
    """
    matrix = roles_matrix or DEFAULT_ROLES_MATRIX
    roles: set[str] = set()
    for group in scim_groups:
        if group in matrix:
            roles.update(matrix[group])
    return sorted(roles)


def validate_oauth_metadata(metadata: dict | None) -> list[str]:
    """Validate OAuth metadata fields. Returns list of validation errors."""
    if not metadata:
        return []

    errors: list[str] = []
    grant_types = metadata.get("grant_types", [])
    if grant_types:
        invalid = set(grant_types) - ALLOWED_GRANT_TYPES
        if invalid:
            errors.append(f"Invalid grant_types: {', '.join(sorted(invalid))}")

    redirect_uris = metadata.get("redirect_uris", [])
    for uri in redirect_uris:
        if not isinstance(uri, str) or not uri.startswith("https://"):
            errors.append(f"redirect_uri must be HTTPS: {uri}")

    return errors


def build_protocol_mappers(tenant_id: str, product_roles: list[str]) -> list[dict]:
    """Build Keycloak protocol mapper configs for JWT claim injection.

    Creates oidc-hardcoded-claim-mapper entries for:
    - tenant_id: string claim
    - product_roles: JSON array claim
    """
    mappers = [
        {
            "name": "tenant_id",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-hardcoded-claim-mapper",
            "config": {
                "claim.name": "tenant_id",
                "claim.value": tenant_id,
                "jsonType.label": "String",
                "id.token.claim": "false",
                "access.token.claim": "true",
                "userinfo.token.claim": "false",
            },
        },
    ]

    if product_roles:
        import json

        mappers.append(
            {
                "name": "product_roles",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "product_roles",
                    "claim.value": json.dumps(product_roles),
                    "jsonType.label": "JSON",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            }
        )

    return mappers


class IdentityGovernanceService:
    """Orchestrates DCR client registration with SCIM-derived roles."""

    def __init__(self, db: AsyncSession, keycloak_service=None):
        self.db = db
        self.repo = OAuthClientRepository(db)
        self.audit = AuditService(db)
        self.keycloak = keycloak_service

    async def register_client(
        self,
        *,
        tenant_id: str,
        client_name: str,
        description: str | None = None,
        product_roles: list[str] | None = None,
        oauth_metadata: dict | None = None,
        actor_id: str | None = None,
        actor_email: str | None = None,
    ) -> OAuthClient:
        """Register a new OAuth client via DCR with SCIM-derived roles.

        1. Validates metadata
        2. Creates Keycloak client with protocol mappers
        3. Stores record in DB
        4. Records audit event
        """
        # Validate metadata
        errors = validate_oauth_metadata(oauth_metadata)
        if errors:
            raise ValueError(f"Invalid oauth_metadata: {'; '.join(errors)}")

        roles = product_roles or []
        client_id_str = str(uuid4())
        kc_client_id = f"{tenant_id}-{client_name}"

        # Check for duplicate
        existing = await self.repo.get_by_keycloak_client_id(kc_client_id)
        if existing:
            raise ValueError(f"Client already registered: {kc_client_id}")

        # Create Keycloak client with protocol mappers
        kc_uuid = None
        vault_path = None
        if self.keycloak:
            try:
                mappers = build_protocol_mappers(tenant_id, roles)
                client_data = {
                    "clientId": kc_client_id,
                    "name": f"DCR: {client_name}",
                    "description": description or f"DCR client for {client_name}",
                    "enabled": True,
                    "protocol": "openid-connect",
                    "publicClient": False,
                    "serviceAccountsEnabled": True,
                    "authorizationServicesEnabled": False,
                    "standardFlowEnabled": False,
                    "directAccessGrantsEnabled": False,
                    "protocolMappers": mappers,
                    "attributes": {
                        "tenant_id": tenant_id,
                        "product_roles": ",".join(roles),
                    },
                }
                self.keycloak._admin.create_client(client_data)
                kc_info = await self.keycloak.get_client(kc_client_id)
                if kc_info:
                    kc_uuid = kc_info.get("id")
                vault_path = f"secret/data/tenants/{tenant_id}/clients/{kc_client_id}"
            except Exception as e:
                logger.error(f"Keycloak client creation failed for {kc_client_id}: {e}")
                raise RuntimeError(f"Failed to create Keycloak client: {e}") from e

        # Store in DB
        client = OAuthClient(
            id=client_id_str,
            tenant_id=tenant_id,
            keycloak_client_id=kc_client_id,
            keycloak_uuid=kc_uuid,
            client_name=client_name,
            description=description,
            product_roles=roles,
            oauth_metadata=oauth_metadata,
            vault_secret_path=vault_path,
            status=OAuthClientStatus.ACTIVE.value,
        )
        client = await self.repo.create(client)

        # Audit
        await self.audit.record_event(
            tenant_id=tenant_id,
            action="create",
            method="POST",
            path="/v1/oauth-clients/",
            resource_type="oauth_client",
            resource_id=client.id,
            resource_name=kc_client_id,
            actor_id=actor_id,
            actor_email=actor_email,
            outcome="success",
            details={"product_roles": roles, "kc_client_id": kc_client_id},
        )

        logger.info(f"Registered OAuth client {kc_client_id} for tenant {tenant_id} with roles {roles}")
        return client

    async def revoke_client(
        self,
        *,
        client_id: str,
        tenant_id: str,
        actor_id: str | None = None,
        actor_email: str | None = None,
    ) -> bool:
        """Revoke an OAuth client — soft-delete in DB + disable in Keycloak."""
        client = await self.repo.get_by_id(client_id)
        if not client or client.tenant_id != tenant_id:
            return False

        # Disable in Keycloak
        if self.keycloak and client.keycloak_uuid:
            try:
                self.keycloak._admin.update_client(client.keycloak_uuid, {"enabled": False})
            except Exception as e:
                logger.warning(f"Failed to disable Keycloak client {client.keycloak_client_id}: {e}")

        # Soft-delete in DB
        await self.repo.update_status(client_id, OAuthClientStatus.REVOKED)

        # Audit
        await self.audit.record_event(
            tenant_id=tenant_id,
            action="delete",
            method="DELETE",
            path=f"/v1/oauth-clients/{client_id}",
            resource_type="oauth_client",
            resource_id=client_id,
            resource_name=client.keycloak_client_id,
            actor_id=actor_id,
            actor_email=actor_email,
            outcome="success",
        )

        logger.info(f"Revoked OAuth client {client.keycloak_client_id}")
        return True
