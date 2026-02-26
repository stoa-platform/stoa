"""System information schemas — edition, license, features (CAB-1311)."""

from enum import StrEnum

from pydantic import BaseModel


class Edition(StrEnum):
    """Platform edition — Open Core model.

    community: Free, Apache 2.0 licensed, self-hosted
    standard: Commercial add-ons (SSO, audit, SLA)
    enterprise: Full platform (federation, WASM plugins, premium support)
    """

    COMMUNITY = "community"
    STANDARD = "standard"
    ENTERPRISE = "enterprise"


class LicenseInfo(BaseModel):
    """License metadata."""

    edition: Edition
    license_type: str  # "Apache-2.0" for community, "Commercial" for standard/enterprise
    license_url: str = "https://github.com/stoa-platform/stoa/blob/main/LICENSE"


class FeatureFlags(BaseModel):
    """Features available per edition."""

    # Core (all editions)
    api_catalog: bool = True
    mcp_gateway: bool = True
    developer_portal: bool = True
    rbac: bool = True
    rate_limiting: bool = True
    openapi_to_mcp: bool = True

    # Standard+
    sso_oidc: bool = False
    audit_trail: bool = False
    tenant_export_import: bool = False
    webhook_delivery: bool = False
    custom_policies: bool = False

    # Enterprise
    mcp_federation: bool = False
    wasm_plugins: bool = False
    multi_cloud_adapters: bool = False
    ai_guardrails: bool = False
    sla_monitoring: bool = False


# Feature sets per edition
_EDITION_FEATURES: dict[Edition, dict[str, bool]] = {
    Edition.COMMUNITY: {},  # all defaults (core only)
    Edition.STANDARD: {
        "sso_oidc": True,
        "audit_trail": True,
        "tenant_export_import": True,
        "webhook_delivery": True,
        "custom_policies": True,
    },
    Edition.ENTERPRISE: {
        "sso_oidc": True,
        "audit_trail": True,
        "tenant_export_import": True,
        "webhook_delivery": True,
        "custom_policies": True,
        "mcp_federation": True,
        "wasm_plugins": True,
        "multi_cloud_adapters": True,
        "ai_guardrails": True,
        "sla_monitoring": True,
    },
}


def get_features_for_edition(edition: Edition) -> FeatureFlags:
    """Return feature flags for a given edition."""
    overrides = _EDITION_FEATURES.get(edition, {})
    return FeatureFlags(**overrides)


class SystemInfoResponse(BaseModel):
    """Platform system information — public endpoint."""

    platform: str = "STOA Platform"
    tagline: str = "The European Agent Gateway"
    version: str
    environment: str
    license: LicenseInfo
    features: FeatureFlags
    docs_url: str = "https://docs.gostoa.dev"
    repository: str = "https://github.com/stoa-platform/stoa"
