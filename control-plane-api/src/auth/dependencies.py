"""FastAPI authentication dependencies.

CAB-330: Enhanced debug logging for authentication troubleshooting.
CAB-438: Sender-constrained token validation (RFC 8705/9449).
CAB-2082: JWT issuer validation + Keycloak public-key cache (Security P0-01).
CAB-2094: Split issuer (public KEYCLOAK_URL) from JWKS fetch (KEYCLOAK_INTERNAL_URL).
CAB-2146: Expose operator-key fingerprint on request.state for per-key rate-limit.
CAB-2153: Accept `stoa-mcp-gateway` as legacy audience during the Audience
Mapper rollout so MCP tokens authenticate even before the mapper lands.
"""

import hashlib
import time

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from ..config import settings
from ..logging_config import bind_request_context, get_logger
from .sender_constrained import validate_sender_constrained_token

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)

# CAB-2082: cache the Keycloak realm public key in-memory (TTL 5 min).
# Prior behavior refetched on every request — DoS vector if Keycloak slow,
# and no pinning/cache meant MITM could substitute the key freely.
_KC_PUBLIC_KEY_CACHE: dict[str, tuple[str, float]] = {}
_KC_PUBLIC_KEY_TTL_SEC = 300.0
_KC_HTTP_TIMEOUT_SEC = 3.0


def _kc_issuer_url() -> str:
    """Expected `iss` claim — must match what Keycloak embeds in tokens."""
    return f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"


def _kc_public_key_url() -> str:
    """URL for fetching the realm public key (internal service URL when set)."""
    return f"{settings.keycloak_internal_url}/realms/{settings.KEYCLOAK_REALM}"


def _clear_keycloak_public_key_cache() -> None:
    _KC_PUBLIC_KEY_CACHE.clear()


class User(BaseModel):
    id: str
    email: str
    username: str
    roles: list[str]
    tenant_id: str | None = None


def _demo_auth_bypass_enabled(request: Request) -> bool:
    return bool(getattr(settings, "STOA_DISABLE_AUTH", False)) and request.headers.get("X-Demo-Mode", "").lower() == "true"


def _demo_bypass_user(request: Request) -> User:
    user = User(
        id="demo-dev-bypass",
        email="demo-dev-bypass@stoa.local",
        username="demo-dev-bypass",
        roles=["cpi-admin"],
        tenant_id=None,
    )
    bind_request_context(user_id=user.id, tenant_id=user.tenant_id)
    request.state.user = {
        "sub": user.id,
        "email": user.email,
        "name": user.username,
        "tenant_id": user.tenant_id,
    }
    logger.warning(
        "Demo/dev auth bypass accepted",
        path=request.url.path,
        method=request.method,
        environment=settings.ENVIRONMENT,
    )
    return user


