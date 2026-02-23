"""AWS API Gateway Adapter.

Implements GatewayAdapterInterface for AWS API Gateway REST APIs.
Uses the AWS API Gateway REST API v1 via httpx (NOT boto3, for consistency
with other STOA adapters).

Auth: AWS SigV4 signing with access_key + secret_key + region.

API reference:
  https://docs.aws.amazon.com/apigateway/latest/api/API_Operations.html
"""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)


def _sign_v4(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str,
    service: str = "apigateway",
) -> dict[str, str]:
    """Produce AWS Signature Version 4 headers.

    Minimal implementation covering the signing steps needed for
    API Gateway management API calls. Returns a dict of headers to
    merge into the request.
    """
    now = datetime.now(tz=UTC)
    datestamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    parsed = urlparse(url)
    host = parsed.hostname or ""
    canonical_uri = quote(parsed.path or "/", safe="/")
    canonical_querystring = parsed.query or ""

    payload_hash = hashlib.sha256(body).hexdigest()

    signed_headers_list = sorted(["host", "x-amz-date", "x-amz-content-sha256"])
    signed_headers_str = ";".join(signed_headers_list)

    header_map = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    canonical_headers = "".join(f"{k}:{header_map[k]}\n" for k in signed_headers_list)

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers_str,
            payload_hash,
        ]
    )

    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    def _hmac_sha256(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _hmac_sha256(
        _hmac_sha256(
            _hmac_sha256(
                _hmac_sha256(f"AWS4{secret_key}".encode(), datestamp),
                region,
            ),
            service,
        ),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }


class AwsApiGatewayAdapter(GatewayAdapterInterface):
    """Adapter for AWS API Gateway (REST APIs).

    Config dict keys:
        - region: AWS region (e.g. "eu-west-1")
        - auth_config.access_key: AWS access key ID
        - auth_config.secret_key: AWS secret access key
        - base_url (optional): override endpoint (for localstack, etc.)
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config=config)
        cfg = config or {}
        self._region = cfg.get("region", "us-east-1")
        auth_config = cfg.get("auth_config", {})
        self._access_key = auth_config.get("access_key", "") if isinstance(auth_config, dict) else ""
        self._secret_key = auth_config.get("secret_key", "") if isinstance(auth_config, dict) else ""
        default_base = f"https://apigateway.{self._region}.amazonaws.com"
        self._base_url = cfg.get("base_url", default_base)
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Create persistent HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
    ) -> httpx.Response:
        """Make a SigV4-signed request to the AWS API Gateway management API."""
        client = self._client or httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        close_after = self._client is None

        url = f"{self._base_url}{path}"
        body = b""
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if json_body is not None:
            body = json.dumps(json_body).encode()

        if self._access_key and self._secret_key:
            sig_headers = _sign_v4(
                method=method,
                url=url,
                headers=headers,
                body=body,
                access_key=self._access_key,
                secret_key=self._secret_key,
                region=self._region,
            )
            headers.update(sig_headers)

        try:
            return await client.request(method, path, content=body, headers=headers)
        finally:
            if close_after:
                await client.aclose()

    # --- Lifecycle ---

    async def health_check(self) -> AdapterResult:
        """Check AWS API Gateway connectivity by listing REST APIs (limit=1)."""
        try:
            resp = await self._request("GET", "/restapis?limit=1")
            if resp.status_code == 200:
                return AdapterResult(success=True, data={"status": "healthy", "region": self._region})
            return AdapterResult(
                success=False,
                error=f"AWS API Gateway health check failed: HTTP {resp.status_code}",
            )
        except httpx.HTTPError as e:
            return AdapterResult(success=False, error=f"Connection error: {e}")

    # --- APIs ---

    async def sync_api(
        self,
        api_spec: dict,
        tenant_id: str,
        auth_token: str | None = None,
    ) -> AdapterResult:
        """Create or update a REST API in AWS API Gateway."""
        try:
            aws_api = mappers.map_api_spec_to_aws(api_spec, tenant_id)
            api_name = aws_api["name"]

            # Search for existing API by name
            existing_id = await self._find_api_by_name(api_name)

            if existing_id:
                # Update existing API
                logger.info("REST API %s exists (%s), updating", api_name, existing_id)
                patch_ops = [
                    {"op": "replace", "path": "/description", "value": aws_api.get("description", "")},
                ]
                resp = await self._request(
                    "PATCH", f"/restapis/{existing_id}", json_body={"patchOperations": patch_ops}
                )
            else:
                # Create new API
                logger.info("Creating new REST API: %s", api_name)
                resp = await self._request("POST", "/restapis", json_body=aws_api)

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("id", existing_id or ""),
                    data=data,
                )
            return AdapterResult(
                success=False,
                error=f"Failed to sync API: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a REST API from AWS API Gateway."""
        try:
            resp = await self._request("DELETE", f"/restapis/{api_id}")
            if resp.status_code in (200, 202, 204, 404):
                return AdapterResult(success=True, resource_id=api_id)
            return AdapterResult(
                success=False,
                error=f"Failed to delete API: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        """List all REST APIs from AWS API Gateway."""
        try:
            resp = await self._request("GET", "/restapis")
            if resp.status_code != 200:
                logger.warning("Failed to list APIs: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("items", data.get("item", []))
            # Filter STOA-managed APIs
            stoa_apis = []
            for item in items:
                tags = item.get("tags", {})
                if tags.get("stoa-managed") == "true":
                    stoa_apis.append(mappers.map_aws_api_to_cp(item))
            return stoa_apis
        except Exception as e:
            logger.warning("Failed to list APIs: %s", e)
            return []

    # --- Policies (Usage Plans) ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create or update a usage plan in AWS API Gateway."""
        try:
            tenant_id = policy_spec.get("tenant_id", "default")
            plan = mappers.map_policy_to_aws_usage_plan(policy_spec, tenant_id)
            plan_name = plan["name"]

            # Search for existing plan by name
            existing_id = await self._find_usage_plan_by_name(plan_name)

            if existing_id:
                logger.info("Usage plan %s exists (%s), updating", plan_name, existing_id)
                patch_ops = []
                if "throttle" in plan:
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": "/throttle/rateLimit",
                            "value": str(plan["throttle"]["rateLimit"]),
                        }
                    )
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": "/throttle/burstLimit",
                            "value": str(plan["throttle"]["burstLimit"]),
                        }
                    )
                if "description" in plan:
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": "/description",
                            "value": plan.get("description", ""),
                        }
                    )
                resp = await self._request(
                    "PATCH",
                    f"/usageplans/{existing_id}",
                    json_body={"patchOperations": patch_ops},
                )
            else:
                logger.info("Creating new usage plan: %s", plan_name)
                resp = await self._request("POST", "/usageplans", json_body=plan)

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("id", existing_id or ""),
                    data=data,
                )
            return AdapterResult(
                success=False,
                error=f"Failed to upsert usage plan: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a usage plan from AWS API Gateway."""
        try:
            resp = await self._request("DELETE", f"/usageplans/{policy_id}")
            if resp.status_code in (200, 202, 204, 404):
                return AdapterResult(success=True, resource_id=policy_id)
            return AdapterResult(
                success=False,
                error=f"Failed to delete usage plan: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        """List usage plans from AWS API Gateway (STOA-managed only)."""
        try:
            resp = await self._request("GET", "/usageplans")
            if resp.status_code != 200:
                logger.warning("Failed to list usage plans: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("items", data.get("item", []))
            stoa_plans = []
            for item in items:
                tags = item.get("tags", {})
                if tags.get("stoa-managed") == "true":
                    stoa_plans.append(mappers.map_aws_usage_plan_to_policy(item))
            return stoa_plans
        except Exception as e:
            logger.warning("Failed to list usage plans: %s", e)
            return []

    # --- Applications (API Keys) ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create an API key and optionally associate it with a usage plan."""
        try:
            tenant_id = app_spec.get("tenant_id", "default")
            key_payload = mappers.map_app_spec_to_aws_api_key(app_spec, tenant_id)

            resp = await self._request("POST", "/apikeys", json_body=key_payload)
            if resp.status_code not in (200, 201):
                return AdapterResult(
                    success=False,
                    error=f"Failed to create API key: HTTP {resp.status_code} - {resp.text}",
                )

            key_data = resp.json()
            key_id = key_data.get("id", "")

            # Associate with usage plan if specified
            usage_plan_id = app_spec.get("usage_plan_id")
            if usage_plan_id and key_id:
                assoc_resp = await self._request(
                    "POST",
                    f"/usageplans/{usage_plan_id}/keys",
                    json_body={"keyId": key_id, "keyType": "API_KEY"},
                )
                if assoc_resp.status_code not in (200, 201):
                    logger.warning(
                        "API key %s created but failed to associate with usage plan %s: HTTP %d",
                        key_id,
                        usage_plan_id,
                        assoc_resp.status_code,
                    )

            return AdapterResult(
                success=True,
                resource_id=key_id,
                data=key_data,
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API key from AWS API Gateway."""
        try:
            resp = await self._request("DELETE", f"/apikeys/{app_id}")
            if resp.status_code in (200, 202, 204, 404):
                return AdapterResult(success=True, resource_id=app_id)
            return AdapterResult(
                success=False,
                error=f"Failed to delete API key: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        """List API keys from AWS API Gateway (STOA-managed only)."""
        try:
            resp = await self._request("GET", "/apikeys?includeValues=true")
            if resp.status_code != 200:
                logger.warning("Failed to list API keys: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("items", data.get("item", []))
            stoa_keys = []
            for item in items:
                tags = item.get("tags", {})
                if tags.get("stoa-managed") == "true":
                    stoa_keys.append(mappers.map_aws_api_key_to_cp(item))
            return stoa_keys
        except Exception as e:
            logger.warning("Failed to list API keys: %s", e)
            return []

    # --- Not supported by AWS API Gateway adapter ---

    async def upsert_auth_server(self, auth_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by AWS API Gateway")

    async def upsert_strategy(self, strategy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by AWS API Gateway")

    async def upsert_scope(self, scope_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by AWS API Gateway")

    async def upsert_alias(self, alias_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by AWS API Gateway")

    async def apply_config(self, config_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by AWS API Gateway")

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        """Not supported."""
        return b""

    async def deploy_contract(self, contract_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by AWS API Gateway")

    # --- Internal helpers ---

    async def _find_api_by_name(self, name: str) -> str | None:
        """Search for a REST API by name, return its ID or None."""
        try:
            resp = await self._request("GET", "/restapis")
            if resp.status_code != 200:
                return None
            data = resp.json()
            for item in data.get("items", data.get("item", [])):
                if item.get("name") == name:
                    return item.get("id")
        except Exception:
            pass
        return None

    async def _find_usage_plan_by_name(self, name: str) -> str | None:
        """Search for a usage plan by name, return its ID or None."""
        try:
            resp = await self._request("GET", "/usageplans")
            if resp.status_code != 200:
                return None
            data = resp.json()
            for item in data.get("items", data.get("item", [])):
                if item.get("name") == name:
                    return item.get("id")
        except Exception:
            pass
        return None
