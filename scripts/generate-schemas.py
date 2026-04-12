#!/usr/bin/env python3
"""Generate JSON Schema registry from Pydantic models.

Exports one JSON Schema file per stoactl Kind into charts/stoa-platform/schemas/.
These schemas are the single source of truth for resource validation in stoactl.

Usage:
    cd control-plane-api && python ../scripts/generate-schemas.py
"""

import json
import sys
from pathlib import Path

# Ensure control-plane-api/src is importable
CP_API_SRC = Path(__file__).resolve().parent.parent / "control-plane-api"
sys.path.insert(0, str(CP_API_SRC))

from src.schemas.backend_api import BackendApiCreate  # noqa: E402
from src.schemas.consumer import ConsumerCreate  # noqa: E402
from src.schemas.contract import ContractCreate  # noqa: E402
from src.schemas.gateway import GatewayInstanceCreate  # noqa: E402
from src.schemas.mcp_subscription import MCPServerCreate  # noqa: E402
from src.schemas.plan import PlanCreate  # noqa: E402
from src.schemas.subscription import SubscriptionCreate  # noqa: E402
from src.schemas.tenant import TenantCreate  # noqa: E402
from src.schemas.webhook import WebhookCreate  # noqa: E402

# ServiceAccountCreate is defined inline in routers — import it
from src.routers.service_accounts import ServiceAccountCreate  # noqa: E402

# ── Kind → Pydantic model mapping ──────────────────────────────────────────
API_VERSION = "gostoa.dev/v1beta1"

KIND_MAP: dict[str, type] = {
    "API": BackendApiCreate,
    "Tenant": TenantCreate,
    "Gateway": GatewayInstanceCreate,
    "Subscription": SubscriptionCreate,
    "Consumer": ConsumerCreate,
    "Contract": ContractCreate,
    "MCPServer": MCPServerCreate,
    "ServiceAccount": ServiceAccountCreate,
    "Plan": PlanCreate,
    "Webhook": WebhookCreate,
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "charts" / "stoa-platform" / "schemas"


def generate_schema(kind: str, model: type) -> dict:
    """Generate a JSON Schema for a stoactl resource kind."""
    schema = model.model_json_schema()

    # Wrap in the stoactl resource envelope
    resource_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://docs.gostoa.dev/schemas/{kind.lower()}.schema.json",
        "title": f"STOA {kind} Resource",
        "description": f"Schema for stoactl apply -f with kind: {kind}",
        "type": "object",
        "required": ["apiVersion", "kind", "metadata", "spec"],
        "properties": {
            "apiVersion": {
                "type": "string",
                "const": API_VERSION,
                "description": "STOA API version",
            },
            "kind": {
                "type": "string",
                "const": kind,
                "description": "Resource kind",
            },
            "metadata": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Resource name (unique within tenant)",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Tenant ID (optional, falls back to CLI context)",
                    },
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Key-value labels",
                    },
                },
                "additionalProperties": False,
            },
            "spec": schema,
        },
        "additionalProperties": False,
    }

    return resource_schema


def generate_registry(kinds: list[str]) -> dict:
    """Generate the registry index listing all available schemas."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://docs.gostoa.dev/schemas/registry.json",
        "title": "STOA Schema Registry",
        "description": f"Registry of all {len(kinds)} stoactl resource kinds at {API_VERSION}",
        "apiVersion": API_VERSION,
        "kinds": {
            kind: {
                "schema": f"{kind.lower()}.schema.json",
                "description": f"STOA {kind} resource",
            }
            for kind in sorted(kinds)
        },
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generated = []
    for kind, model in sorted(KIND_MAP.items()):
        schema = generate_schema(kind, model)
        output_path = OUTPUT_DIR / f"{kind.lower()}.schema.json"
        output_path.write_text(json.dumps(schema, indent=2) + "\n")
        generated.append(kind)
        print(f"  ✓ {kind:20s} → {output_path.relative_to(OUTPUT_DIR.parent.parent.parent)}")

    # Write registry index
    registry = generate_registry(generated)
    registry_path = OUTPUT_DIR / "registry.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n")
    print(f"  ✓ {'registry':20s} → {registry_path.relative_to(OUTPUT_DIR.parent.parent.parent)}")

    print(f"\n✅ Generated {len(generated)} schemas + registry at {API_VERSION}")


if __name__ == "__main__":
    main()
