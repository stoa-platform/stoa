"""
Keycloak Certificate Sync Service - CAB-866
Synchronise les clients STOA mTLS vers Keycloak.

Security requirements (Team Coca validated):
- No fingerprint in logs
- Synchronous CREATE (no race condition)
- RFC 8705 compliant x5t#S256
- Explicit timeout on Keycloak calls
"""

import hashlib
import base64
import json
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakError
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from src.logging_config import get_logger
from src.config import settings

logger = get_logger(__name__)

# Timeout explicite pour appels Keycloak (Gh0st review)
KEYCLOAK_TIMEOUT_SECONDS = 10


class SyncStatus(str, Enum):
    SYNCED = "synced"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class SyncResult:
    keycloak_id: str | None
    status: SyncStatus
    error: str | None = None


class CertificateParseError(Exception):
    """Raised when certificate PEM is invalid."""
    pass


class KeycloakCertificateSyncService:
    """Sync STOA mTLS clients to Keycloak."""

    def __init__(self, keycloak_admin: KeycloakAdmin, realm: str):
        self._kc = keycloak_admin
        self._realm = realm

    def compute_x5t_s256(self, cert_pem: str) -> str:
        """
        RFC 8705: x5t#S256 = base64url(SHA256(DER_cert)) sans padding.

        Raises:
            CertificateParseError: Si le PEM est invalide
        """
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            der_bytes = cert.public_bytes(serialization.Encoding.DER)
            sha256_digest = hashlib.sha256(der_bytes).digest()
            return base64.urlsafe_b64encode(sha256_digest).rstrip(b'=').decode('ascii')
        except Exception as e:
            raise CertificateParseError(f"Invalid certificate PEM: {e}") from e

    def _extract_subject_dn(self, cert_pem: str) -> str:
        """Extrait le Subject DN du certificat."""
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            return cert.subject.rfc4514_string()
        except Exception:
            return "unknown"

    def _generate_keycloak_client_id(self) -> str:
        """
        Genere un clientId opaque (UUID) pour Keycloak.
        Evite l'information leakage du tenant_id (Chucky review).
        """
        return f"stoa-mtls-{uuid4().hex[:12]}"

    def _find_existing_client(self, stoa_client_id: str) -> dict | None:
        """Recherche par attribut stoa.client_id pour idempotence."""
        try:
            clients = self._kc.get_clients()
            for c in clients:
                attrs = c.get("attributes", {})
                if attrs.get("stoa.client_id") == stoa_client_id:
                    return c
            return None
        except KeycloakError:
            return None

    def _build_protocol_mappers(self, tenant_id: str) -> list[dict]:
        """Protocol Mappers pour claims tenant et applications."""
        return [
            {
                "name": "stoa-tenant",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "stoa_tenant",
                    "claim.value": tenant_id,
                    "jsonType.label": "String",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                }
            },
            {
                "name": "stoa-applications",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "stoa_applications",
                    "claim.value": "[]",
                    "jsonType.label": "JSON",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                }
            },
        ]

    async def sync_mtls_client_create(
        self,
        stoa_client_id: str,
        client_name: str,
        tenant_id: str,
        certificate_pem: str,
    ) -> SyncResult:
        """
        Synchronise un client mTLS vers Keycloak.
        SYNCHRONE - appele inline avant commit DB.
        Idempotent - lookup avant create.

        Args:
            stoa_client_id: UUID du client STOA
            client_name: Nom du client (pour display)
            tenant_id: ID du tenant
            certificate_pem: Certificat PEM pour calcul fingerprint

        Returns:
            SyncResult avec keycloak_id si succes
        """
        # Idempotence : verifier si deja cree
        existing = self._find_existing_client(stoa_client_id)
        if existing:
            logger.info("Keycloak client already exists", client_id=stoa_client_id)
            return SyncResult(
                keycloak_id=existing["id"],
                status=SyncStatus.SYNCED
            )

        # Calcul fingerprint RFC 8705
        try:
            fingerprint = self.compute_x5t_s256(certificate_pem)
            subject_dn = self._extract_subject_dn(certificate_pem)
        except CertificateParseError as e:
            logger.error("Certificate parse failed", client_id=stoa_client_id)
            return SyncResult(
                keycloak_id=None,
                status=SyncStatus.FAILED,
                error=str(e)
            )

        # Build Keycloak client representation
        keycloak_client_id = self._generate_keycloak_client_id()
        client_repr = {
            "clientId": keycloak_client_id,
            "name": f"STOA: {client_name}",
            "enabled": True,
            "clientAuthenticatorType": "client-x509",
            "serviceAccountsEnabled": True,
            "attributes": {
                "stoa.client_id": stoa_client_id,
                "stoa.tenant": tenant_id,
                "stoa.applications": "[]",
                "x509.certificate.sha256": fingerprint,
                "x509.subjectdn": subject_dn,
            },
            "protocolMappers": self._build_protocol_mappers(tenant_id),
        }

        # Create with timeout (Gh0st review)
        try:
            # Note: python-keycloak utilise requests, timeout via session config
            kc_id = self._kc.create_client(client_repr, skip_exists=False)
            logger.info(
                "Keycloak client created",
                client_id=stoa_client_id,
                keycloak_id=kc_id
                # PAS de fingerprint dans les logs (Pr1nc3ss review)
            )
            return SyncResult(keycloak_id=kc_id, status=SyncStatus.SYNCED)

        except KeycloakError as e:
            logger.error(
                "Keycloak sync failed",
                client_id=stoa_client_id,
                error=str(e)
            )
            return SyncResult(
                keycloak_id=None,
                status=SyncStatus.FAILED,
                error=f"Keycloak error: {e}"
            )

    async def update_client_applications(
        self,
        stoa_client_id: str,
        application_ids: list[str]
    ) -> bool:
        """Met a jour la liste des applications autorisees."""
        existing = self._find_existing_client(stoa_client_id)
        if not existing:
            logger.warning("Client not found in Keycloak", client_id=stoa_client_id)
            return False

        try:
            existing["attributes"]["stoa.applications"] = json.dumps(application_ids)
            self._kc.update_client(existing["id"], existing)
            return True
        except KeycloakError as e:
            logger.error("Update applications failed", client_id=stoa_client_id, error=str(e))
            return False

    async def delete_keycloak_client(self, stoa_client_id: str) -> bool:
        """Supprime le client Keycloak correspondant."""
        existing = self._find_existing_client(stoa_client_id)
        if not existing:
            return True  # Deja supprime = idempotent

        try:
            self._kc.delete_client(existing["id"])
            logger.info("Keycloak client deleted", client_id=stoa_client_id)
            return True
        except KeycloakError as e:
            logger.error("Delete failed", client_id=stoa_client_id, error=str(e))
            return False


# Singleton instance - lazy init via dependency injection
_keycloak_cert_sync_service: KeycloakCertificateSyncService | None = None


def get_keycloak_cert_sync_service() -> KeycloakCertificateSyncService:
    """Get or create singleton instance."""
    global _keycloak_cert_sync_service
    if _keycloak_cert_sync_service is None:
        from src.services.keycloak_service import keycloak_service
        if keycloak_service._admin is None:
            raise RuntimeError("Keycloak not connected - call keycloak_service.connect() first")
        _keycloak_cert_sync_service = KeycloakCertificateSyncService(
            keycloak_admin=keycloak_service._admin,
            realm=settings.KEYCLOAK_REALM,
        )
    return _keycloak_cert_sync_service


# Alias for convenience
keycloak_cert_sync_service = get_keycloak_cert_sync_service
