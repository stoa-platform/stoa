"""Keycloak service for authentication and client management"""

import logging

import httpx
from keycloak import KeycloakAdmin, KeycloakOpenIDConnection

from ..config import settings

logger = logging.getLogger(__name__)


class KeycloakService:
    """Service for Keycloak operations"""

    def __init__(self):
        self._admin: KeycloakAdmin | None = None

    async def connect(self):
        """Initialize Keycloak admin connection"""
        try:
            conn = KeycloakOpenIDConnection(
                server_url=settings.KEYCLOAK_URL,
                realm_name=settings.KEYCLOAK_REALM,
                client_id=settings.KEYCLOAK_ADMIN_CLIENT_ID,
                client_secret_key=settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
                verify=True,
            )
            self._admin = KeycloakAdmin(connection=conn)
            logger.info(f"Connected to Keycloak realm: {settings.KEYCLOAK_REALM}")
        except Exception as e:
            logger.error(f"Failed to connect to Keycloak: {e}")
            raise

    async def disconnect(self):
        """Close Keycloak connection"""
        self._admin = None

    # User operations
    async def get_users(self, tenant_id: str | None = None) -> list[dict]:
        """Get users, optionally filtered by tenant"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        users = self._admin.get_users({})

        if tenant_id:
            # Filter by tenant_id attribute
            users = [u for u in users if u.get("attributes", {}).get("tenant_id", [None])[0] == tenant_id]

        return users

    async def get_user(self, user_id: str) -> dict | None:
        """Get user by ID"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        try:
            return self._admin.get_user(user_id)
        except Exception:
            return None

    async def create_user(
        self,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        tenant_id: str,
        roles: list[str],
        temporary_password: str | None = None,
    ) -> str:
        """Create a new user in Keycloak"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        user_data = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": True,
            "attributes": {
                "tenant_id": [tenant_id],
            },
        }

        if temporary_password:
            user_data["credentials"] = [
                {
                    "type": "password",
                    "value": temporary_password,
                    "temporary": True,
                }
            ]

        user_id = self._admin.create_user(user_data)

        # Assign roles
        for role_name in roles:
            await self.assign_role(user_id, role_name)

        logger.info(f"Created user {username} with roles {roles}")
        return user_id

    async def update_user(self, user_id: str, updates: dict) -> bool:
        """Update user attributes"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        self._admin.update_user(user_id, updates)
        return True

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        self._admin.delete_user(user_id)
        logger.info(f"Deleted user {user_id}")
        return True

    # Role operations
    async def get_roles(self) -> list[dict]:
        """Get all realm roles"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        return self._admin.get_realm_roles()

    async def assign_role(self, user_id: str, role_name: str) -> bool:
        """Assign a role to a user"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        role = self._admin.get_realm_role(role_name)
        self._admin.assign_realm_roles(user_id, [role])
        return True

    async def remove_role(self, user_id: str, role_name: str) -> bool:
        """Remove a role from a user"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        role = self._admin.get_realm_role(role_name)
        self._admin.delete_realm_roles_of_user(user_id, [role])
        return True

    # Client (Application) operations
    async def get_clients(self, tenant_id: str | None = None) -> list[dict]:
        """Get all clients, optionally filtered by tenant"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        clients = self._admin.get_clients()

        if tenant_id:
            # Filter by client attribute or naming convention
            clients = [
                c
                for c in clients
                if c.get("attributes", {}).get("tenant_id", [None])[0] == tenant_id
                or c.get("clientId", "").startswith(f"{tenant_id}-")
            ]

        return clients

    async def get_client(self, client_id: str) -> dict | None:
        """Get client by client_id"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        clients = self._admin.get_clients()
        for client in clients:
            if client["clientId"] == client_id:
                return client
        return None

    async def get_client_by_id(self, client_uuid: str) -> dict | None:
        """Get client by Keycloak internal UUID."""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")
        try:
            return self._admin.get_client(client_uuid)
        except Exception:
            return None

    async def create_client(
        self, tenant_id: str, name: str, display_name: str, redirect_uris: list[str], description: str = ""
    ) -> dict:
        """
        Create a new OAuth2 client for an application.

        Returns client_id and client_secret.
        """
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        client_id = f"{tenant_id}-{name}"

        client_data = {
            "clientId": client_id,
            "name": display_name,
            "description": description,
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "authorizationServicesEnabled": False,
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
            "redirectUris": redirect_uris,
            "webOrigins": ["+"],
            "attributes": {
                "tenant_id": tenant_id,
            },
        }

        # Create client
        self._admin.create_client(client_data)

        # Get the created client to retrieve the ID
        client = await self.get_client(client_id)
        if not client:
            raise RuntimeError("Failed to create client")

        # Get client secret
        client_uuid = client["id"]
        secret_data = self._admin.get_client_secrets(client_uuid)

        logger.info(f"Created client {client_id} for tenant {tenant_id}")

        return {
            "client_id": client_id,
            "client_secret": secret_data.get("value"),
            "id": client_uuid,
        }

    async def update_client(self, client_uuid: str, updates: dict) -> bool:
        """Update client configuration"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        self._admin.update_client(client_uuid, updates)
        return True

    async def delete_client(self, client_uuid: str) -> bool:
        """Delete a client"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        self._admin.delete_client(client_uuid)
        logger.info(f"Deleted client {client_uuid}")
        return True

    async def regenerate_client_secret(self, client_uuid: str) -> str:
        """Regenerate client secret"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        secret_data = self._admin.generate_client_secrets(client_uuid)
        return secret_data.get("value")

    # Consumer client operations (CAB-1121 Phase 2)
    async def create_consumer_client(
        self,
        tenant_slug: str,
        consumer_external_id: str,
        consumer_id: str,
        plan_slug: str | None = None,
        rate_limit: int | None = None,
    ) -> dict:
        """
        Create an OAuth2 client for a consumer (client_credentials grant).

        Called when a consumer is activated. Creates a Keycloak client with
        protocol mappers that embed tenant_id, consumer_id, plan_slug, and
        rate_limit as token claims.

        Args:
            tenant_slug: Tenant identifier (used in client_id naming)
            consumer_external_id: Consumer's external ID
            consumer_id: Consumer UUID (string)
            plan_slug: Optional plan slug for token claim
            rate_limit: Optional rate limit for token claim

        Returns:
            dict with client_id, client_secret, and id (Keycloak UUID)
        """
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        client_id = f"{tenant_slug}-{consumer_external_id}"

        # Build protocol mappers for token enrichment
        protocol_mappers = [
            {
                "name": "tenant_id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "tenant_id",
                    "claim.value": tenant_slug,
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            },
            {
                "name": "consumer_id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "consumer_id",
                    "claim.value": consumer_id,
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            },
        ]

        if plan_slug:
            protocol_mappers.append(
                {
                    "name": "plan_slug",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-hardcoded-claim-mapper",
                    "config": {
                        "claim.name": "plan_slug",
                        "claim.value": plan_slug,
                        "jsonType.label": "String",
                        "id.token.claim": "false",
                        "access.token.claim": "true",
                        "userinfo.token.claim": "false",
                    },
                }
            )

        if rate_limit is not None:
            protocol_mappers.append(
                {
                    "name": "rate_limit",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-hardcoded-claim-mapper",
                    "config": {
                        "claim.name": "rate_limit",
                        "claim.value": str(rate_limit),
                        "jsonType.label": "int",
                        "id.token.claim": "false",
                        "access.token.claim": "true",
                        "userinfo.token.claim": "false",
                    },
                }
            )

        client_data = {
            "clientId": client_id,
            "name": f"Consumer: {consumer_external_id}",
            "description": f"OAuth2 client for consumer {consumer_external_id} in tenant {tenant_slug}",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "authorizationServicesEnabled": False,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "implicitFlowEnabled": False,
            "redirectUris": [],
            "webOrigins": [],
            "attributes": {
                "tenant_id": tenant_slug,
                "consumer_id": consumer_id,
                "consumer_external_id": consumer_external_id,
            },
            "protocolMappers": protocol_mappers,
        }

        self._admin.create_client(client_data)

        # Retrieve the created client to get the Keycloak UUID
        client = await self.get_client(client_id)
        if not client:
            raise RuntimeError(f"Failed to create consumer client {client_id}")

        client_uuid = client["id"]
        secret_data = self._admin.get_client_secrets(client_uuid)

        logger.info(f"Created consumer client {client_id} for tenant {tenant_slug}")

        return {
            "client_id": client_id,
            "client_secret": secret_data.get("value"),
            "id": client_uuid,
        }

    async def create_consumer_client_with_cert(
        self,
        tenant_slug: str,
        consumer_external_id: str,
        consumer_id: str,
        fingerprint_b64url: str,
    ) -> dict:
        """
        Create an OAuth2 client for a consumer with mTLS cnf binding (CAB-864).

        Adds a protocol mapper that embeds the certificate thumbprint
        as cnf.x5t#S256 in the access token (RFC 8705).
        """
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        client_id = f"{tenant_slug}-{consumer_external_id}"

        protocol_mappers = [
            {
                "name": "tenant_id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "tenant_id",
                    "claim.value": tenant_slug,
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            },
            {
                "name": "consumer_id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "consumer_id",
                    "claim.value": consumer_id,
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            },
            {
                "name": "cnf-x5t-s256",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "cnf.x5t#S256",
                    "claim.value": fingerprint_b64url,
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            },
        ]

        client_data = {
            "clientId": client_id,
            "name": f"Consumer: {consumer_external_id}",
            "description": (
                f"mTLS-bound OAuth2 client for consumer {consumer_external_id} " f"in tenant {tenant_slug}"
            ),
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "authorizationServicesEnabled": False,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "implicitFlowEnabled": False,
            "redirectUris": [],
            "webOrigins": [],
            "attributes": {
                "tenant_id": tenant_slug,
                "consumer_id": consumer_id,
                "consumer_external_id": consumer_external_id,
                "mtls_enabled": "true",
            },
            "protocolMappers": protocol_mappers,
        }

        self._admin.create_client(client_data)

        client = await self.get_client(client_id)
        if not client:
            raise RuntimeError(f"Failed to create consumer client {client_id}")

        client_uuid = client["id"]
        secret_data = self._admin.get_client_secrets(client_uuid)

        logger.info(f"Created mTLS consumer client {client_id} for tenant {tenant_slug}")

        return {
            "client_id": client_id,
            "client_secret": secret_data.get("value"),
            "id": client_uuid,
        }

    async def update_consumer_client_cnf(
        self,
        client_id: str,
        fingerprint_b64url: str,
    ) -> bool:
        """
        Update the cnf.x5t#S256 protocol mapper on a consumer client (CAB-864).

        Used during certificate rotation to update the thumbprint.
        """
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        client = await self.get_client(client_id)
        if not client:
            raise RuntimeError(f"Consumer client {client_id} not found")

        client_uuid = client["id"]

        # Find existing cnf mapper or create new one
        mappers = client.get("protocolMappers", [])
        cnf_mapper = next((m for m in mappers if m.get("name") == "cnf-x5t-s256"), None)

        if cnf_mapper:
            cnf_mapper["config"]["claim.value"] = fingerprint_b64url
            self._admin.update_client(client_uuid, {"protocolMappers": mappers})
        else:
            new_mapper = {
                "name": "cnf-x5t-s256",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "cnf.x5t#S256",
                    "claim.value": fingerprint_b64url,
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                },
            }
            mappers.append(new_mapper)
            self._admin.update_client(client_uuid, {"protocolMappers": mappers})

        logger.info(f"Updated cnf mapper for client {client_id}")
        return True

    async def disable_consumer_client(self, client_id: str) -> bool:
        """
        Disable a consumer's Keycloak client (CAB-864).

        Used during certificate revocation to prevent new token issuance.
        """
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        client = await self.get_client(client_id)
        if not client:
            logger.warning(f"Consumer client {client_id} not found for disable")
            return False

        self._admin.update_client(client["id"], {"enabled": False})
        logger.info(f"Disabled consumer client {client_id}")
        return True

    async def exchange_token(
        self,
        client_id: str,
        client_secret: str,
        subject_token: str,
        subject_token_type: str = "urn:ietf:params:oauth:token-type:access_token",  # noqa: S107 — token type URN, not a secret
        audience: str | None = None,
        scope: str | None = None,
    ) -> dict:
        """
        Perform RFC 8693 token exchange via Keycloak.

        Uses the consumer's Keycloak client as the acting party to exchange
        a subject token for a new access token with potentially narrowed scope.

        Args:
            client_id: Consumer's Keycloak client_id (acting party)
            client_secret: Consumer's Keycloak client secret
            subject_token: The token to exchange
            subject_token_type: Token type identifier (default: access_token)
            audience: Target audience for the exchanged token
            scope: Requested scope for the exchanged token

        Returns:
            dict with access_token, token_type, expires_in, scope

        Raises:
            httpx.HTTPStatusError: If Keycloak returns an error
            RuntimeError: If Keycloak is unreachable
        """
        token_url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}" f"/protocol/openid-connect/token"

        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": client_id,
            "client_secret": client_secret,
            "subject_token": subject_token,
            "subject_token_type": subject_token_type,
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }

        if audience:
            data["audience"] = audience
        if scope:
            data["scope"] = scope

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()

        result = response.json()
        logger.info(f"Token exchange succeeded for client {client_id}")
        return result

    async def delete_consumer_client(self, client_id: str) -> bool:
        """Delete a consumer's Keycloak client by client_id."""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        client = await self.get_client(client_id)
        if not client:
            logger.warning(f"Consumer client {client_id} not found in Keycloak")
            return False

        self._admin.delete_client(client["id"])
        logger.info(f"Deleted consumer client {client_id}")
        return True

    # Service Account operations (for MCP access)
    async def create_service_account(
        self,
        user_id: str,
        user_email: str,
        tenant_id: str,
        name: str,
        description: str = "",
        roles: list[str] | None = None,
    ) -> dict:
        """
        Create a Service Account (OAuth2 client) for a user's MCP access.

        The service account inherits the user's roles and tenant isolation.
        This enables RBAC-based MCP tool access.

        Args:
            user_id: Keycloak user ID
            user_email: User email for naming
            tenant_id: User's tenant ID
            name: Service account name (e.g., "claude-desktop")
            description: Optional description
            roles: Optional list of roles (defaults to user's roles)

        Returns:
            dict with client_id, client_secret, and id
        """
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        # Generate unique client ID
        safe_name = name.lower().replace(" ", "-").replace("_", "-")
        safe_email = user_email.split("@")[0].lower().replace(".", "-")
        client_id = f"sa-{tenant_id}-{safe_email}-{safe_name}"

        # Ensure client_id is unique by adding suffix if needed
        existing = await self.get_client(client_id)
        if existing:
            import uuid

            client_id = f"{client_id}-{uuid.uuid4().hex[:6]}"

        client_data = {
            "clientId": client_id,
            "name": f"Service Account: {name}",
            "description": description or f"MCP Service Account for {user_email}",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "serviceAccountsEnabled": True,  # Enable client credentials flow
            "authorizationServicesEnabled": False,
            "standardFlowEnabled": False,  # Disable authorization code flow
            "directAccessGrantsEnabled": False,  # Disable password grant
            "implicitFlowEnabled": False,
            "redirectUris": [],
            "webOrigins": [],
            "attributes": {
                "tenant_id": tenant_id,
                "owner_user_id": user_id,
                "owner_email": user_email,
                "service_account_type": "mcp",
            },
        }

        # Create client
        self._admin.create_client(client_data)

        # Get the created client
        client = await self.get_client(client_id)
        if not client:
            raise RuntimeError("Failed to create service account client")

        client_uuid = client["id"]

        # Get service account user for this client
        sa_user = self._admin.get_client_service_account_user(client_uuid)
        sa_user_id = sa_user["id"]

        # Assign roles to service account
        if roles:
            for role_name in roles:
                try:
                    await self.assign_role(sa_user_id, role_name)
                except Exception as e:
                    logger.warning(f"Failed to assign role {role_name}: {e}")
        else:
            # Copy roles from the owner user
            user = await self.get_user(user_id)
            if user:
                user_roles = self._admin.get_realm_roles_of_user(user_id)
                for role in user_roles:
                    if role["name"] not in ["default-roles-stoa", "offline_access", "uma_authorization"]:
                        try:
                            self._admin.assign_realm_roles(sa_user_id, [role])
                        except Exception as e:
                            logger.warning(f"Failed to copy role {role['name']}: {e}")

        # Set tenant_id attribute on service account user
        self._admin.update_user(
            sa_user_id,
            {
                "attributes": {
                    "tenant_id": [tenant_id],
                    "owner_user_id": [user_id],
                }
            },
        )

        # Get client secret
        secret_data = self._admin.get_client_secrets(client_uuid)

        logger.info(f"Created service account {client_id} for user {user_email}")

        return {
            "client_id": client_id,
            "client_secret": secret_data.get("value"),
            "id": client_uuid,
            "name": name,
        }

    async def list_user_service_accounts(self, user_id: str) -> list[dict]:
        """List all service accounts owned by a user"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        clients = self._admin.get_clients()
        user_accounts = []

        for client in clients:
            attrs = client.get("attributes", {})
            if attrs.get("owner_user_id") == user_id and attrs.get("service_account_type") == "mcp":
                user_accounts.append(
                    {
                        "id": client["id"],
                        "client_id": client["clientId"],
                        "name": client.get("name", "").replace("Service Account: ", ""),
                        "description": client.get("description", ""),
                        "enabled": client.get("enabled", False),
                        "created": client.get("attributes", {}).get("created_at"),
                    }
                )

        return user_accounts

    async def delete_service_account(self, client_uuid: str, user_id: str) -> bool:
        """Delete a service account (only if owned by user)"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        # Verify ownership
        client = self._admin.get_client(client_uuid)
        if not client:
            raise ValueError("Service account not found")

        owner = client.get("attributes", {}).get("owner_user_id")
        if owner != user_id:
            raise PermissionError("Not authorized to delete this service account")

        self._admin.delete_client(client_uuid)
        logger.info(f"Deleted service account {client_uuid}")
        return True

    # Tenant setup
    async def setup_tenant_group(self, tenant_id: str, tenant_name: str) -> str:
        """Create a Keycloak group for the tenant"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        group_data = {
            "name": tenant_id,
            "attributes": {
                "display_name": [tenant_name],
            },
        }

        group_id = self._admin.create_group(group_data)
        logger.info(f"Created group for tenant {tenant_id}")
        return group_id

    async def add_user_to_tenant(self, user_id: str, tenant_id: str) -> bool:
        """Add user to tenant group and set tenant_id attribute"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        # Get tenant group
        groups = self._admin.get_groups()
        tenant_group = next((g for g in groups if g["name"] == tenant_id), None)

        if tenant_group:
            self._admin.group_user_add(user_id, tenant_group["id"])

        # Update user attribute
        await self.update_user(user_id, {"attributes": {"tenant_id": [tenant_id]}})

        return True

    async def remove_user_from_group(self, user_id: str, tenant_id: str) -> bool:
        """Remove user from tenant group (idempotent)."""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        groups = self._admin.get_groups()
        tenant_group = next((g for g in groups if g["name"] == tenant_id), None)
        if tenant_group:
            try:
                self._admin.group_user_remove(user_id, tenant_group["id"])
                logger.info(f"Removed user {user_id} from group {tenant_id}")
            except Exception as e:
                logger.warning(f"Failed to remove user {user_id} from group {tenant_id}: {e}")
                return False
        return True

    async def delete_tenant_group(self, tenant_id: str) -> bool:
        """Delete tenant group from Keycloak (idempotent)."""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        groups = self._admin.get_groups()
        tenant_group = next((g for g in groups if g["name"] == tenant_id), None)
        if not tenant_group:
            logger.info(f"Group {tenant_id} not found, nothing to delete")
            return True
        try:
            self._admin.delete_group(tenant_group["id"])
            logger.info(f"Deleted group for tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"Failed to delete group {tenant_id}: {e}")
            return False
        return True

    async def get_user_roles(self, user_id: str) -> list[str]:
        """Get realm roles for a user, filtering out system roles."""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        system_roles = {"default-roles-stoa", "offline_access", "uma_authorization"}
        roles = self._admin.get_realm_roles_of_user(user_id)
        return [r["name"] for r in roles if r["name"] not in system_roles]

    async def exchange_federation_token(
        self,
        client_id: str,
        scopes: list[str],
        ttl_seconds: int,
    ) -> dict | None:
        """Exchange a federation sub-account's KC client credentials for an access token (CAB-1370).

        Best-effort: returns token dict on success, None on any failure.
        Never raises -- caller handles None gracefully.
        """
        try:
            if not self._admin:
                logger.warning("Keycloak not connected, cannot exchange federation token")
                return None

            internal_id = self._admin.get_client_id(client_id)
            if not internal_id:
                logger.warning("Federation token exchange: KC client '%s' not found", client_id)
                return None

            secret_data = self._admin.get_client_secret(internal_id)
            client_secret = secret_data.get("value", "") if secret_data else ""
            if not client_secret:
                logger.warning("Federation token exchange: no secret for client '%s'", client_id)
                return None

            token_url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}" "/protocol/openid-connect/token"
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": " ".join(scopes),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            return {
                "access_token": data["access_token"],
                "token_type": data.get("token_type", "Bearer"),
                "expires_in": data.get("expires_in", ttl_seconds),
                "scope": data.get("scope", " ".join(scopes)),
            }
        except Exception as e:
            logger.warning("Federation token exchange failed for client '%s': %s", client_id, e)
            return None

    async def setup_federation_client(
        self,
        sub_account_id: str,
        master_account_id: str,
        tenant_id: str,
    ) -> str | None:
        """Create a confidential KC client for federation Token Exchange (CAB-1313).

        Best-effort: returns client_id on success, None on any failure.
        Never raises -- caller handles None gracefully.
        """
        try:
            if not self._admin:
                logger.warning("Keycloak not connected, skipping federation client setup")
                return None

            client_id = f"stoa-fed-{sub_account_id[:8]}"

            client_data = {
                "clientId": client_id,
                "name": f"Federation: {sub_account_id[:8]}",
                "description": f"Token Exchange client for federation sub-account in tenant {tenant_id}",
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "authorizationServicesEnabled": False,
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "implicitFlowEnabled": False,
                "redirectUris": [],
                "webOrigins": [],
                "attributes": {
                    "tenant_id": tenant_id,
                    "master_account_id": master_account_id,
                    "sub_account_id": sub_account_id,
                    "federation_client": "true",
                },
            }

            self._admin.create_client(client_data)
            logger.info("Created federation client %s for tenant %s", client_id, tenant_id)
            return client_id
        except Exception as e:
            logger.warning("Failed to create federation client for sub-account %s: %s", sub_account_id, e)
            return None


# Global instance
keycloak_service = KeycloakService()
