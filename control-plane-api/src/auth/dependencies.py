# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""FastAPI authentication dependencies.

CAB-330: Enhanced debug logging for authentication troubleshooting.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import List, Optional
import httpx

from ..config import settings
from ..logging_config import get_logger, bind_request_context

logger = get_logger(__name__)
security = HTTPBearer(auto_error=True)

class User(BaseModel):
    id: str
    email: str
    username: str
    roles: List[str]
    tenant_id: Optional[str] = None

async def get_keycloak_public_key():
    """Fetch Keycloak realm public key"""
    url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()
        public_key = data.get("public_key")
        return f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Validate JWT token and return current user."""
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
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False}
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

        email = payload.get("email", "")
        username = payload.get("preferred_username", "")
        roles = payload.get("realm_access", {}).get("roles", [])
        # Handle tenant_id as either string or list (from group membership mapper)
        raw_tenant_id = payload.get("tenant_id")
        if isinstance(raw_tenant_id, list):
            tenant_id = raw_tenant_id[0] if raw_tenant_id else None
        else:
            tenant_id = raw_tenant_id

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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except httpx.HTTPError as e:
        logger.error(
            "Failed to fetch Keycloak public key",
            error=str(e),
            keycloak_url=settings.KEYCLOAK_URL,
            realm=settings.KEYCLOAK_REALM,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )
