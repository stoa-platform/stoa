# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
Certificate Validation Router (CAB-313)

Provides endpoints for validating client certificates for mTLS subscriptions.
- Parse PEM certificates
- Validate expiration
- Check certificate chain (optional)
- Return certificate metadata
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

# Import cryptography for certificate parsing
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import NameOID

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

router = APIRouter(prefix="/v1/certificates", tags=["certificates"])

# Warning threshold for certificate expiration (days)
EXPIRY_WARNING_DAYS = 30


class CertificateInfo(BaseModel):
    """Certificate information response model."""

    subject: str = Field(..., description="Certificate subject (CN, O, etc.)")
    issuer: str = Field(..., description="Certificate issuer")
    valid_from: datetime = Field(..., description="Certificate validity start date")
    valid_to: datetime = Field(..., description="Certificate validity end date")
    days_until_expiry: int = Field(..., description="Days until certificate expires")
    is_valid: bool = Field(..., description="Whether the certificate is currently valid")
    is_expired: bool = Field(..., description="Whether the certificate has expired")
    expires_soon: bool = Field(..., description="Warning: expires within 30 days")
    serial_number: str = Field(..., description="Certificate serial number")
    fingerprint_sha256: str = Field(..., description="SHA-256 fingerprint")
    key_size: int | None = Field(None, description="Public key size in bits")
    signature_algorithm: str = Field(..., description="Signature algorithm")
    san: list[str] = Field(default_factory=list, description="Subject Alternative Names")


class CertificateValidationRequest(BaseModel):
    """Request model for certificate validation."""

    pem_data: str = Field(..., description="PEM-encoded certificate data")


class CertificateValidationResponse(BaseModel):
    """Response model for certificate validation."""

    valid: bool = Field(..., description="Whether the certificate is valid for use")
    certificate: CertificateInfo | None = Field(None, description="Certificate details if parsed")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")


def _format_name(name: "x509.Name") -> str:
    """Format X.509 name to readable string."""
    parts = []
    for attr in name:
        oid_name = attr.oid._name if hasattr(attr.oid, "_name") else str(attr.oid)
        parts.append(f"{oid_name}={attr.value}")
    return ", ".join(parts)


def _get_san(cert: "x509.Certificate") -> list[str]:
    """Extract Subject Alternative Names from certificate."""
    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san = san_ext.value
        names = []
        for name in san:
            if isinstance(name, x509.DNSName):
                names.append(f"DNS:{name.value}")
            elif isinstance(name, x509.IPAddress):
                names.append(f"IP:{name.value}")
            elif isinstance(name, x509.RFC822Name):
                names.append(f"Email:{name.value}")
        return names
    except x509.ExtensionNotFound:
        return []


def _parse_certificate(pem_data: str) -> tuple[CertificateInfo | None, list[str], list[str]]:
    """
    Parse a PEM certificate and extract information.

    Returns:
        Tuple of (CertificateInfo, errors, warnings)
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        return None, ["cryptography library not available"], []

    errors: list[str] = []
    warnings: list[str] = []

    try:
        # Ensure PEM data has proper format
        pem_bytes = pem_data.encode("utf-8")

        # Try to load as certificate
        cert = x509.load_pem_x509_certificate(pem_bytes)

        # Extract basic info
        now = datetime.now(UTC)
        valid_from = cert.not_valid_before_utc
        valid_to = cert.not_valid_after_utc
        days_until_expiry = (valid_to - now).days

        is_expired = now > valid_to
        is_not_yet_valid = now < valid_from
        is_valid = not is_expired and not is_not_yet_valid
        expires_soon = days_until_expiry <= EXPIRY_WARNING_DAYS and days_until_expiry > 0

        # Check validity
        if is_expired:
            errors.append(f"Certificate expired on {valid_to.isoformat()}")
        if is_not_yet_valid:
            errors.append(f"Certificate not yet valid until {valid_from.isoformat()}")
        if expires_soon:
            warnings.append(f"Certificate expires in {days_until_expiry} days")

        # Get fingerprint
        fingerprint = cert.fingerprint(hashes.SHA256())
        fingerprint_hex = ":".join(f"{b:02x}" for b in fingerprint)

        # Get key size
        key_size = None
        try:
            public_key = cert.public_key()
            if hasattr(public_key, "key_size"):
                key_size = public_key.key_size
        except Exception:
            pass

        # Get signature algorithm
        sig_algo = cert.signature_algorithm_oid._name if hasattr(cert.signature_algorithm_oid, "_name") else str(cert.signature_algorithm_oid)

        cert_info = CertificateInfo(
            subject=_format_name(cert.subject),
            issuer=_format_name(cert.issuer),
            valid_from=valid_from,
            valid_to=valid_to,
            days_until_expiry=days_until_expiry,
            is_valid=is_valid,
            is_expired=is_expired,
            expires_soon=expires_soon,
            serial_number=format(cert.serial_number, "x"),
            fingerprint_sha256=fingerprint_hex,
            key_size=key_size,
            signature_algorithm=sig_algo,
            san=_get_san(cert),
        )

        return cert_info, errors, warnings

    except ValueError as e:
        return None, [f"Invalid PEM format: {e!s}"], []
    except Exception as e:
        return None, [f"Failed to parse certificate: {e!s}"], []


@router.post(
    "/validate",
    response_model=CertificateValidationResponse,
    summary="Validate a PEM certificate",
    description="Parse and validate a PEM-encoded X.509 certificate. Returns certificate details and validation status.",
)
async def validate_certificate(request: CertificateValidationRequest) -> CertificateValidationResponse:
    """
    Validate a PEM-encoded certificate.

    Checks:
    - Valid PEM format
    - Not expired
    - Not yet valid
    - Expiration warning (<30 days)

    Returns certificate metadata and validation status.
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Certificate validation not available: cryptography library not installed",
        )

    cert_info, errors, warnings = _parse_certificate(request.pem_data)

    return CertificateValidationResponse(
        valid=cert_info is not None and len(errors) == 0,
        certificate=cert_info,
        errors=errors,
        warnings=warnings,
    )


@router.post(
    "/upload",
    response_model=CertificateValidationResponse,
    summary="Upload and validate a certificate file",
    description="Upload a .pem or .crt file for validation.",
)
async def upload_certificate(file: UploadFile) -> CertificateValidationResponse:
    """
    Upload and validate a certificate file (.pem or .crt).
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Certificate validation not available: cryptography library not installed",
        )

    # Validate file extension
    if file.filename:
        allowed_extensions = {".pem", ".crt", ".cer", ".cert"}
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}",
            )

    # Read file content
    try:
        content = await file.read()
        pem_data = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file encoding. Certificate must be PEM-encoded (base64 text).",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {e!s}",
        )

    cert_info, errors, warnings = _parse_certificate(pem_data)

    return CertificateValidationResponse(
        valid=cert_info is not None and len(errors) == 0,
        certificate=cert_info,
        errors=errors,
        warnings=warnings,
    )


@router.get(
    "/health",
    summary="Check certificate validation service health",
)
async def health_check() -> dict:
    """Check if certificate validation is available."""
    return {
        "status": "healthy" if CRYPTOGRAPHY_AVAILABLE else "degraded",
        "cryptography_available": CRYPTOGRAPHY_AVAILABLE,
        "expiry_warning_days": EXPIRY_WARNING_DAYS,
    }
