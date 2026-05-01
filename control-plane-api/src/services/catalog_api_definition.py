"""Helpers for catalog ``api.yaml`` normalization and deployment targets.

The catalog currently contains two API shapes:

* flat legacy entries (``name``, ``backend_url``, ``deployments``)
* Kubernetes-style entries (``apiVersion/kind/metadata/spec``)

Control Plane sync paths must consume both shapes consistently.  These helpers
produce the flat read-model shape used by ``api_catalog`` while preserving
deployment-target metadata for the runtime reconciler.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_DEFAULT_ENV_ALIASES: dict[str, str] = {
    "dev": "dev",
    "development": "dev",
    "staging": "staging",
    "stage": "staging",
    "prod": "production",
    "production": "production",
}


@dataclass(frozen=True)
class CatalogDeploymentTarget:
    """One desired runtime target declared by catalog metadata."""

    instance: str | None
    environment: str | None = None
    activated: bool = True
    source: str = "gateways"


def normalize_environment(value: object) -> str | None:
    """Return the canonical environment label used by runtime reconciliation."""
    if value is None:
        return None
    env = str(value).strip().lower()
    if not env:
        return None
    return _DEFAULT_ENV_ALIASES.get(env, env)


def normalize_api_definition(raw_data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize raw catalog YAML into the flat sync format.

    The function intentionally preserves fields such as ``deployments`` and
    ``gateways`` instead of reducing them to a legacy ``dev/staging`` boolean
    map.  Runtime recovery depends on those fields surviving the Git -> CP
    projection.
    """
    if "apiVersion" not in raw_data or "kind" not in raw_data:
        return raw_data if isinstance(raw_data, dict) else dict(raw_data)

    raw = dict(raw_data)

    metadata = _mapping(raw.get("metadata"))
    spec = _mapping(raw.get("spec"))
    backend = _mapping(spec.get("backend"))

    deployments = spec.get("deployments", {"dev": False, "staging": False})
    if deployments is None:
        deployments = {}

    normalized: dict[str, Any] = {
        "id": metadata.get("name", ""),
        "name": metadata.get("name", ""),
        "display_name": spec.get("displayName", metadata.get("name", "")),
        "version": metadata.get("version", "1.0.0"),
        "description": spec.get("description", ""),
        "backend_url": backend.get("url", ""),
        "status": spec.get("status", "draft"),
        "category": spec.get("category"),
        "tags": spec.get("tags", []),
        "deployments": deployments,
    }

    # Preferred explicit target fields.  ``spec.gateway`` in current catalog
    # files describes webMethods API settings, not a target instance, so it is
    # deliberately not treated as a deployment target.
    for key in ("gateways", "gateway_targets", "deployment_targets"):
        if key in spec:
            normalized["gateways"] = spec[key]
            break

    if "audience" in spec:
        normalized["audience"] = spec["audience"]
    if "documentation" in spec:
        normalized["documentation"] = spec["documentation"]
    if "routing" in spec:
        normalized["routing"] = spec["routing"]
    if "policies" in spec:
        normalized["policies"] = spec["policies"]

    return normalized


def extract_deployment_targets(raw_api: Mapping[str, Any]) -> list[CatalogDeploymentTarget]:
    """Extract deployment targets from normalized or raw catalog API content.

    Supported target declarations:

    * ``gateways: [{instance: connect-webmethods-dev, environment: dev}]``
    * ``gateways: [connect-webmethods-dev]``
    * ``gateways: {connect-webmethods-dev: {activated: true}}``
    * ``deployments.dev.gateways: [...]``
    * ``deployments.dev.gateway: connect-webmethods-dev``
    * ``deployments.dev: [connect-webmethods-dev]``

    Boolean ``deployments: {dev: true}`` is retained as an environment marker
    but does not identify a gateway instance.  The reconciler logs it as
    non-materializable rather than guessing a target.
    """
    api = normalize_api_definition(raw_api)
    targets: list[CatalogDeploymentTarget] = []
    targets.extend(_parse_targets_block(api.get("gateways"), default_environment=None, source="gateways"))
    targets.extend(_parse_deployments_block(api.get("deployments")))
    return _dedupe_targets(targets)


def extract_target_gateway_names(raw_api: Mapping[str, Any]) -> list[str]:
    """Return explicit gateway instance names declared by the catalog API."""
    names: list[str] = []
    seen: set[str] = set()
    for target in extract_deployment_targets(raw_api):
        if not target.instance or target.instance in seen:
            continue
        seen.add(target.instance)
        names.append(target.instance)
    return names


