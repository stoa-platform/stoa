"""FastAPI authentication dependencies.

CAB-330: Enhanced debug logging for authentication troubleshooting.
"""

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from ..config import settings
from ..logging_config import bind_request_context, get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


class User(BaseModel):
    id: str
    email: str
    username: str
    roles: list[str]
    tenant_id: str | None = None


async def get_keycloak_public_key():
    """Fetch Keycloak realm public key"""
    url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()
        public_key = data.get("public_key")
        return f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """Validate JWT token and return current user.

    Supports service-to-service auth via X-Operator-Key header (ADR-042).
    """
    # Service-to-service auth for internal operators (ADR-042)
    operator_key = request.headers.get("X-Operator-Key")
    if operator_key and operator_key in settings.gateway_api_keys_list:
        logger.info("Operator authenticated via X-Operator-Key")
        bind_request_context(user_id="stoa-operator")
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

        # Decode without audience validation first
        payload = jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})

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
        # - control-plane-ui, stoa-portal: Legacy support for tokens without Audience Mapper
        #   TODO: Remove these once all users have refreshed their tokens
        valid_audiences = {settings.KEYCLOAK_CLIENT_ID, "account", "control-plane-ui", "stoa-portal"}
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
        legacy_audiences = {"control-plane-ui", "stoa-portal"}
        primary_audience = {settings.KEYCLOAK_CLIENT_ID}
        if any(aud in legacy_audiences for aud in token_aud) and not any(aud in primary_audience for aud in token_aud):
            logger.warning(
                "DEPRECATION: Token uses legacy audience, migrate to Audience Mapper",
                token_aud=token_aud,
                azp=payload.get("azp"),
                expected_audience=settings.KEYCLOAK_CLIENT_ID,
                migration_deadline="Q2 2026",
            )

        email = payload.get("email", "")
        username = payload.get("preferred_username", "")
        roles = payload.get("realm_access", {}).get("roles", [])
        # Handle tenant_id as either string or list (from group membership mapper)
        raw_tenant_id = payload.get("tenant_id")
        tenant_id = (raw_tenant_id[0] if raw_tenant_id else None) if isinstance(raw_tenant_id, list) else raw_tenant_id

        # Get user ID from 'sub' claim, with fallback to email or username
        # Some Keycloak configurations may not include 'sub' in certain token types
        user_id = payload.get("sub")
        if not user_id:
            # Fallback: use email or preferred_username as user identifier
            user_id = email or username
            if user_id:
                logger.warning(
                    "JWT token missing 'sub' claim, using fallback identifier",
                    fallback_id=user_id,
                    payload_keys=list(payload.keys()),
                    typ=payload.get("typ"),
                    azp=payload.get("azp"),
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

        if not user_id:
            logger.error(
                "JWT token missing user ID - no 'sub', email, or preferred_username",
                payload_keys=list(payload.keys()),
                typ=payload.get("typ"),
                azp=payload.get("azp"),
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing user ID")

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
            keycloak_url=settings.KEYCLOAK_URL,
            realm=settings.KEYCLOAK_REALM,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service unavailable"
        )
