"""FastAPI authentication dependencies"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import List, Optional
import httpx

from ..config import settings

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
    """Validate JWT token and return current user"""
    print(f"[AUTH] Received credentials: scheme={credentials.scheme}", flush=True)
    token = credentials.credentials
    print(f"[AUTH] Token length: {len(token)}", flush=True)

    try:
        public_key = await get_keycloak_public_key()
        # Decode without audience validation first
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        # Manually verify audience - accept tokens from both UI and API clients
        valid_audiences = {settings.KEYCLOAK_CLIENT_ID, "control-plane-ui", "account"}
        token_aud = payload.get("aud", [])
        if isinstance(token_aud, str):
            token_aud = [token_aud]
        if not any(aud in valid_audiences for aud in token_aud):
            raise JWTError(f"Invalid audience: {token_aud}")

        user_id = payload.get("sub")
        email = payload.get("email", "")
        username = payload.get("preferred_username", "")
        roles = payload.get("realm_access", {}).get("roles", [])
        tenant_id = payload.get("tenant_id")

        print(f"[AUTH] user={username}, email={email}, roles={roles}", flush=True)

        if not user_id:
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
        print(f"[AUTH ERROR] JWT validation error: {str(e)}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
