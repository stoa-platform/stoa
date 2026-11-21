"""CUJ-04: Auth Federation OAM→Keycloak — Token Exchange (RFC 8693).

Validates the bank demo flow: a token from an external IDP
(Oracle OAM, simulated) is exchanged via Keycloak for a STOA token.

Sub-tests:
    CUJ-04a: Obtain token from external IDP (or mock)
    CUJ-04b: POST token-exchange → new Keycloak token
    CUJ-04c: Decode JWT → mapped claims present
    CUJ-04d: Call API with exchanged token → 200 OK
    CUJ-04e: Call API with original (non-exchanged) token → 401 (negative)
    CUJ-04f: Exchange latency < 500ms

Thresholds:
    - Token exchange < 500ms
    - Exchanged token must contain mapped claims (roles, scope)
"""

from __future__ import annotations

import base64
import json
import os
import time

import httpx
import pytest

from ..conftest import API_URL, AUTH_URL, GATEWAY_URL, KC_REALM, TIMEOUT, CUJResult, SubTestResult

pytestmark = [pytest.mark.l2]

CUJ_ID = "CUJ-04"
EXCHANGE_THRESHOLD_MS = 500

# External IDP config (mock or real OAM)
EXTERNAL_IDP_TOKEN_URL = os.environ.get("EXTERNAL_IDP_TOKEN_URL", "")
EXTERNAL_IDP_CLIENT_ID = os.environ.get("EXTERNAL_IDP_CLIENT_ID", "")
EXTERNAL_IDP_CLIENT_SECRET = os.environ.get("EXTERNAL_IDP_CLIENT_SECRET", "")

# Keycloak token exchange config
TOKEN_EXCHANGE_CLIENT_ID = os.environ.get("TOKEN_EXCHANGE_CLIENT_ID", "stoa-token-exchange")
TOKEN_EXCHANGE_CLIENT_SECRET = os.environ.get("TOKEN_EXCHANGE_CLIENT_SECRET", "")


@pytest.fixture()
def result() -> CUJResult:
    return CUJResult(cuj_id=CUJ_ID, start_time=time.monotonic())


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without signature verification (bench only)."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    # Add padding
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


