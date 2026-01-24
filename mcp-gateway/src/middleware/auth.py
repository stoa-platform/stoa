"""OIDC Authentication Middleware for Keycloak.

Validates JWT tokens from Keycloak and extracts user claims.
Supports multiple authentication schemes:
- Bearer token in Authorization header
- API Key in X-API-Key header (for M2M)
- OAuth2 Client Credentials (client_id/client_secret via Basic Auth)

CAB-604: Updated with 12 granular OAuth2 scopes and 6 personas.
"""

import base64
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import httpx
import structlog
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader, HTTPBasic, HTTPBasicCredentials
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from pydantic import BaseModel

from ..config import get_settings
from ..policy.scopes import (
    Scope,
    LegacyScope,
    Persona,
    PERSONAS,
    LEGACY_ROLE_TO_PERSONA,
    expand_legacy_scopes,
    get_scopes_for_roles,
    get_persona_for_roles,
)

logger = structlog.get_logger(__name__)

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
basic_scheme = HTTPBasic(auto_error=False)


class TokenClaims(BaseModel):
    """Validated token claims.

    CAB-604: Extended with granular scope and persona support.
    CAB-672/ADR-001: Added raw_token for Core API calls.
    """

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
    tenant_id: str | None = None  # Tenant ID for multi-tenancy
    raw_token: str | None = None  # ADR-001: Original JWT token for Core API calls

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
        """Check if token has a specific scope (direct or via expansion)."""
        effective_scopes = self.effective_scopes
        return scope in effective_scopes

    @property
    def token_scopes(self) -> set[str]:
        """Get raw scopes from the token."""
        if not self.scope:
            return set()
        return set(self.scope.split())

    @property
    def effective_scopes(self) -> set[str]:
        """Get all effective scopes including role-derived and expanded scopes.

        CAB-604: Combines token scopes, role-derived scopes, and expands
        legacy scopes to their granular equivalents.
        """
        scopes = self.token_scopes.copy()

        # Add scopes from persona roles
        role_scopes = get_scopes_for_roles(self.roles)
        scopes.update(role_scopes)

        # Expand legacy scopes to granular
        expanded = expand_legacy_scopes(scopes)
        return expanded

    @property
    def persona(self) -> Persona | None:
        """Get the user's persona based on their roles.

        CAB-604: Returns the highest-privilege persona for the user.
        """
        return get_persona_for_roles(self.roles)

    @property
    def persona_name(self) -> str | None:
        """Get the user's persona name."""
        persona = self.persona
        return persona.name if persona else None

    def has_any_scope(self, *scopes: str) -> bool:
        """Check if user has any of the specified scopes."""
        effective = self.effective_scopes
        return any(scope in effective for scope in scopes)

    def has_all_scopes(self, *scopes: str) -> bool:
        """Check if user has all of the specified scopes."""
        effective = self.effective_scopes
        return all(scope in effective for scope in scopes)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.has_any_scope(
            LegacyScope.ADMIN.value,
            Scope.ADMIN_READ.value,
            Scope.ADMIN_WRITE.value,
        )

    @property
    def can_write(self) -> bool:
        """Check if user has write privileges."""
        return self.has_any_scope(
            LegacyScope.WRITE.value,
            LegacyScope.ADMIN.value,
            Scope.CATALOG_WRITE.value,
            Scope.SUBSCRIPTION_WRITE.value,
        )

    def can_access_tenant(self, tenant_id: str | None) -> bool:
        """Check if user can access resources in a tenant.

        CAB-604: Uses persona constraints for tenant isolation.
        """
        if not tenant_id:
            return True  # Global resources

        # Admins can access all tenants
        if self.is_admin:
            return True

        # Check persona constraints
        persona = self.persona
        if persona and not persona.own_tenant_only:
            return True

        # Must match own tenant
        return self.tenant_id == tenant_id


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

            # Normalize tenant_id if it's an array (Keycloak user attributes)
            if "tenant_id" in payload and isinstance(payload["tenant_id"], list):
                # Take the first tenant_id if it's a list
                payload["tenant_id"] = payload["tenant_id"][0] if payload["tenant_id"] else None

            # ADR-001: Store raw token for Core API calls
            claims = TokenClaims(**payload)
            claims.raw_token = token
            return claims

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

    async def exchange_client_credentials(
        self, client_id: str, client_secret: str
    ) -> TokenClaims:
        """Exchange client credentials for access token and return claims.

        Uses OAuth2 Client Credentials flow against Keycloak.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret

        Returns:
            TokenClaims with validated claims

        Raises:
            HTTPException: If credentials are invalid
        """
        settings = get_settings()
        token_endpoint = settings.keycloak_token_endpoint

        try:
            client = await self._get_http_client()
            response = await client.post(
                token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 401:
                logger.warning(
                    "Client credentials authentication failed",
                    client_id=client_id,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Invalid client credentials",
                )

            response.raise_for_status()
            token_data = response.json()

            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(
                    status_code=500,
                    detail="No access token in response",
                )

            # Validate the returned token
            claims = await self.validate_token(access_token)
            logger.info(
                "Client authenticated via credentials",
                client_id=client_id,
                subject=claims.subject,
            )
            return claims

        except httpx.HTTPStatusError as e:
            logger.error(
                "Client credentials exchange failed",
                client_id=client_id,
                status_code=e.response.status_code,
            )
            raise HTTPException(
                status_code=401,
                detail="Client credentials authentication failed",
            )
        except httpx.HTTPError as e:
            logger.error(
                "Keycloak token endpoint error",
                error=str(e),
            )
            raise HTTPException(
                status_code=503,
                detail="Authentication service unavailable",
            )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()


# Token cache for client credentials (avoid repeated token exchanges)
_client_token_cache: dict[str, tuple[TokenClaims, float]] = {}
CLIENT_TOKEN_CACHE_TTL = 300  # 5 minutes


async def get_cached_client_token(
    authenticator: "OIDCAuthenticator",
    client_id: str,
    client_secret: str,
) -> TokenClaims:
    """Get cached token for client credentials or exchange new one."""
    cache_key = f"{client_id}:{client_secret[:8]}"  # Use prefix of secret for key

    # Check cache
    if cache_key in _client_token_cache:
        claims, cached_at = _client_token_cache[cache_key]
        if time.time() - cached_at < CLIENT_TOKEN_CACHE_TTL:
            # Check if token is not expired
            if claims.exp and claims.exp > time.time():
                return claims

    # Exchange credentials for new token
    claims = await authenticator.exchange_client_credentials(client_id, client_secret)

    # Cache the token
    _client_token_cache[cache_key] = (claims, time.time())

    return claims


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
    basic: Annotated[HTTPBasicCredentials | None, Security(basic_scheme)] = None,
) -> TokenClaims:
    """Dependency to get the current authenticated user.

    Supports:
    - Bearer token authentication (JWT)
    - Basic Auth with OAuth2 client credentials (client_id:client_secret)
    - API Key authentication (for M2M)

    Args:
        request: FastAPI request
        bearer: Bearer token from Authorization header
        api_key: API key from X-API-Key header
        basic: Basic auth credentials (client_id:client_secret)

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
        logger.info(
            "Attempting Bearer token authentication",
            token_prefix=bearer.credentials[:50] if len(bearer.credentials) > 50 else bearer.credentials,
        )
        authenticator = get_authenticator()
        try:
            claims = await authenticator.validate_token(bearer.credentials)
            logger.info(
                "User authenticated via Bearer token",
                sub=claims.subject,
                username=claims.preferred_username,
                issuer=claims.iss,
            )
            return claims
        except HTTPException as e:
            logger.warning(
                "Bearer token validation failed",
                error=e.detail,
                token_prefix=bearer.credentials[:50] if len(bearer.credentials) > 50 else bearer.credentials,
            )
            raise

    # Try Basic Auth (OAuth2 Client Credentials)
    if basic and basic.username and basic.password:
        authenticator = get_authenticator()
        claims = await get_cached_client_token(
            authenticator, basic.username, basic.password
        )
        logger.debug(
            "User authenticated via Client Credentials",
            client_id=basic.username,
            sub=claims.subject,
        )
        return claims

    # Try API Key (stoa_sk_* format)
    if api_key:
        if api_key.startswith("stoa_sk_"):
            from ..services.api_key import validate_api_key
            claims = await validate_api_key(api_key)
            if claims:
                logger.debug(
                    "User authenticated via API Key",
                    key_prefix=api_key[:16],
                    sub=claims.subject,
                )
                return claims
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    # No authentication provided
    # Log all headers for debugging Claude.ai auth issues
    all_headers = dict(request.headers)
    # Redact sensitive headers
    if "authorization" in all_headers:
        all_headers["authorization"] = all_headers["authorization"][:50] + "..."
    logger.warning(
        "No authentication provided",
        has_bearer=bool(bearer),
        has_api_key=bool(api_key),
        has_basic=bool(basic),
        auth_header=request.headers.get("Authorization", "")[:50] if request.headers.get("Authorization") else None,
        path=str(request.url.path),
        method=request.method,
        mcp_session_id=request.headers.get("Mcp-Session-Id"),
    )
    print(f"[AUTH DEBUG] 401 for {request.method} {request.url.path} - Headers: {all_headers}", flush=True)
    raise HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": 'Bearer, Basic realm="STOA MCP Gateway"'},
    )


async def get_optional_user(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
    basic: Annotated[HTTPBasicCredentials | None, Security(basic_scheme)] = None,
) -> TokenClaims | None:
    """Dependency for optional authentication.

    Returns None if no credentials provided, raises if credentials are invalid.
    Supports Bearer token and Basic Auth (client credentials).
    """
    authenticator = get_authenticator()

    # Try Bearer token
    if bearer and bearer.credentials:
        return await authenticator.validate_token(bearer.credentials)

    # Try Basic Auth (client credentials)
    if basic and basic.username and basic.password:
        return await get_cached_client_token(
            authenticator, basic.username, basic.password
        )

    return None


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

    CAB-604: Uses effective scopes (including expanded legacy scopes).

    Usage:
        @app.get("/data", dependencies=[Depends(require_scope("stoa:catalog:read"))])
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
                user_scopes=list(user.effective_scopes),
                persona=user.persona_name,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{scope}' required",
            )
        return user

    return scope_checker


def require_any_scope(*scopes: str):
    """Dependency factory to require any of the specified scopes.

    CAB-604: Allows access if user has at least one of the scopes.

    Usage:
        @app.get("/data", dependencies=[Depends(require_any_scope(
            Scope.CATALOG_READ.value, Scope.ADMIN_READ.value
        ))])
        async def data_endpoint():
            ...
    """

    async def scope_checker(
        user: Annotated[TokenClaims, Depends(get_current_user)],
    ) -> TokenClaims:
        if not user.has_any_scope(*scopes):
            logger.warning(
                "Access denied - missing scopes",
                user=user.subject,
                required_scopes=list(scopes),
                user_scopes=list(user.effective_scopes),
                persona=user.persona_name,
            )
            raise HTTPException(
                status_code=403,
                detail=f"One of scopes {list(scopes)} required",
            )
        return user

    return scope_checker


def require_all_scopes(*scopes: str):
    """Dependency factory to require all of the specified scopes.

    CAB-604: Requires user to have all specified scopes.

    Usage:
        @app.get("/admin-data", dependencies=[Depends(require_all_scopes(
            Scope.ADMIN_READ.value, Scope.SECURITY_READ.value
        ))])
        async def admin_data_endpoint():
            ...
    """

    async def scope_checker(
        user: Annotated[TokenClaims, Depends(get_current_user)],
    ) -> TokenClaims:
        if not user.has_all_scopes(*scopes):
            missing = set(scopes) - user.effective_scopes
            logger.warning(
                "Access denied - missing scopes",
                user=user.subject,
                required_scopes=list(scopes),
                missing_scopes=list(missing),
                user_scopes=list(user.effective_scopes),
                persona=user.persona_name,
            )
            raise HTTPException(
                status_code=403,
                detail=f"All scopes {list(scopes)} required",
            )
        return user

    return scope_checker


def require_persona(*personas: str):
    """Dependency factory to require one of the specified personas.

    CAB-604: Requires user to have a specific persona role.

    Usage:
        @app.get("/admin", dependencies=[Depends(require_persona("stoa.admin", "stoa.security"))])
        async def admin_endpoint():
            ...
    """

    async def persona_checker(
        user: Annotated[TokenClaims, Depends(get_current_user)],
    ) -> TokenClaims:
        user_persona = user.persona_name
        if not user_persona or user_persona not in personas:
            logger.warning(
                "Access denied - missing persona",
                user=user.subject,
                required_personas=list(personas),
                user_persona=user_persona,
                user_roles=user.roles,
            )
            raise HTTPException(
                status_code=403,
                detail=f"One of personas {list(personas)} required",
            )
        return user

    return persona_checker


def require_tenant_access(tenant_id_param: str = "tenant_id"):
    """Dependency factory to require access to a specific tenant.

    CAB-604: Uses persona constraints for tenant isolation.

    Usage:
        @app.get("/tenants/{tenant_id}/data")
        async def tenant_data(
            tenant_id: str,
            user: TokenClaims = Depends(require_tenant_access("tenant_id"))
        ):
            ...
    """

    async def tenant_checker(
        request: Request,
        user: Annotated[TokenClaims, Depends(get_current_user)],
    ) -> TokenClaims:
        # Get tenant_id from path parameters
        tenant_id = request.path_params.get(tenant_id_param)

        if tenant_id and not user.can_access_tenant(tenant_id):
            logger.warning(
                "Access denied - tenant isolation",
                user=user.subject,
                user_tenant=user.tenant_id,
                requested_tenant=tenant_id,
                persona=user.persona_name,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Access to tenant '{tenant_id}' denied",
            )
        return user

    return tenant_checker


# =============================================================================
# CAB-604: Pre-built scope requirements for common operations
# =============================================================================

# Catalog operations
require_catalog_read = require_scope(Scope.CATALOG_READ.value)
require_catalog_write = require_scope(Scope.CATALOG_WRITE.value)

# Subscription operations
require_subscription_read = require_scope(Scope.SUBSCRIPTION_READ.value)
require_subscription_write = require_scope(Scope.SUBSCRIPTION_WRITE.value)

# Observability operations
require_observability_read = require_scope(Scope.OBSERVABILITY_READ.value)
require_observability_write = require_scope(Scope.OBSERVABILITY_WRITE.value)

# Tool operations
require_tools_read = require_scope(Scope.TOOLS_READ.value)
require_tools_execute = require_scope(Scope.TOOLS_EXECUTE.value)

# Admin operations
require_admin_read = require_scope(Scope.ADMIN_READ.value)
require_admin_write = require_scope(Scope.ADMIN_WRITE.value)

# Security operations
require_security_read = require_scope(Scope.SECURITY_READ.value)
require_security_write = require_scope(Scope.SECURITY_WRITE.value)
