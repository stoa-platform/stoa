"""
Keycloak Certificate Sync Service (CAB-866)

Synchronizes mTLS client certificates to Keycloak OAuth2 clients
for RFC 8705 certificate-bound access tokens.

Flow: CertificateService → Event → KafkaCertConsumer → KeycloakCertSyncService
"""
import base64
import json
import logging
from typing import Optional

from src.models.client import Client
from src.services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)


def hex_to_base64url(hex_fingerprint: str) -> str:
    """Convert hex fingerprint to base64url (RFC 8705 x5t#S256 format)."""
    raw_bytes = bytes.fromhex(hex_fingerprint.replace(":", ""))
    b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii")
    return b64.rstrip("=")


# Protocol mapper definitions for certificate-bound tokens
CNF_MAPPER = {
    "name": "cnf-certificate-binding",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-hardcoded-claim-mapper",
    "config": {
        "claim.name": "cnf",
        "jsonType.label": "JSON",
        "access.token.claim": "true",
        "id.token.claim": "false",
    },
}

TENANT_MAPPER = {
    "name": "tenant-mapper",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-hardcoded-claim-mapper",
    "config": {
        "claim.name": "tenant",
        "jsonType.label": "String",
        "access.token.claim": "true",
        "id.token.claim": "true",
    },
}