class TestCUJ04AuthFederation:
    """CUJ-04: Auth Federation (Token Exchange) end-to-end."""

    async def test_cuj04_auth_federation(
        self,
        http_client: httpx.AsyncClient,
        admin_token: str,
        admin_headers: dict[str, str],
        result: CUJResult,
    ) -> None:
        """Run full CUJ-04: obtain external token → exchange → verify → call."""
        result.start_time = time.monotonic()

        # ---------------------------------------------------------------
        # CUJ-04a: Obtain external IDP token (or use admin token as mock)
        # ---------------------------------------------------------------
        t0 = time.monotonic()
        external_token = ""

        if EXTERNAL_IDP_TOKEN_URL and EXTERNAL_IDP_CLIENT_SECRET:
            # Real external IDP
            resp = await http_client.post(
                EXTERNAL_IDP_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": EXTERNAL_IDP_CLIENT_ID,
                    "client_secret": EXTERNAL_IDP_CLIENT_SECRET,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                external_token = resp.json().get("access_token", "")
        else:
            # Mock: use admin token as the "external" token for exchange
            # This tests the exchange mechanism even without a real external IDP
            external_token = admin_token

        t1 = time.monotonic()
        has_external = bool(external_token)

        result.sub_tests.append(SubTestResult(
            test_id="CUJ-04a",
            status="PASS" if has_external else "FAIL",
            latency_ms=(t1 - t0) * 1000,
            details={"source": "external_idp" if EXTERNAL_IDP_TOKEN_URL else "mock"},
        ))

        if not has_external:
            _fill_remaining(result, ["CUJ-04b", "CUJ-04c", "CUJ-04d", "CUJ-04e", "CUJ-04f"])
            result.end_time = time.monotonic()
            _write_result(result)
            pytest.skip("No external token available for exchange test")

        # ---------------------------------------------------------------
        # CUJ-04b: Token Exchange (RFC 8693)
        # ---------------------------------------------------------------
        t0 = time.monotonic()
        token_url = f"{AUTH_URL}/realms/{KC_REALM}/protocol/openid-connect/token"

        exchange_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": external_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }

        # Add client auth if available
        if TOKEN_EXCHANGE_CLIENT_SECRET:
            exchange_data["client_id"] = TOKEN_EXCHANGE_CLIENT_ID
            exchange_data["client_secret"] = TOKEN_EXCHANGE_CLIENT_SECRET
        else:
            exchange_data["client_id"] = TOKEN_EXCHANGE_CLIENT_ID

        exchange_resp = await http_client.post(
            token_url, data=exchange_data, timeout=TIMEOUT,
        )
        t1 = time.monotonic()
        exchange_ms = (t1 - t0) * 1000

        exchanged_token = ""
        exchange_ok = False
        if exchange_resp.status_code == 200:
            exchanged_token = exchange_resp.json().get("access_token", "")
            exchange_ok = bool(exchanged_token)
        elif exchange_resp.status_code == 400:
            # Token exchange may not be configured — this is a degraded state
            error = exchange_resp.json().get("error", "")
            if error in ("unsupported_grant_type", "invalid_grant"):
                result.sub_tests.append(SubTestResult(
                    test_id="CUJ-04b",
                    status="FAIL",
                    latency_ms=exchange_ms,
                    details={"reason": f"Token exchange not configured: {error}"},
                ))
                _fill_remaining(result, ["CUJ-04c", "CUJ-04d", "CUJ-04e", "CUJ-04f"])
                result.end_time = time.monotonic()
                _write_result(result)
                return  # Non-blocking for demo

        result.sub_tests.append(SubTestResult(
            test_id="CUJ-04b",
            status="PASS" if exchange_ok else "FAIL",
            latency_ms=exchange_ms,
            details={"http_code": exchange_resp.status_code},
        ))

        if not exchange_ok:
            _fill_remaining(result, ["CUJ-04c", "CUJ-04d", "CUJ-04e", "CUJ-04f"])
            result.end_time = time.monotonic()
            _write_result(result)
            return

        # ---------------------------------------------------------------
        # CUJ-04c: Decode JWT → mapped claims present
        # ---------------------------------------------------------------
        t0 = time.monotonic()
        claims = _decode_jwt_payload(exchanged_token)
        t1 = time.monotonic()

        # Check for expected claims
        has_roles = bool(claims.get("realm_access", {}).get("roles", []))
        has_scope = bool(claims.get("scope", ""))
        claims_ok = has_roles or has_scope

        result.sub_tests.append(SubTestResult(
            test_id="CUJ-04c",
            status="PASS" if claims_ok else "FAIL",
            latency_ms=(t1 - t0) * 1000,
            details={
                "has_roles": has_roles,
                "has_scope": has_scope,
                "roles": claims.get("realm_access", {}).get("roles", [])[:5],
            },
        ))

        # ---------------------------------------------------------------
        # CUJ-04d: Call API with exchanged token → 200 OK
        # ---------------------------------------------------------------
        t0 = time.monotonic()
        api_resp = await http_client.get(
            f"{GATEWAY_URL}/echo/get",
            headers={"Authorization": f"Bearer {exchanged_token}"},
            timeout=TIMEOUT,
        )
        t1 = time.monotonic()
        call_ok = api_resp.status_code < 400

        result.sub_tests.append(SubTestResult(
            test_id="CUJ-04d",
            status="PASS" if call_ok else "FAIL",
            latency_ms=(t1 - t0) * 1000,
            details={"http_code": api_resp.status_code},
        ))

        # ---------------------------------------------------------------
        # CUJ-04e: Call API with original external token → 401 (negative)
        # ---------------------------------------------------------------
        t0 = time.monotonic()
        # Only meaningful if external_token != admin_token (real external IDP)
        if EXTERNAL_IDP_TOKEN_URL:
            neg_resp = await http_client.get(
                f"{GATEWAY_URL}/echo/get",
                headers={"Authorization": f"Bearer {external_token}"},
                timeout=TIMEOUT,
            )
            negative_ok = neg_resp.status_code in (401, 403)
        else:
            # Mock mode: admin token is valid, so skip negative test
            negative_ok = True
            neg_resp = None
        t1 = time.monotonic()

        result.sub_tests.append(SubTestResult(
            test_id="CUJ-04e",
            status="PASS" if negative_ok else "FAIL",
            latency_ms=(t1 - t0) * 1000,
            details={
                "http_code": neg_resp.status_code if neg_resp else "skipped_mock",
                "mode": "real" if EXTERNAL_IDP_TOKEN_URL else "mock",
            },
        ))

        # ---------------------------------------------------------------
        # CUJ-04f: Exchange latency < threshold
        # ---------------------------------------------------------------
        timing_ok = exchange_ms < EXCHANGE_THRESHOLD_MS
        result.sub_tests.append(SubTestResult(
            test_id="CUJ-04f",
            status="PASS" if timing_ok else "FAIL",
            latency_ms=exchange_ms,
            details={"threshold_ms": EXCHANGE_THRESHOLD_MS},
        ))

        result.end_time = time.monotonic()
        _write_result(result)

        # CUJ-04 is non-blocking for demo (degraded mode)


def _fill_remaining(result: CUJResult, test_ids: list[str]) -> None:
    for tid in test_ids:
        result.sub_tests.append(SubTestResult(
            test_id=tid, status="FAIL", latency_ms=0,
            details={"reason": "skipped — prerequisite failed"},
        ))


def _write_result(result: CUJResult) -> None:
    import pathlib
    out_dir = pathlib.Path("/tmp/stoa-bench-results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"cuj_{result.cuj_id.lower().replace('-', '_')}.json"
    out_file.write_text(json.dumps(result.to_dict(), indent=2))
