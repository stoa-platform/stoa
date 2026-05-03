"""OpenAPI helpers used by the API lifecycle service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import yaml

from .errors import ApiLifecycleSpecValidationError, ApiLifecycleValidationError

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


@dataclass(frozen=True)
class OpenApiValidationResult:
    valid: bool
    code: str
    message: str
    spec_format: str
    spec_version: str
    title: str
    version: str
    path_count: int
    operation_count: int


def parse_openapi_contract(spec: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Parse an inline OpenAPI/Swagger document without changing catalog state."""
    if spec is None:
        return None
    if isinstance(spec, dict):
        parsed = spec
    elif isinstance(spec, str):
        if not spec.strip():
            return None
        try:
            parsed = json.loads(spec) if spec.lstrip().startswith("{") else yaml.safe_load(spec)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ApiLifecycleValidationError(f"Invalid OpenAPI spec: unable to parse: {exc}") from exc
    else:
        raise ApiLifecycleValidationError("Invalid OpenAPI spec: expected a JSON/YAML string or object")

    if not isinstance(parsed, dict):
        raise ApiLifecycleValidationError("Invalid OpenAPI spec: must be a JSON/YAML object")

    return parsed


def validate_openapi_contract(spec: str | dict[str, Any] | None) -> OpenApiValidationResult:
    """Validate the minimum OpenAPI/Swagger structure needed before deployment."""
    try:
        parsed = parse_openapi_contract(spec)
    except ApiLifecycleValidationError as exc:
        _invalid("openapi_spec_invalid", str(exc))
    if parsed is None:
        _invalid("openapi_spec_missing", "OpenAPI spec is required")

    spec_format, spec_version = _validate_spec_version(parsed)
    info = parsed.get("info")
    if not isinstance(info, dict):
        _invalid("openapi_info_missing", "OpenAPI spec must include an info object")

    title = info.get("title")
    if not isinstance(title, str) or not title.strip():
        _invalid("openapi_info_title_missing", "OpenAPI info.title is required")

    api_version = info.get("version")
    if not isinstance(api_version, str) or not api_version.strip():
        _invalid("openapi_info_version_missing", "OpenAPI info.version is required")

    paths = parsed.get("paths")
    if not isinstance(paths, dict):
        _invalid("openapi_paths_missing", "OpenAPI spec must include a paths object")
    if not paths:
        _invalid("openapi_paths_empty", "OpenAPI spec must include at least one path")

    operation_count = _validate_paths(paths)
    return OpenApiValidationResult(
        valid=True,
        code="validated",
        message="OpenAPI contract validated",
        spec_format=spec_format,
        spec_version=spec_version,
        title=title.strip(),
        version=api_version.strip(),
        path_count=len(paths),
        operation_count=operation_count,
    )


def _validate_spec_version(spec: dict[str, Any]) -> tuple[str, str]:
    openapi_version = spec.get("openapi")
    swagger_version = spec.get("swagger")
    if openapi_version:
        version = str(openapi_version)
        if not version.startswith("3"):
            _invalid("openapi_version_unsupported", f"Unsupported OpenAPI version: {version}. Supported: 3.x")
        return "openapi", version
    if swagger_version:
        version = str(swagger_version)
        if not version.startswith("2"):
            _invalid("swagger_version_unsupported", f"Unsupported Swagger version: {version}. Supported: 2.0")
        return "swagger", version
    _invalid("openapi_version_missing", "OpenAPI spec must declare 'openapi' or 'swagger'")


def _validate_paths(paths: dict[str, Any]) -> int:
    operation_count = 0
    for path, path_item in paths.items():
        if not isinstance(path, str) or not path.startswith("/"):
            _invalid("openapi_path_invalid", "OpenAPI path keys must start with '/'")
        if not isinstance(path_item, dict):
            _invalid("openapi_path_item_invalid", f"OpenAPI path item must be an object: {path}")

        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            operation_count += 1
            if not isinstance(operation, dict):
                _invalid("openapi_operation_invalid", f"OpenAPI operation must be an object: {path} {method}")
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                _invalid(
                    "openapi_operation_responses_missing",
                    f"OpenAPI operation must declare a non-empty responses object: {path} {method}",
                )
    return operation_count


def _invalid(code: str, message: str) -> None:
    raise ApiLifecycleSpecValidationError(code, message)
