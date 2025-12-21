"""Keycloak service for authentication and client management"""
import logging
from typing import Optional
from keycloak import KeycloakAdmin, KeycloakOpenIDConnection

from ..config import settings

logger = logging.getLogger(__name__)

class KeycloakService:
    """Service for Keycloak operations"""

    def __init__(self):
        self._admin: Optional[KeycloakAdmin] = None

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
    async def get_users(self, tenant_id: Optional[str] = None) -> list[dict]:
        """Get users, optionally filtered by tenant"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        users = self._admin.get_users({})

        if tenant_id:
            # Filter by tenant_id attribute
            users = [
                u for u in users
                if u.get("attributes", {}).get("tenant_id", [None])[0] == tenant_id
            ]

        return users

    async def get_user(self, user_id: str) -> Optional[dict]:
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
        temporary_password: Optional[str] = None
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
            user_data["credentials"] = [{
                "type": "password",
                "value": temporary_password,
                "temporary": True,
            }]

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
    async def get_clients(self, tenant_id: Optional[str] = None) -> list[dict]:
        """Get all clients, optionally filtered by tenant"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        clients = self._admin.get_clients()

        if tenant_id:
            # Filter by client attribute or naming convention
            clients = [
                c for c in clients
                if c.get("attributes", {}).get("tenant_id", [None])[0] == tenant_id
                or c.get("clientId", "").startswith(f"{tenant_id}-")
            ]

        return clients

    async def get_client(self, client_id: str) -> Optional[dict]:
        """Get client by client_id"""
        if not self._admin:
            raise RuntimeError("Keycloak not connected")

        clients = self._admin.get_clients()
        for client in clients:
            if client["clientId"] == client_id:
                return client
        return None

    async def create_client(
        self,
        tenant_id: str,
        name: str,
        display_name: str,
        redirect_uris: list[str],
        description: str = ""
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
        await self.update_user(user_id, {
            "attributes": {"tenant_id": [tenant_id]}
        })

        return True

# Global instance
keycloak_service = KeycloakService()
