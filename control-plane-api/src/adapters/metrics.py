"""Instrumented Adapter Wrapper — Prometheus metrics around every adapter call.

Wraps any GatewayAdapterInterface implementation to transparently record
operation counts, durations, and health check metrics. Applied at
AdapterRegistry.create() so all callers get instrumented adapters.

Metrics:
    stoa_adapter_operations_total      Counter(gateway_type, operation, status)
    stoa_adapter_operation_duration     Histogram(gateway_type, operation)
    stoa_adapter_health_checks_total    Counter(gateway_type, status)
    stoa_adapter_health_check_latency   Histogram(gateway_type)
"""

import logging
import time

from prometheus_client import Counter, Histogram

from .gateway_adapter_interface import AdapterResult, GatewayAdapterInterface

logger = logging.getLogger(__name__)

# Metrics prefix consistent with middleware/metrics.py
ADAPTER_PREFIX = "stoa_adapter"

# --- Prometheus Metrics ---

ADAPTER_OPERATIONS_TOTAL = Counter(
    f"{ADAPTER_PREFIX}_operations_total",
    "Total adapter operations",
    ["gateway_type", "operation", "status"],
)

ADAPTER_OPERATION_DURATION = Histogram(
    f"{ADAPTER_PREFIX}_operation_duration_seconds",
    "Adapter operation duration in seconds",
    ["gateway_type", "operation"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

ADAPTER_HEALTH_CHECKS_TOTAL = Counter(
    f"{ADAPTER_PREFIX}_health_checks_total",
    "Total adapter health checks",
    ["gateway_type", "status"],
)

ADAPTER_HEALTH_CHECK_LATENCY = Histogram(
    f"{ADAPTER_PREFIX}_health_check_latency_seconds",
    "Adapter health check latency in seconds",
    ["gateway_type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# All interface methods that return AdapterResult
_ADAPTER_RESULT_METHODS = frozenset(
    {
        "health_check",
        "sync_api",
        "delete_api",
        "upsert_policy",
        "delete_policy",
        "provision_application",
        "deprovision_application",
        "upsert_auth_server",
        "upsert_strategy",
        "upsert_scope",
        "upsert_alias",
        "apply_config",
        "deploy_contract",
    }
)

# Methods that return list[dict]
_ADAPTER_LIST_METHODS = frozenset(
    {
        "list_apis",
        "list_policies",
        "list_applications",
    }
)

# Methods that return bytes
_ADAPTER_BYTES_METHODS = frozenset(
    {
        "export_archive",
    }
)

# Methods that return None
_ADAPTER_VOID_METHODS = frozenset(
    {
        "connect",
        "disconnect",
    }
)

# All instrumented methods
_ALL_INSTRUMENTED = _ADAPTER_RESULT_METHODS | _ADAPTER_LIST_METHODS | _ADAPTER_BYTES_METHODS | _ADAPTER_VOID_METHODS


class InstrumentedAdapter(GatewayAdapterInterface):
    """Transparent metrics wrapper around any GatewayAdapterInterface.

    Proxies all 17+ methods to the inner adapter while recording:
    - Operation counter (success/error/timeout per gateway_type + operation)
    - Duration histogram (per gateway_type + operation)
    - Dedicated health check counter and latency histogram
    """

    def __init__(self, inner: GatewayAdapterInterface, gateway_type: str):
        self._inner = inner
        self._gateway_type = gateway_type
        self._config = inner._config

    def __getattr__(self, name: str):
        """Proxy attribute access to the inner adapter for non-interface attributes."""
        return getattr(self._inner, name)

    async def _record(self, operation: str, coro):
        """Execute a coroutine and record metrics around it."""
        start = time.perf_counter()
        status = "success"
        try:
            result = await coro
            if isinstance(result, AdapterResult) and not result.success:
                status = "error"
            return result
        except TimeoutError:
            status = "timeout"
            raise
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.perf_counter() - start
            ADAPTER_OPERATIONS_TOTAL.labels(
                gateway_type=self._gateway_type,
                operation=operation,
                status=status,
            ).inc()
            ADAPTER_OPERATION_DURATION.labels(
                gateway_type=self._gateway_type,
                operation=operation,
            ).observe(duration)

            # Dedicated health check metrics
            if operation == "health_check":
                ADAPTER_HEALTH_CHECKS_TOTAL.labels(
                    gateway_type=self._gateway_type,
                    status=status,
                ).inc()
                ADAPTER_HEALTH_CHECK_LATENCY.labels(
                    gateway_type=self._gateway_type,
                ).observe(duration)

    # --- Lifecycle ---

    async def health_check(self) -> AdapterResult:
        return await self._record("health_check", self._inner.health_check())

    async def connect(self) -> None:
        return await self._record("connect", self._inner.connect())

    async def disconnect(self) -> None:
        return await self._record("disconnect", self._inner.disconnect())

    # --- APIs ---

    async def sync_api(self, api_spec: dict, tenant_id: str, auth_token: str | None = None) -> AdapterResult:
        return await self._record("sync_api", self._inner.sync_api(api_spec, tenant_id, auth_token))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        return await self._record("delete_api", self._inner.delete_api(api_id, auth_token))

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        return await self._record("list_apis", self._inner.list_apis(auth_token))

    # --- Policies ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("upsert_policy", self._inner.upsert_policy(policy_spec, auth_token))

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        return await self._record("delete_policy", self._inner.delete_policy(policy_id, auth_token))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        return await self._record("list_policies", self._inner.list_policies(auth_token))

    # --- Applications ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("provision_application", self._inner.provision_application(app_spec, auth_token))

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        return await self._record("deprovision_application", self._inner.deprovision_application(app_id, auth_token))

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        return await self._record("list_applications", self._inner.list_applications(auth_token))

    # --- Auth / OIDC ---

    async def upsert_auth_server(self, auth_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("upsert_auth_server", self._inner.upsert_auth_server(auth_spec, auth_token))

    async def upsert_strategy(self, strategy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("upsert_strategy", self._inner.upsert_strategy(strategy_spec, auth_token))

    async def upsert_scope(self, scope_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("upsert_scope", self._inner.upsert_scope(scope_spec, auth_token))

    # --- Aliases ---

    async def upsert_alias(self, alias_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("upsert_alias", self._inner.upsert_alias(alias_spec, auth_token))

    # --- Configuration ---

    async def apply_config(self, config_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("apply_config", self._inner.apply_config(config_spec, auth_token))

    # --- Backup / Archive ---

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        return await self._record("export_archive", self._inner.export_archive(auth_token))

    # --- UAC Contract ---

    async def deploy_contract(self, contract_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return await self._record("deploy_contract", self._inner.deploy_contract(contract_spec, auth_token))
