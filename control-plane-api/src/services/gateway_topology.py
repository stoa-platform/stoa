"""Gateway topology normalization helpers.

The STOA runtime mode and the deployment topology are separate concepts:
``sidecar`` as a runtime means "expose /authz", while ``deployment_mode=sidecar``
is reserved for a proven same-pod Kubernetes sidecar.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

DEPLOYMENT_MODES = {"edge", "connect", "sidecar"}
TOPOLOGIES = {"native-edge", "remote-agent", "same-pod"}
TARGET_GATEWAY_TYPES = {
    "stoa",
    "kong",
    "webmethods",
    "gravitee",
    "agentgateway",
    "apigee",
    "aws_apigateway",
    "azure_apim",
}

_THIRD_PARTY_TARGETS = TARGET_GATEWAY_TYPES - {"stoa"}


@dataclass(frozen=True)
class GatewayTopology:
    """Canonical gateway classification exposed to Console and deployment logic."""

    deployment_mode: str
    target_gateway_type: str
    topology: str
    endpoints: dict[str, str]


def wire_value(value: object) -> str:
    """Return enum value for wire responses while preserving plain values."""
    return str(value.value if hasattr(value, "value") else (value or ""))


def _string_value(value: object) -> str | None:
    """Return a real string/enum wire value, ignoring loose mock attributes."""
    if value is None:
        return None
    raw = value.value if hasattr(value, "value") else value
    return raw if isinstance(raw, str) else None


def normalize_mode(mode: object | None) -> str:
    """Normalize ADR-024 runtime mode aliases."""
    mode_lower = (_string_value(mode) or "").strip().lower().replace("_", "-")
    if mode_lower in {"edge", "edge-mcp", "edgemcp", "mcp"}:
        return "edge-mcp"
    if mode_lower in {"sidecar", "proxy", "shadow", "connect"}:
        return mode_lower
    return mode_lower


def _normalized(value: object | None) -> str | None:
    value = (_string_value(value) or "").strip().lower().replace("_", "-")
    return value or None


def _normalize_deployment_mode(value: object | None) -> str | None:
    normalized = _normalized(value)
    return normalized if normalized in DEPLOYMENT_MODES else None


def _normalize_topology(value: object | None) -> str | None:
    normalized = _normalized(value)
    return normalized if normalized in TOPOLOGIES else None


def derive_target_gateway_type(
    gateway_type: object,
    explicit_target: object | None = None,
    *,
    tags: list[str] | None = None,
    name: object | None = None,
    target_gateway_url: object | None = None,
    base_url: object | None = None,
) -> str:
    """Normalize the actual target gateway technology.

    STOA-specific gateway types describe the STOA runtime. For Link/Connect
    instances, tags/name/URLs often carry the real third-party target.
    """
    explicit = (_string_value(explicit_target) or "").strip().lower().replace("-", "_")
    if explicit in TARGET_GATEWAY_TYPES:
        return explicit

    search_space = " ".join(
        value
        for value in [
            *[_string_value(tag) for tag in (tags or [])],
            _string_value(name),
            _string_value(target_gateway_url),
            _string_value(base_url),
        ]
        if value
    ).lower()

    for target in ("webmethods", "gravitee", "agentgateway", "kong"):
        if target in search_space:
            return target
    if "vps-wm" in search_space or "-wm-" in search_space or search_space.endswith("-wm"):
        return "webmethods"

    gw_type = (_string_value(gateway_type) or "").strip().lower()
    if gw_type.startswith("stoa_") or gw_type == "stoa":
        return "stoa"
    return gw_type or "stoa"


def has_same_pod_sidecar_proof(topology: str | None, proof: dict | None) -> bool:
    """Return true only when all sidecar proof conditions are present."""
    if topology != "same-pod" or not isinstance(proof, dict):
        return False

    declared = bool(proof.get("declared_in_kubernetes")) or bool(
        proof.get("namespace") and (proof.get("deployment") or proof.get("pod"))
    )

    containers = proof.get("containers")
    container_names = {str(name) for name in containers} if isinstance(containers, list) else set()
    target_container = str(proof.get("target_container") or "")
    sidecar_container = str(proof.get("sidecar_container") or "")
    container_count = proof.get("pod_container_count")
    enough_containers = (
        len(container_names) >= 2
        or (isinstance(container_count, int) and container_count >= 2)
        or bool(target_container and sidecar_container)
    )

    has_target = bool(target_container) and (not container_names or target_container in container_names)
    has_stoa_sidecar = sidecar_container == "stoa-sidecar" and (
        not container_names or sidecar_container in container_names
    )

    authz_url = str(proof.get("authz_url") or "")
    host = urlparse(authz_url).hostname
    local_authz = host in {"localhost", "127.0.0.1"} and authz_url.endswith("/authz")

    return declared and enough_containers and has_target and has_stoa_sidecar and local_authz


def build_endpoints(
    *,
    endpoints: dict | None = None,
    base_url: object | None = None,
    public_url: object | None = None,
    ui_url: object | None = None,
) -> dict[str, str]:
    """Return a normalized endpoint map while preserving existing explicit keys."""
    normalized: dict[str, str] = {
        str(key): str(value)
        for key, value in (endpoints if isinstance(endpoints, dict) else {}).items()
        if value is not None and str(value).strip()
    }
    public_url = _string_value(public_url)
    base_url = _string_value(base_url)
    ui_url = _string_value(ui_url)
    if public_url:
        normalized.setdefault("public_url", public_url)
    if base_url:
        normalized.setdefault("admin_url", base_url)
        if ".svc.cluster.local" in base_url or "://" not in base_url:
            normalized.setdefault("internal_url", base_url)
        normalized.setdefault("health_url", f"{base_url.rstrip('/')}/health")
    if ui_url:
        normalized.setdefault("ui_url", ui_url)
    return normalized


def normalize_gateway_topology(
    *,
    gateway_type: object,
    mode: object | None,
    source: object | None,
    deployment_mode: object | None = None,
    target_gateway_type: object | None = None,
    topology: object | None = None,
    health_details: dict | None = None,
    endpoints: dict | None = None,
    base_url: object | None = None,
    public_url: object | None = None,
    ui_url: object | None = None,
    target_gateway_url: object | None = None,
    tags: list[str] | None = None,
    name: object | None = None,
) -> GatewayTopology:
    """Normalize a gateway into the canonical topology contract."""
    normalized_mode = normalize_mode(mode)
    normalized_deployment = _normalize_deployment_mode(deployment_mode)
    normalized_topology = _normalize_topology(topology)
    target = derive_target_gateway_type(
        gateway_type,
        target_gateway_type,
        tags=tags,
        name=name,
        target_gateway_url=target_gateway_url,
        base_url=base_url,
    )
    endpoint_map = build_endpoints(endpoints=endpoints, base_url=base_url, public_url=public_url, ui_url=ui_url)
    proof = health_details.get("topology_proof") if isinstance(health_details, dict) else None

    if normalized_deployment == "sidecar" or normalized_topology == "same-pod":
        if target in _THIRD_PARTY_TARGETS and has_same_pod_sidecar_proof(normalized_topology, proof):
            return GatewayTopology("sidecar", target, "same-pod", endpoint_map)
        return GatewayTopology("connect", target, "remote-agent", endpoint_map)

    if normalized_deployment == "connect" or normalized_topology == "remote-agent":
        return GatewayTopology("connect", target, "remote-agent", endpoint_map)

    if normalized_deployment == "edge" or normalized_topology == "native-edge":
        return GatewayTopology("edge", "stoa" if target == "stoa" else target, "native-edge", endpoint_map)

    gw_type = (_string_value(gateway_type) or "").strip().lower()
    if normalized_mode == "edge-mcp" or gw_type == "stoa_edge_mcp":
        return GatewayTopology("edge", "stoa", "native-edge", endpoint_map)

    if normalized_mode == "connect" or _string_value(source) == "self_register":
        return GatewayTopology("connect", target, "remote-agent", endpoint_map)

    if gw_type == "stoa" and target == "stoa":
        return GatewayTopology("edge", target, "native-edge", endpoint_map)

    return GatewayTopology("connect", target, "remote-agent", endpoint_map)
