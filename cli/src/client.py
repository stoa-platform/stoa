"""HTTP client for the STOA Control-Plane API."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .auth import refresh_token
from .config import Credentials, StoaConfig, load_config, load_credentials
from .models import APIResponse, HealthResponse, TenantResponse


class StoaClient:
    """Thin wrapper around httpx that handles auth headers and token refresh."""

    def __init__(
        self,
        config: StoaConfig | None = None,
        credentials: Credentials | None = None,
    ) -> None:
        self.config = config or load_config()
        self.credentials = credentials or load_credentials()

    def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if not self.credentials.access_token:
            raise RuntimeError("Not authenticated. Run 'stoa login' first.")

        if time.time() >= self.credentials.expires_at - 30:
            self.credentials = refresh_token(self.config, self.credentials)

        return self.credentials.access_token

    def _headers(self) -> dict[str, str]:
        token = self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.config.server}{path}"

    def _tenant_id(self) -> str:
        """Resolve tenant_id from config or token claims."""
        if self.config.tenant_id:
            return self.config.tenant_id
        tid = self.credentials.claims.get("tenant_id")
        if isinstance(tid, list):
            tid = tid[0] if tid else None
        if tid:
            return str(tid)
        # Fallback: fetch tenants and pick the first one
        tenants = self.list_tenants()
        if not tenants:
            raise RuntimeError("No tenant found. Set tenant_id in ~/.stoa/config.yaml")
        return tenants[0].id

    # ── Health ──────────────────────────────────────────────

    def health(self) -> HealthResponse:
        with httpx.Client(timeout=10) as c:
            resp = c.get(self._url("/health"))
        resp.raise_for_status()
        return HealthResponse.model_validate(resp.json())

    # ── Tenants ─────────────────────────────────────────────

    def list_tenants(self) -> list[TenantResponse]:
        with httpx.Client(timeout=30) as c:
            resp = c.get(self._url("/v1/tenants"), headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return [TenantResponse.model_validate(t) for t in data]
        return [TenantResponse.model_validate(t) for t in data.get("tenants", data)]

    # ── APIs ────────────────────────────────────────────────

    def list_apis(self, tenant_id: str | None = None) -> list[APIResponse]:
        tid = tenant_id or self._tenant_id()
        with httpx.Client(timeout=30) as c:
            resp = c.get(
                self._url(f"/v1/tenants/{tid}/apis"),
                headers=self._headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return [APIResponse.model_validate(a) for a in data]
        return [APIResponse.model_validate(a) for a in data.get("apis", data)]

    def get_api(
        self, api_name: str, tenant_id: str | None = None
    ) -> APIResponse:
        apis = self.list_apis(tenant_id)
        for api in apis:
            if api.name == api_name or api.id == api_name:
                return api
        raise RuntimeError(f"API '{api_name}' not found.")

    def create_api(
        self, payload: dict[str, Any], tenant_id: str | None = None
    ) -> dict[str, Any]:
        tid = tenant_id or self._tenant_id()
        with httpx.Client(timeout=30) as c:
            resp = c.post(
                self._url(f"/v1/tenants/{tid}/apis"),
                headers=self._headers(),
                json=payload,
            )
        resp.raise_for_status()
        return resp.json()

    def update_api(
        self,
        api_id: str,
        payload: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        tid = tenant_id or self._tenant_id()
        with httpx.Client(timeout=30) as c:
            resp = c.put(
                self._url(f"/v1/tenants/{tid}/apis/{api_id}"),
                headers=self._headers(),
                json=payload,
            )
        resp.raise_for_status()
        return resp.json()
