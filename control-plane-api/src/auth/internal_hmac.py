import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request, status

from src.config import settings

_AUTH_SCHEME = "HMAC-SHA256 "
_REPLAY_WINDOW_SECONDS = 300


def _shared_secret() -> str:
    secret = settings.INTERNAL_AUDIT_HMAC_SECRET
    if hasattr(secret, "get_secret_value"):
        return str(secret.get_secret_value())
    return str(secret)


async def verify_internal_hmac(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    x_timestamp: str | None = Header(None, alias="X-Timestamp"),
) -> None:
    if not authorization or not authorization.startswith(_AUTH_SCHEME) or not x_timestamp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal signature")

    try:
        timestamp = int(x_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal signature") from exc

    if abs(int(time.time()) - timestamp) > _REPLAY_WINDOW_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal signature")

    body = await request.body()
    body_hash = hashlib.sha256(body).hexdigest()
    signing_string = f"{timestamp}\n{request.method.upper()}\n{request.url.path}\n{body_hash}"
    expected = hmac.new(_shared_secret().encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256).hexdigest()
    supplied = authorization.removeprefix(_AUTH_SCHEME).strip()

    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal signature")