async def get_keycloak_public_key() -> str:
    """Fetch Keycloak realm public key, cached in-memory for 5 minutes."""
    url = _kc_public_key_url()
    now = time.monotonic()
    cached = _KC_PUBLIC_KEY_CACHE.get(url)
    if cached is not None and now - cached[1] < _KC_PUBLIC_KEY_TTL_SEC:
        return cached[0]

    async with httpx.AsyncClient(timeout=_KC_HTTP_TIMEOUT_SEC) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    public_key = data.get("public_key")
    if not public_key:
        raise httpx.HTTPError("Keycloak realm endpoint returned no public_key")
    pem = f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"
    _KC_PUBLIC_KEY_CACHE[url] = (pem, now)
    return pem


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """Validate JWT token and return current user.

    Supports service-to-service auth via X-Operator-Key header (ADR-042).
    """
    if _demo_auth_bypass_enabled(request):
        return _demo_bypass_user(request)

    # Service-to-service auth for internal operators (ADR-042)
    operator_key = request.headers.get("X-Operator-Key")
    if operator_key and operator_key in settings.gateway_api_keys_list:
        # CAB-2146: fingerprint the key so the rate-limit bucket is per-operator.
        # Never log or store the raw key — only the sha256[:16] fingerprint.
        fingerprint = hashlib.sha256(operator_key.encode("utf-8")).hexdigest()[:16]
        request.state.operator_fingerprint = fingerprint
        logger.info(
            "Operator authenticated via X-Operator-Key",
            fingerprint=fingerprint,
            client_ip=request.client.host if request.client else None,
            path=request.url.path,
        )
        bind_request_context(user_id="stoa-operator")
        # Store on request.state for audit middleware (CAB-1793)
        request.state.user = {
            "sub": "stoa-operator",
            "email": "",
            "name": "stoa-operator",
            "tenant_id": None,
        }
        return User(
            id="stoa-operator",
            email="",
            username="stoa-operator",
            roles=["cpi-admin"],
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials

    # Debug logging for auth troubleshooting (CAB-330)
    if settings.LOG_DEBUG_AUTH_TOKENS:
        logger.debug(
            "Auth token received",
            scheme=credentials.scheme,
            token_length=len(token),
            token_preview=f"{token[:20]}...{token[-10:]}" if len(token) > 30 else "[short]",
        )

    try:
        public_key = await get_keycloak_public_key()

        # CAB-2082: enforce issuer. Audience is validated manually below to
        # support legacy clients still mapping azp instead of aud.
        # CAB-2094: issuer comes from the PUBLIC URL regardless of where we
        # fetched the public key (which may be the internal SVC URL).
        expected_issuer = _kc_issuer_url()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=expected_issuer,
            options={"verify_aud": False, "verify_iss": True},
        )

        # Debug: log payload structure (not values) for troubleshooting
        if settings.LOG_DEBUG_AUTH_PAYLOAD:
            logger.debug(
                "JWT payload decoded",
                payload_keys=list(payload.keys()),
                has_sub=bool(payload.get("sub")),
                has_email=bool(payload.get("email")),
                has_preferred_username=bool(payload.get("preferred_username")),
                has_realm_access=bool(payload.get("realm_access")),
                has_tenant_id=bool(payload.get("tenant_id")),
                aud=payload.get("aud"),
                iss=payload.get("iss"),
                exp=payload.get("exp"),
                iat=payload.get("iat"),
                typ=payload.get("typ"),
                azp=payload.get("azp"),
            )

        # Verify audience - tokens should be intended for this API (Resource Server)
        # OAuth2 Best Practice:
        # - `aud` = the API that consumes the token (control-plane-api)
        # - `azp` = the client that requested the token (control-plane-ui, stoa-portal, etc.)
        #
        # All clients should have Audience Mappers configured in Keycloak to include
        # 'control-plane-api' in the 'aud' claim. See: configure-keycloak-audience.sh
        #
        # Accepted audiences:
        # - control-plane-api: Primary API audience (from Audience Mapper)
        # - account: Keycloak account management tokens
        # - control-plane-ui, stoa-portal, stoa-mcp-gateway: Legacy support for
        #   tokens issued before the Audience Mapper was deployed on that
        #   client. CAB-2153 adds `stoa-mcp-gateway` so the MCP migration
        #   window (Mode B per CAB-2151) works end-to-end.
        #   TODO: Remove these once all users have refreshed their tokens.
        valid_audiences = {
            settings.KEYCLOAK_CLIENT_ID,
            "account",
            "control-plane-ui",
            "stoa-portal",
            "stoa-mcp-gateway",
        }
        token_aud = payload.get("aud", [])
        if isinstance(token_aud, str):
            token_aud = [token_aud]
        if not any(aud in valid_audiences for aud in token_aud):
            logger.warning(
                "JWT audience validation failed",
                token_aud=token_aud,
                valid_audiences=list(valid_audiences),
                azp=payload.get("azp"),
                hint="Ensure Audience Mapper is configured in Keycloak for this client",
            )
            raise JWTError(f"Invalid audience: {token_aud}. Expected: {list(valid_audiences)}")

        # Deprecation warning for legacy audiences (control-plane-ui, stoa-portal)
        # These clients should configure Audience Mappers in Keycloak to include
        # 'control-plane-api' in the 'aud' claim. Legacy support will be removed
        # after all clients have migrated (target: Q2 2026).
        legacy_audiences = {"control-plane-ui", "stoa-portal", "stoa-mcp-gateway"}
        primary_audience = {settings.KEYCLOAK_CLIENT_ID}
        if any(aud in legacy_audiences for aud in token_aud) and not any(aud in primary_audience for aud in token_aud):
            logger.warning(
                "DEPRECATION: Token uses legacy audience, migrate to Audience Mapper",
                token_aud=token_aud,
                azp=payload.get("azp"),
                expected_audience=settings.KEYCLOAK_CLIENT_ID,
                migration_deadline="Q2 2026",
            )

        # --- Sender-Constrained Token Validation (CAB-438) ---
        request_headers = {k.lower(): v for k, v in request.headers.items()}
        sc_result = validate_sender_constrained_token(
            token_payload=payload,
            access_token=token,
            headers=request_headers,
            http_method=request.method,
            http_uri=str(request.url),
        )
        if not sc_result.valid:
            logger.warning(
                "Sender-constrained validation failed",
                mode=sc_result.mode,
                error=sc_result.error,
                azp=payload.get("azp"),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=sc_result.error,
            )

        email = payload.get("email", "")
        username = payload.get("preferred_username", "")
        # Lazy import to avoid circular: dependencies -> rbac -> dependencies
        from .rbac import normalize_roles

        roles = normalize_roles(payload.get("realm_access", {}).get("roles", []))
        # Handle tenant_id as either string or list (from group membership mapper)
        raw_tenant_id = payload.get("tenant_id")
        tenant_id = (raw_tenant_id[0] if raw_tenant_id else None) if isinstance(raw_tenant_id, list) else raw_tenant_id

        # Get user ID from 'sub' claim (Keycloak UUID)
        # The 'sub' claim is mandatory in OIDC access tokens — if missing, the
        # Keycloak client scope or token type is misconfigured (CAB-1669).
        user_id = payload.get("sub")
        if not user_id:
            # Fallback: use email or preferred_username as user identifier.
            # This is a degraded state — owner_id will be set to email instead
            # of UUID, which breaks if the user changes their email.
            user_id = email or username
            if user_id:
                logger.warning(
                    "JWT token missing 'sub' claim — using fallback identifier. "
                    "This causes owner_id to use email instead of UUID. "
                    "Fix: verify Keycloak client scopes include the 'sub' claim "
                    "(built-in 'Subject (sub)' mapper in openid-connect scope).",
                    fallback_id=user_id,
                    payload_keys=list(payload.keys()),
                    typ=payload.get("typ"),
                    azp=payload.get("azp"),
                    iss=payload.get("iss"),
                )

        # Log authentication result
        logger.info(
            "User authenticated",
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            tenant_id=tenant_id,
        )

        # Bind user context for all subsequent logs in this request
        bind_request_context(user_id=user_id, tenant_id=tenant_id)

        # Store user info on request.state for audit middleware (CAB-1793)
        request.state.user = {
            "sub": user_id,
            "email": email,
            "name": username,
            "tenant_id": tenant_id,
        }

        if not user_id:
            logger.error(
                "JWT token missing user ID - no 'sub', email, or preferred_username",
                payload_keys=list(payload.keys()),
                typ=payload.get("typ"),
                azp=payload.get("azp"),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )

        return User(
            id=user_id,
            email=email,
            username=username,
            roles=roles,
            tenant_id=tenant_id,
        )

    except JWTError as e:
        logger.error(
            "JWT validation failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e!s}")
    except httpx.HTTPError as e:
        logger.error(
            "Failed to fetch Keycloak public key",
            error=str(e),
            keycloak_url=settings.keycloak_internal_url,
            realm=settings.KEYCLOAK_REALM,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
