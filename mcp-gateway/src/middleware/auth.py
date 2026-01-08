"""OIDC Authentication Middleware for Keycloak.

Validates JWT tokens from Keycloak and extracts user claims.
Supports multiple authentication schemes:
- Bearer token in Authorization header
- API Key in X-API-Key header (for M2M)
"""

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import httpx
import structlog
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from pydantic import BaseModel

from ..config import get_settings

logger = structlog.get_logger(__name__)

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class TokenClaims(BaseModel):
    """Validated token claims."""

    sub: str | None = None  # Subject (user ID) - may be missing for service accounts
    email: str | None = None
    preferred_username: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    realm_access: dict[str, list[str]] | None = None
    resource_access: dict[str, dict[str, list[str]]] | None = None
    scope: str | None = None
    client_id: str | None = None
    azp: str | None = None  # Authorized party
    iss: str | None = None  # Issuer
    aud: str | list[str] | None = None  # Audience
    exp: int | None = None  # Expiration
    iat: int | None = None  # Issued at
    acr: str | None = None  # Authentication Context Class Reference (for step-up auth/TOTP)

    @property
    def subject(self) -> str:
        """Get the subject identifier (user ID or client ID)."""
        return self.sub or self.client_id or self.azp or "unknown"

    @property
    def roles(self) -> list[str]:
        """Extract realm roles from token."""
        if self.realm_access and "roles" in self.realm_access:
            return self.realm_access["roles"]
        return []

    @property
    def client_roles(self) -> dict[str, list[str]]:
        """Extract client-specific roles."""
        if not self.resource_access:
            return {}
        return {
            client: access.get("roles", [])
            for client, access in self.resource_access.items()
        }

    def has_role(self, role: str) -> bool:
        """Check if user has a specific realm role."""
        return role in self.roles

    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope."""
        if not self.scope:
            return False
        return scope in self.scope.split()


@dataclass
class JWKSCache:
    """Cache for JWKS (JSON Web Key Set)."""

    keys: dict[str, Any]
    fetched_at: float
    ttl: int = 300  # 5 minutes


class OIDCAuthenticator:
    """OIDC Authenticator for Keycloak.

    Handles JWT validation using Keycloak's public keys (JWKS).
    """

    def __init__(self, keycloak_url: str, realm: str):
        self.keycloak_url = keycloak_url.rstrip("/")
        self.realm = realm
        self.issuer = f"{self.keycloak_url}/realms/{self.realm}"
        self.jwks_uri = f"{self.issuer}/protocol/openid-connect/certs"
        self._jwks_cache: JWKSCache | None = None
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS from Keycloak."""
        # Check cache
        if self._jwks_cache:
            age = time.time() - self._jwks_cache.fetched_at
            if age < self._jwks_cache.ttl:
                return self._jwks_cache.keys

        logger.info("Fetching JWKS from Keycloak", jwks_uri=self.jwks_uri)

        try:
            client = await self._get_http_client()
            response = await client.get(self.jwks_uri)
            response.raise_for_status()
            jwks = response.json()

            # Cache the keys
            self._jwks_cache = JWKSCache(
                keys=jwks,
                fetched_at=time.time(),
            )

            logger.info("JWKS fetched successfully", num_keys=len(jwks.get("keys", [])))
            return jwks

        except httpx.HTTPError as e:
            logger.error("Failed to fetch JWKS", error=str(e))
            # Return cached keys if available
            if self._jwks_cache:
                logger.warning("Using stale JWKS cache")
                return self._jwks_cache.keys
            raise HTTPException(
                status_code=503,
                detail="Authentication service unavailable",
            )

    async def validate_token(self, token: str) -> TokenClaims:
        """Validate JWT token and return claims.

        Args:
            token: JWT token string

        Returns:
            TokenClaims with validated claims

        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Get JWKS
            jwks = await self._fetch_jwks()

            # Decode without verification first to get the key ID
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            if not kid:
                raise HTTPException(
                    status_code=401,
                    detail="Token missing key ID",
                )

            # Find the matching key
            rsa_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = key
                    break

            if not rsa_key:
                # Key not found, try refreshing JWKS
                self._jwks_cache = None
                jwks = await self._fetch_jwks()
                for key in jwks.get("keys", []):
                    if key.get("kid") == kid:
                        rsa_key = key
                        break

            if not rsa_key:
                raise HTTPException(
                    status_code=401,
                    detail="Unable to find appropriate key",
                )

            # Validate token
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={
                    "verify_aud": False,  # Keycloak doesn't always set audience
                    "verify_exp": True,
                },
            )

            return TokenClaims(**payload)

        except ExpiredSignatureError:
            logger.warning("Token expired")
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
            )
        except JWTError as e:
            logger.warning("JWT validation failed", error=str(e))
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()


# Global authenticator instance
_authenticator: OIDCAuthenticator | None = None


def get_authenticator() -> OIDCAuthenticator:
    """Get or create authenticator instance."""
    global _authenticator
    if _authenticator is None:
        settings = get_settings()
        _authenticator = OIDCAuthenticator(
            keycloak_url=settings.keycloak_url,
            realm=settings.keycloak_realm,
        )
    return _authenticator


async def get_current_user(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
    api_key: Annotated[str | None, Security(api_key_header)] = None,
) -> TokenClaims:
    """Dependency to get the current authenticated user.

    Supports:
    - Bearer token authentication
    - API Key authentication (for M2M)

    Args:
        request: FastAPI request
        bearer: Bearer token from Authorization header
        api_key: API key from X-API-Key header

    Returns:
        TokenClaims with user information

    Raises:
        HTTPException: If authentication fails
    """
    settings = get_settings()

    # Skip auth in debug mode if configured
    if settings.debug and settings.environment == "dev":
        # Check for X-Debug-User header for testing
        debug_user = request.headers.get("X-Debug-User")
        if debug_user:
            logger.warning("Using debug authentication", user=debug_user)
            return TokenClaims(
                sub=debug_user,
                preferred_username=debug_user,
                realm_access={"roles": ["admin", "developer"]},
            )

    # Try Bearer token first
    if bearer and bearer.credentials:
        authenticator = get_authenticator()
        claims = await authenticator.validate_token(bearer.credentials)
        logger.debug(
            "User authenticated via Bearer token",
            sub=claims.subject,
            username=claims.preferred_username,
        )
        return claims

    # Try API Key
    if api_key:
        # TODO: Implement API key validation against Control Plane API
        # For now, reject API keys
        raise HTTPException(
            status_code=401,
            detail="API Key authentication not yet implemented",
        )

    # No authentication provided
    raise HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> TokenClaims | None:
    """Dependency for optional authentication.

    Returns None if no token provided, raises if token is invalid.
    """
    if not bearer or not bearer.credentials:
        return None

    authenticator = get_authenticator()
    return await authenticator.validate_token(bearer.credentials)


def require_role(role: str):
    """Dependency factory to require a specific role.

    Usage:
        @app.get("/admin", dependencies=[Depends(require_role("admin"))])
        async def admin_endpoint():
            ...
    """

    async def role_checker(
        user: Annotated[TokenClaims, Depends(get_current_user)],
    ) -> TokenClaims:
        if not user.has_role(role):
            logger.warning(
                "Access denied - missing role",
                user=user.subject,
                required_role=role,
                user_roles=user.roles,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' required",
            )
        return user

    return role_checker


def require_scope(scope: str):
    """Dependency factory to require a specific scope.

    Usage:
        @app.get("/data", dependencies=[Depends(require_scope("read:data"))])
        async def data_endpoint():
            ...
    """

    async def scope_checker(
        user: Annotated[TokenClaims, Depends(get_current_user)],
    ) -> TokenClaims:
        if not user.has_scope(scope):
            logger.warning(
                "Access denied - missing scope",
                user=user.subject,
                required_scope=scope,
                user_scopes=user.scope,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{scope}' required",
            )
        return user

    return scope_checker