class KeycloakCertSyncService:
    """Syncs STOA mTLS clients to Keycloak OAuth2 clients with RFC 8705 attributes."""

    def _build_client_id(self, client: Client) -> str:
        return f"mtls-{client.tenant_id}-{client.certificate_cn}"

    def _build_attributes(
        self,
        client: Client,
        fingerprint_b64url: str,
        previous_fingerprint: Optional[str] = None,
        grace_expires_at: Optional[str] = None,
    ) -> dict:
        attrs = {
            "x509.certificate.sha256": fingerprint_b64url,
            "x509.subjectdn": f"CN={client.certificate_cn}",
            "x509.certificate.serial": client.certificate_serial or "",
            "stoa.tenant": str(client.tenant_id),
            "stoa.applications": "[]",
        }
        if client.certificate_not_after:
            attrs["stoa.cert.valid_until"] = client.certificate_not_after.isoformat()
        if previous_fingerprint:
            attrs["x509.certificate.sha256.previous"] = previous_fingerprint
        if grace_expires_at:
            attrs["stoa.cert.grace_expires_at"] = grace_expires_at
        return attrs

    def _build_cnf_mapper(self, fingerprint_b64url: str) -> dict:
        mapper = json.loads(json.dumps(CNF_MAPPER))
        mapper["config"]["claim.value"] = json.dumps(
            {"x5t#S256": fingerprint_b64url}
        )
        return mapper

    def _build_tenant_mapper(self, tenant_id: str) -> dict:
        mapper = json.loads(json.dumps(TENANT_MAPPER))
        mapper["config"]["claim.value"] = tenant_id
        return mapper

    async def sync_client_certificate(
        self, client: Client, correlation_id: str
    ) -> dict:
        """Create or update a Keycloak OAuth2 client for the mTLS certificate."""
        kc_client_id = self._build_client_id(client)
        fingerprint_b64url = hex_to_base64url(client.certificate_fingerprint)
        attributes = self._build_attributes(client, fingerprint_b64url)

        log_extra = {
            "correlation_id": correlation_id,
            "kc_client_id": kc_client_id,
            "tenant_id": client.tenant_id,
        }

        existing = await keycloak_service.get_client(kc_client_id)
        if existing:
            # Update existing client
            kc_uuid = existing["id"]
            await keycloak_service.update_client(kc_uuid, {"attributes": attributes})
            logger.info("keycloak_cert_sync_updated", extra=log_extra)
            return {"action": "updated", "keycloak_client_id": kc_client_id, "keycloak_uuid": kc_uuid}

        # Create new Keycloak client for mTLS
        client_data = {
            "clientId": kc_client_id,
            "name": f"mTLS: {client.name}",
            "description": f"Certificate-bound client for {client.certificate_cn}",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "implicitFlowEnabled": False,
            "clientAuthenticatorType": "client-x509",
            "attributes": attributes,
            "protocolMappers": [
                self._build_cnf_mapper(fingerprint_b64url),
                self._build_tenant_mapper(str(client.tenant_id)),
            ],
        }

        keycloak_service._admin.create_client(client_data)

        created = await keycloak_service.get_client(kc_client_id)
        if not created:
            raise RuntimeError(f"Failed to create Keycloak client {kc_client_id}")

        logger.info("keycloak_cert_sync_created", extra=log_extra)
        return {
            "action": "created",
            "keycloak_client_id": kc_client_id,
            "keycloak_uuid": created["id"],
        }

    async def rotate_client_certificate(
        self,
        client: Client,
        old_fingerprint_hex: str,
        correlation_id: str,
        grace_expires_at: Optional[str] = None,
    ) -> dict:
        """Update Keycloak client with new cert, keeping previous fingerprint for grace period."""
        kc_client_id = self._build_client_id(client)
        new_fingerprint_b64url = hex_to_base64url(client.certificate_fingerprint)
        old_fingerprint_b64url = hex_to_base64url(old_fingerprint_hex)

        attributes = self._build_attributes(
            client, new_fingerprint_b64url,
            previous_fingerprint=old_fingerprint_b64url,
            grace_expires_at=grace_expires_at,
        )

        log_extra = {
            "correlation_id": correlation_id,
            "kc_client_id": kc_client_id,
            "tenant_id": client.tenant_id,
        }

        existing = await keycloak_service.get_client(kc_client_id)
        if not existing:
            logger.warning("keycloak_cert_rotate_missing_client", extra=log_extra)
            return await self.sync_client_certificate(client, correlation_id)

        kc_uuid = existing["id"]
        # Update attributes and cnf mapper
        await keycloak_service.update_client(kc_uuid, {
            "attributes": attributes,
            "protocolMappers": [
                self._build_cnf_mapper(new_fingerprint_b64url),
                self._build_tenant_mapper(str(client.tenant_id)),
            ],
        })

        logger.info("keycloak_cert_sync_rotated", extra=log_extra)
        return {
            "action": "rotated",
            "keycloak_client_id": kc_client_id,
            "keycloak_uuid": kc_uuid,
        }

    async def revoke_client_certificate(
        self, client: Client, correlation_id: str
    ) -> dict:
        """Disable the Keycloak client when the certificate is revoked."""
        kc_client_id = self._build_client_id(client)

        log_extra = {
            "correlation_id": correlation_id,
            "kc_client_id": kc_client_id,
            "tenant_id": client.tenant_id,
        }

        existing = await keycloak_service.get_client(kc_client_id)
        if not existing:
            logger.warning("keycloak_cert_revoke_missing_client", extra=log_extra)
            return {"action": "noop", "keycloak_client_id": kc_client_id}

        kc_uuid = existing["id"]
        await keycloak_service.update_client(kc_uuid, {"enabled": False})

        logger.info("keycloak_cert_sync_revoked", extra=log_extra)
        return {
            "action": "revoked",
            "keycloak_client_id": kc_client_id,
            "keycloak_uuid": kc_uuid,
        }


    async def clear_previous_fingerprint(
        self, client: Client, correlation_id: str
    ) -> dict:
        """Remove previous fingerprint and grace expiry from Keycloak after grace period ends."""
        kc_client_id = self._build_client_id(client)

        log_extra = {
            "correlation_id": correlation_id,
            "kc_client_id": kc_client_id,
            "tenant_id": client.tenant_id,
        }

        existing = await keycloak_service.get_client(kc_client_id)
        if not existing:
            logger.warning("keycloak_clear_previous_missing_client", extra=log_extra)
            return {"action": "noop", "keycloak_client_id": kc_client_id}

        kc_uuid = existing["id"]
        attrs = existing.get("attributes", {})
        attrs.pop("x509.certificate.sha256.previous", None)
        attrs.pop("stoa.cert.grace_expires_at", None)

        await keycloak_service.update_client(kc_uuid, {"attributes": attrs})
        logger.info("keycloak_cert_previous_cleared", extra=log_extra)
        return {
            "action": "cleared_previous",
            "keycloak_client_id": kc_client_id,
            "keycloak_uuid": kc_uuid,
        }


keycloak_cert_sync_service = KeycloakCertSyncService()