def environment_matches(gateway_environment: object, target_environment: object) -> bool:
    """Return True when a gateway environment satisfies a target environment."""
    target = normalize_environment(target_environment)
    if target is None:
        return True
    gateway = normalize_environment(gateway_environment)
    return gateway == target


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _parse_deployments_block(value: object) -> list[CatalogDeploymentTarget]:
    if not isinstance(value, Mapping):
        return []

    targets: list[CatalogDeploymentTarget] = []
    for env_name, env_config in value.items():
        env = normalize_environment(env_name)
        if env_config is False or env_config is None:
            continue
        if env_config is True:
            targets.append(CatalogDeploymentTarget(instance=None, environment=env, source="deployments"))
            continue
        targets.extend(_parse_targets_block(env_config, default_environment=env, source="deployments"))
    return targets


def _parse_targets_block(
    value: object,
    *,
    default_environment: str | None,
    source: str,
) -> list[CatalogDeploymentTarget]:
    if value is None:
        return []

    if isinstance(value, str):
        name = value.strip()
        return [CatalogDeploymentTarget(instance=name, environment=default_environment, source=source)] if name else []

    if isinstance(value, list):
        targets: list[CatalogDeploymentTarget] = []
        for entry in value:
            targets.extend(_parse_target_entry(entry, default_environment=default_environment, source=source))
        return targets

    if isinstance(value, Mapping):
        data = dict(value)
        nested = _first_present(data, ("gateways", "gateway_targets", "deployment_targets", "instances"))
        if nested is not None:
            env = normalize_environment(data.get("environment")) or default_environment
            has_activation = _has_activation_key(data)
            activated = _coerce_activated(data, default=True)
            return [
                CatalogDeploymentTarget(
                    instance=t.instance,
                    environment=t.environment or env,
                    activated=activated if has_activation else t.activated,
                    source=t.source,
                )
                for t in _parse_targets_block(nested, default_environment=env, source=source)
            ]

        explicit_name = _target_name(data)
        if explicit_name:
            return [
                CatalogDeploymentTarget(
                    instance=explicit_name,
                    environment=normalize_environment(data.get("environment")) or default_environment,
                    activated=_coerce_activated(data, default=True),
                    source=source,
                )
            ]

        if _looks_like_name_map(data):
            targets: list[CatalogDeploymentTarget] = []
            for name, config in data.items():
                if isinstance(config, Mapping):
                    entry = {"instance": name, **dict(config)}
                elif config is False or config is None:
                    continue
                else:
                    entry = {"instance": name, "activated": bool(config)}
                targets.extend(_parse_target_entry(entry, default_environment=default_environment, source=source))
            return targets

    return []


def _parse_target_entry(
    entry: object,
    *,
    default_environment: str | None,
    source: str,
) -> list[CatalogDeploymentTarget]:
    if isinstance(entry, str):
        name = entry.strip()
        return [CatalogDeploymentTarget(instance=name, environment=default_environment, source=source)] if name else []
    if not isinstance(entry, Mapping):
        return []
    if entry.get("enabled") is False or entry.get("deployed") is False:
        return []
    return _parse_targets_block(entry, default_environment=default_environment, source=source)


def _target_name(data: Mapping[str, Any]) -> str | None:
    for key in ("instance", "name", "gateway", "gateway_name", "gatewayInstance", "gateway_instance"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_present(data: Mapping[str, Any], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _coerce_activated(data: Mapping[str, Any], *, default: bool) -> bool:
    for key in ("activated", "active", "enabled", "deployed"):
        value = data.get(key)
        if isinstance(value, bool):
            return value
    return default


def _has_activation_key(data: Mapping[str, Any]) -> bool:
    return any(key in data for key in ("activated", "active", "enabled", "deployed"))


def _looks_like_name_map(data: Mapping[str, Any]) -> bool:
    reserved = {
        "environment",
        "activated",
        "active",
        "enabled",
        "deployed",
        "gateways",
        "gateway_targets",
        "deployment_targets",
        "instances",
    }
    return bool(data) and not any(key in reserved for key in data)


def _dedupe_targets(targets: list[CatalogDeploymentTarget]) -> list[CatalogDeploymentTarget]:
    seen: set[tuple[str | None, str | None]] = set()
    result: list[CatalogDeploymentTarget] = []
    for target in targets:
        key = (target.instance, target.environment)
        if key in seen:
            continue
        seen.add(key)
        result.append(target)
    return result
