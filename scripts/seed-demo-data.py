#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAB-1061: Seed demo data for STOA Platform presentation.

Creates:
  1. 3 APIs: petstore, account-management, payments (portal-published)
  2. 2 Plans: standard (10 rps), premium (50 rps, approval required)
  3. 2 Consumers: OASIS Mobile, Gunter Analytics (with Keycloak clients)
  4. 2 Applications: 1 active, 1 pending approval
  5. 2 Subscriptions: 1 active (approved), 1 pending
  6. Sample API calls to generate Grafana metrics

Idempotent: Safe to re-run. 409 = already exists = OK.

Usage:
    # Default: targets production (gostoa.dev)
    python scripts/seed-demo-data.py

    # Custom environment
    CONTROL_PLANE_URL=http://localhost:8000 \
    KEYCLOAK_URL=http://localhost:8180 \
    ANORAK_PASSWORD=Anorak2045! \
    python scripts/seed-demo-data.py

Environment Variables:
    CONTROL_PLANE_URL   API base URL          (default: https://api.gostoa.dev)
    KEYCLOAK_URL        Keycloak base URL     (default: https://auth.gostoa.dev)
    KEYCLOAK_REALM      Keycloak realm        (default: stoa)
    ANORAK_USER         Admin username         (default: anorak@gostoa.dev)
    ANORAK_PASSWORD     Admin password         (required)
    SEED_TENANT         Target tenant          (default: high-five)
"""

import json
import os
import sys
import time

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

API_URL = os.getenv("CONTROL_PLANE_URL", "https://api.gostoa.dev")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.gostoa.dev")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
SEED_USER = os.getenv("ANORAK_USER", "anorak@gostoa.dev")
SEED_PASSWORD = os.getenv("ANORAK_PASSWORD", "")
DEMO_TENANT = os.getenv("SEED_TENANT", "high-five")


# =============================================================================
# OpenAPI Specifications (embedded, minimal but renderable)
# =============================================================================

PETSTORE_SPEC = json.dumps(
    {
        "openapi": "3.0.0",
        "info": {
            "title": "Petstore API",
            "version": "1.0.0",
            "description": "Classic pet management API — browse, add, and manage pets in the store.",
        },
        "servers": [{"url": "https://httpbin.org/anything"}],
        "paths": {
            "/pets": {
                "get": {
                    "summary": "List all pets",
                    "operationId": "listPets",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "maximum": 100},
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": ["available", "pending", "sold"],
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "A list of pets",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Pet"},
                                    }
                                }
                            },
                        }
                    },
                },
                "post": {
                    "summary": "Create a pet",
                    "operationId": "createPet",
                    "tags": ["pets"],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}},
                    },
                    "responses": {"201": {"description": "Pet created"}},
                },
            },
            "/pets/{petId}": {
                "get": {
                    "summary": "Get pet by ID",
                    "operationId": "getPetById",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "petId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "A pet",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}},
                        },
                        "404": {"description": "Pet not found"},
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "id": {"type": "integer", "format": "int64"},
                        "name": {"type": "string", "example": "Buddy"},
                        "status": {
                            "type": "string",
                            "enum": ["available", "pending", "sold"],
                        },
                        "category": {"type": "string", "example": "dog"},
                    },
                }
            }
        },
    }
)

ACCOUNTS_SPEC = json.dumps(
    {
        "openapi": "3.0.0",
        "info": {
            "title": "Account Management API",
            "version": "2.1.0",
            "description": (
                "Manage user accounts, profiles, and preferences. " "Supports CRUD operations with full audit trail."
            ),
        },
        "servers": [{"url": "https://httpbin.org/anything"}],
        "paths": {
            "/accounts": {
                "get": {
                    "summary": "List accounts",
                    "operationId": "listAccounts",
                    "tags": ["accounts"],
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1},
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["active", "suspended", "closed"],
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Paginated list of accounts",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "items": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/Account"},
                                            },
                                            "total": {"type": "integer"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                },
                "post": {
                    "summary": "Create account",
                    "operationId": "createAccount",
                    "tags": ["accounts"],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AccountCreate"}}},
                    },
                    "responses": {"201": {"description": "Account created"}},
                },
            },
            "/accounts/{accountId}": {
                "get": {
                    "summary": "Get account details",
                    "operationId": "getAccount",
                    "tags": ["accounts"],
                    "parameters": [
                        {
                            "name": "accountId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Account details"},
                        "404": {"description": "Account not found"},
                    },
                },
                "put": {
                    "summary": "Update account",
                    "operationId": "updateAccount",
                    "tags": ["accounts"],
                    "parameters": [
                        {
                            "name": "accountId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "requestBody": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AccountUpdate"}}}
                    },
                    "responses": {"200": {"description": "Account updated"}},
                },
                "delete": {
                    "summary": "Close account",
                    "operationId": "deleteAccount",
                    "tags": ["accounts"],
                    "parameters": [
                        {
                            "name": "accountId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {"204": {"description": "Account closed"}},
                },
            },
        },
        "components": {
            "schemas": {
                "Account": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "email": {"type": "string", "format": "email"},
                        "display_name": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["active", "suspended", "closed"],
                        },
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "AccountCreate": {
                    "type": "object",
                    "required": ["email", "display_name"],
                    "properties": {
                        "email": {
                            "type": "string",
                            "format": "email",
                            "example": "user@example.com",
                        },
                        "display_name": {
                            "type": "string",
                            "example": "Jane Doe",
                        },
                    },
                },
                "AccountUpdate": {
                    "type": "object",
                    "properties": {
                        "display_name": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["active", "suspended"],
                        },
                    },
                },
            }
        },
    }
)

PAYMENTS_SPEC = json.dumps(
    {
        "openapi": "3.0.0",
        "info": {
            "title": "Payments API",
            "version": "3.0.0",
            "description": ("Process payments, refunds, and manage payment methods. " "PCI-DSS Level 1 compliant."),
        },
        "servers": [{"url": "https://httpbin.org/anything"}],
        "paths": {
            "/payments": {
                "post": {
                    "summary": "Create a payment",
                    "operationId": "createPayment",
                    "tags": ["payments"],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PaymentCreate"}}},
                    },
                    "responses": {
                        "201": {
                            "description": "Payment initiated",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Payment"}}},
                        },
                        "422": {"description": "Invalid payment data"},
                    },
                },
                "get": {
                    "summary": "List payments",
                    "operationId": "listPayments",
                    "tags": ["payments"],
                    "parameters": [
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["pending", "completed", "failed", "refunded"],
                            },
                        },
                        {
                            "name": "from",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "to",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                    ],
                    "responses": {"200": {"description": "List of payments"}},
                },
            },
            "/payments/{paymentId}": {
                "get": {
                    "summary": "Get payment details",
                    "operationId": "getPayment",
                    "tags": ["payments"],
                    "parameters": [
                        {
                            "name": "paymentId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Payment details"},
                        "404": {"description": "Payment not found"},
                    },
                }
            },
            "/payments/{paymentId}/refund": {
                "post": {
                    "summary": "Refund a payment",
                    "operationId": "refundPayment",
                    "tags": ["refunds"],
                    "parameters": [
                        {
                            "name": "paymentId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "amount": {
                                            "type": "number",
                                            "format": "double",
                                            "description": "Partial refund amount (omit for full)",
                                        },
                                        "reason": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Refund processed"},
                        "409": {"description": "Payment already refunded"},
                    },
                },
            },
        },
        "components": {
            "schemas": {
                "Payment": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "amount": {"type": "number", "format": "double"},
                        "currency": {"type": "string", "example": "EUR"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "completed", "failed", "refunded"],
                        },
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "PaymentCreate": {
                    "type": "object",
                    "required": ["amount", "currency"],
                    "properties": {
                        "amount": {
                            "type": "number",
                            "format": "double",
                            "minimum": 0.01,
                            "example": 49.99,
                        },
                        "currency": {
                            "type": "string",
                            "enum": ["EUR", "USD", "GBP"],
                            "example": "EUR",
                        },
                        "description": {
                            "type": "string",
                            "example": "Monthly subscription",
                        },
                        "metadata": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                },
            }
        },
    }
)


# =============================================================================
# Demo Data Definitions
# =============================================================================

DEMO_APIS = [
    {
        "name": "petstore",
        "display_name": "Petstore API",
        "version": "1.0.0",
        "description": (
            "Classic pet management API \u2014 browse, add, and manage pets in the store. "
            "Ideal starter API for testing subscriptions and playground."
        ),
        "backend_url": "https://httpbin.org/anything",
        "tags": ["portal:published", "rest", "demo", "public"],
        "openapi_spec": PETSTORE_SPEC,
    },
    {
        "name": "account-management",
        "display_name": "Account Management API",
        "version": "2.1.0",
        "description": (
            "Manage user accounts, profiles, and preferences. " "Full CRUD with audit trail and role-based access."
        ),
        "backend_url": "https://httpbin.org/anything",
        "tags": ["portal:published", "rest", "demo", "enterprise"],
        "openapi_spec": ACCOUNTS_SPEC,
    },
    {
        "name": "payments",
        "display_name": "Payments API",
        "version": "3.0.0",
        "description": (
            "Process payments, refunds, and manage payment methods. "
            "PCI-DSS Level 1 compliant. Supports EUR, USD, GBP."
        ),
        "backend_url": "https://httpbin.org/anything",
        "tags": ["portal:published", "rest", "demo", "enterprise", "pci"],
        "openapi_spec": PAYMENTS_SPEC,
    },
]

DEMO_PLANS = [
    {
        "slug": "standard",
        "name": "Standard Plan",
        "description": "Standard API access \u2014 10 req/s, 600 req/min, 100k daily.",
        "rate_limit_per_second": 10,
        "rate_limit_per_minute": 600,
        "daily_request_limit": 100000,
        "monthly_request_limit": 3000000,
        "burst_limit": 20,
        "requires_approval": False,
    },
    {
        "slug": "premium",
        "name": "Premium Plan",
        "description": "Premium API access \u2014 50 req/s, 3k req/min, 1M daily. Requires approval.",
        "rate_limit_per_second": 50,
        "rate_limit_per_minute": 3000,
        "daily_request_limit": 1000000,
        "monthly_request_limit": 30000000,
        "burst_limit": 100,
        "requires_approval": True,
    },
]

DEMO_CONSUMERS = [
    {
        "external_id": "oasis-mobile-app",
        "name": "OASIS Mobile App",
        "email": "api@oasis.high-five.dev",
        "company": "High Five Inc",
        "description": "Mobile application consuming Petstore API",
    },
    {
        "external_id": "gunter-analytics",
        "name": "Gunter Analytics Dashboard",
        "email": "api@gunter.high-five.dev",
        "company": "High Five Inc",
        "description": "Analytics dashboard consuming Payments API",
    },
]

DEMO_APPS = [
    {
        "name": "oasis-mobile",
        "display_name": "OASIS Mobile App",
        "description": "Mobile application for OASIS API consumption",
        "tenant_id": None,  # set dynamically
        "_status": "active",  # will have approved subscription
    },
    {
        "name": "gunter-dashboard",
        "display_name": "Gunter Analytics Dashboard",
        "description": "Analytics dashboard \u2014 pending approval for Payments API access",
        "tenant_id": None,  # set dynamically
        "_status": "pending",  # subscription left pending
    },
]


# =============================================================================
# Auth
# =============================================================================


def get_access_token() -> str | None:
    """Get access token from Keycloak via password grant."""
    if not SEED_PASSWORD:
        print("  [!] ANORAK_PASSWORD not set")
        return None

    token_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

    try:
        resp = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": "control-plane-ui",
                "username": SEED_USER,
                "password": SEED_PASSWORD,
            },
            timeout=15.0,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        print(f"  [-] Auth failed: {resp.status_code} \u2014 {resp.text[:120]}")
        return None
    except Exception as e:
        print(f"  [-] Auth error: {e}")
        return None


def create_client(token: str | None) -> httpx.Client:
    """Create HTTP client with auth header."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_URL, headers=headers, timeout=30.0)


# =============================================================================
# Phase 1: Seed APIs (GitOps first, offline fallback to catalog/seed)
# =============================================================================


def ensure_tenant(client: httpx.Client) -> bool:
    """Create demo tenant if it doesn't exist."""
    print(f"\n=== Phase 0: Ensuring tenant '{DEMO_TENANT}' exists ===")
    payload = {
        "name": DEMO_TENANT,
        "display_name": "High Five - The Resistance",
        "description": "Parzival's team — demo tenant for STOA Platform",
        "owner_email": "parzival@highfive.oasis",
    }
    try:
        resp = client.post("/v1/tenants", json=payload)
        if resp.status_code in (200, 201):
            print(f"  [+] Tenant '{DEMO_TENANT}' created")
            return True
        elif resp.status_code == 409:
            print(f"  [=] Tenant '{DEMO_TENANT}' already exists")
            return True
        else:
            print(f"  [-] Tenant creation failed: {resp.status_code} — {resp.text[:120]}")
            return False
    except Exception as e:
        print(f"  [-] Tenant creation error: {e}")
        return False


def seed_apis_via_gitops(client: httpx.Client) -> dict[str, bool]:
    """Try creating APIs via GitOps endpoint. Returns {name: success}."""
    results = {}
    for api in DEMO_APIS:
        name = api["name"]
        payload = {
            "name": api["name"],
            "display_name": api["display_name"],
            "version": api["version"],
            "description": api["description"],
            "backend_url": api["backend_url"],
            "tags": api["tags"],
            "openapi_spec": api["openapi_spec"],
        }
        try:
            resp = client.post(f"/v1/tenants/{DEMO_TENANT}/apis", json=payload)
            if resp.status_code in (200, 201):
                print(f"  [+] API '{name}' created (GitOps)")
                results[name] = True
            elif resp.status_code == 409:
                print(f"  [=] API '{name}' already exists (idempotent)")
                results[name] = True
            else:
                print(f"  [-] API '{name}' failed: {resp.status_code} — {resp.text[:120]}")
                results[name] = False
        except Exception as e:
            print(f"  [-] API '{name}' error: {e}")
            results[name] = False
    return results


def seed_apis_offline(client: httpx.Client) -> dict[str, bool]:
    """Seed APIs directly into catalog (bypasses GitLab). Offline mode."""
    print("  [~] Switching to OFFLINE mode (direct catalog seed)...")
    payload = {
        "tenant_id": DEMO_TENANT,
        "apis": [
            {
                "name": api["name"],
                "display_name": api["display_name"],
                "version": api["version"],
                "description": api["description"],
                "backend_url": api["backend_url"],
                "tags": api["tags"],
                "openapi_spec": api["openapi_spec"],
                "category": "Demo",
            }
            for api in DEMO_APIS
        ],
    }
    try:
        resp = client.post("/v1/admin/catalog/seed", json=payload)
        if resp.status_code in (200, 201):
            data = resp.json()
            seeded = data.get("seeded", 0)
            failed = data.get("failed", 0)
            results_map = data.get("results", {})
            print(f"  [+] Offline seed: {seeded} seeded, {failed} failed")
            return {name: (results_map.get(name, "") == "seeded") for name in results_map}
        print(f"  [-] Offline seed failed: {resp.status_code} — {resp.text[:200]}")
        return {api["name"]: False for api in DEMO_APIS}
    except Exception as e:
        print(f"  [-] Offline seed error: {e}")
        return {api["name"]: False for api in DEMO_APIS}


def seed_apis(client: httpx.Client) -> tuple[dict[str, bool], bool]:
    """Create 3 demo APIs. Returns (results, used_offline_mode)."""
    print(f"\n=== Phase 1: Creating APIs in tenant '{DEMO_TENANT}' ===")

    # Try GitOps first
    results = seed_apis_via_gitops(client)

    # If any failed (likely "GitLab not connected"), fall back to offline seed
    if not all(results.values()):
        failed_names = [n for n, ok in results.items() if not ok]
        print(f"  [!] {len(failed_names)} APIs failed via GitOps — trying offline seed")
        offline_results = seed_apis_offline(client)
        # Merge: keep GitOps successes, override failures with offline results
        for name in failed_names:
            results[name] = offline_results.get(name, False)
        return results, True

    return results, False


def trigger_catalog_sync(client: httpx.Client) -> bool:
    """Trigger catalog sync so APIs appear in the portal."""
    print("\n=== Phase 2: Triggering catalog sync ===")
    try:
        resp = client.post(f"/v1/admin/catalog/sync/tenant/{DEMO_TENANT}")
        if resp.status_code in (200, 201):
            data = resp.json()
            print(f"  [+] Sync triggered: {data.get('message', 'OK')}")
            return True
        print(f"  [-] Sync trigger failed: {resp.status_code} — {resp.text[:120]}")
        return False
    except Exception as e:
        print(f"  [-] Sync trigger error: {e}")
        return False


def wait_for_sync(client: httpx.Client, timeout: int = 30) -> bool:
    """Poll sync status until complete or timeout."""
    print("  [~] Waiting for sync to complete...", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = client.get("/v1/admin/catalog/sync/status")
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status in ("success", "completed"):
                    items = data.get("items_synced", "?")
                    print(f" done ({items} items)")
                    return True
                if status == "failed":
                    print(f" FAILED: {data.get('errors', [])}")
                    return False
            elif resp.status_code == 404:
                print(" (no sync history yet)")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print(" timeout")
    return False


def verify_portal_apis(client: httpx.Client) -> int:
    """Check how many APIs are visible in the portal catalog."""
    try:
        resp = client.get("/v1/portal/apis", params={"page_size": 100})
        if resp.status_code == 200:
            data = resp.json()
            return data.get("total", 0)
    except Exception:
        pass
    return -1


# =============================================================================
# Phase 3: Seed Plans (CAB-1121 P4)
# =============================================================================


def seed_plans(client: httpx.Client) -> dict[str, str | None]:
    """Create subscription plans. Returns {slug: plan_id}."""
    results: dict[str, str | None] = {}

    print(f"\n=== Phase 3: Creating Plans in tenant '{DEMO_TENANT}' ===")
    for plan_def in DEMO_PLANS:
        slug = plan_def["slug"]
        try:
            resp = client.post(f"/v1/plans/{DEMO_TENANT}", json=plan_def)
            if resp.status_code in (200, 201):
                data = resp.json()
                plan_id = data.get("id")
                print(f"  [+] Plan '{slug}' created (id: {str(plan_id)[:8]}...)")
                results[slug] = str(plan_id) if plan_id else None
            elif resp.status_code == 409:
                print(f"  [=] Plan '{slug}' already exists")
                # Try to fetch it by slug to get the ID
                try:
                    get_resp = client.get(f"/v1/plans/{DEMO_TENANT}/by-slug/{slug}")
                    if get_resp.status_code == 200:
                        results[slug] = str(get_resp.json().get("id"))
                    else:
                        results[slug] = None
                except Exception:
                    results[slug] = None
            else:
                print(f"  [-] Plan '{slug}' failed: {resp.status_code} \u2014 {resp.text[:120]}")
                results[slug] = None
        except Exception as e:
            print(f"  [-] Plan '{slug}' error: {e}")
            results[slug] = None

    return results


# =============================================================================
# Phase 4: Seed Consumers (CAB-1121 P1)
# =============================================================================


def seed_consumers(client: httpx.Client) -> dict[str, str | None]:
    """Create demo consumers with Keycloak OAuth2 clients. Returns {external_id: consumer_id}."""
    results: dict[str, str | None] = {}

    print(f"\n=== Phase 4: Creating Consumers in tenant '{DEMO_TENANT}' ===")
    for consumer_def in DEMO_CONSUMERS:
        ext_id = consumer_def["external_id"]
        try:
            resp = client.post(f"/v1/consumers/{DEMO_TENANT}", json=consumer_def)
            if resp.status_code in (200, 201):
                data = resp.json()
                consumer_id = data.get("id")
                kc_client = data.get("keycloak_client_id", "pending")
                print(f"  [+] Consumer '{ext_id}' created (id: {str(consumer_id)[:8]}..., kc: {kc_client})")
                results[ext_id] = str(consumer_id) if consumer_id else None
            elif resp.status_code == 409:
                print(f"  [=] Consumer '{ext_id}' already exists")
                results[ext_id] = None
            elif resp.status_code == 503:
                print(f"  [~] Consumer '{ext_id}' created but Keycloak unavailable (retry later)")
                results[ext_id] = None
            else:
                print(f"  [-] Consumer '{ext_id}' failed: {resp.status_code} \u2014 {resp.text[:120]}")
                results[ext_id] = None
        except Exception as e:
            print(f"  [-] Consumer '{ext_id}' error: {e}")
            results[ext_id] = None

    return results


# =============================================================================
# Phase 5: Seed Applications
# =============================================================================


def seed_applications(client: httpx.Client) -> dict[str, str | None]:
    """Create 2 demo applications. Returns {name: app_id}."""
    results = {}

    print("\n=== Phase 5: Creating Applications ===")
    for app_def in DEMO_APPS:
        name = app_def["name"]
        payload = {
            "name": app_def["name"],
            "display_name": app_def["display_name"],
            "description": app_def["description"],
            "tenant_id": DEMO_TENANT,
        }
        try:
            resp = client.post("/v1/applications", json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                app_id = data.get("id")
                client_id = data.get("client_id", "?")
                print(f"  [+] App '{name}' created (client_id: {client_id})")
                results[name] = app_id
            elif resp.status_code == 409:
                print(f"  [=] App '{name}' already exists")
                results[name] = None
            else:
                print(f"  [-] App '{name}' failed: {resp.status_code} \u2014 {resp.text[:120]}")
                results[name] = None
        except Exception as e:
            print(f"  [-] App '{name}' error: {e}")
            results[name] = None

    return results


# =============================================================================
# Phase 6: Seed Subscriptions (1 active, 1 pending)
# =============================================================================


def seed_subscriptions(
    client: httpx.Client,
    app_ids: dict[str, str | None],
    consumer_ids: dict[str, str | None] | None = None,
    plan_ids: dict[str, str | None] | None = None,
) -> dict[str, str]:
    """Create subscriptions: oasis-mobile=active, gunter-dashboard=pending."""
    results = {}
    consumer_ids = consumer_ids or {}
    plan_ids = plan_ids or {}

    print("\n=== Phase 6: Creating Subscriptions ===")

    # Active subscription: oasis-mobile -> petstore (approved)
    active_app_id = app_ids.get("oasis-mobile")
    if active_app_id:
        sub_payload: dict[str, str | None] = {
            "application_id": active_app_id,
            "application_name": "OASIS Mobile App",
            "api_id": "petstore",
            "api_name": "Petstore API",
            "api_version": "1.0.0",
            "tenant_id": DEMO_TENANT,
            "plan_id": "standard",
            "plan_name": "Standard Plan",
        }
        if consumer_ids.get("oasis-mobile-app"):
            sub_payload["consumer_id"] = consumer_ids["oasis-mobile-app"]
        if plan_ids.get("standard"):
            sub_payload["plan_id"] = plan_ids["standard"]
        try:
            resp = client.post("/v1/subscriptions", json=sub_payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                sub_id = data.get("subscription_id") or data.get("id")
                api_key = data.get("api_key", "")
                print(f"  [+] Subscription oasis-mobile -> petstore (sub: {sub_id})")
                if api_key:
                    print(f"      API Key: {api_key[:20]}...")
                results["oasis-mobile:petstore"] = "created"

                # Auto-approve
                if sub_id:
                    approve_resp = client.post(f"/v1/subscriptions/{sub_id}/approve")
                    if approve_resp.status_code == 200:
                        print("      [+] Subscription APPROVED (active)")
                        results["oasis-mobile:petstore"] = "active"
                    else:
                        print(f"      [~] Auto-approve: {approve_resp.status_code}")
            elif resp.status_code == 409:
                print("  [=] Subscription oasis-mobile -> petstore already exists")
                results["oasis-mobile:petstore"] = "exists"
            else:
                print(f"  [-] Subscription failed: {resp.status_code}")
                results["oasis-mobile:petstore"] = "failed"
        except Exception as e:
            print(f"  [-] Subscription error: {e}")
            results["oasis-mobile:petstore"] = "error"

    # Pending subscription: gunter-dashboard -> payments (left pending)
    pending_app_id = app_ids.get("gunter-dashboard")
    if pending_app_id:
        sub_payload_pending: dict[str, str | None] = {
            "application_id": pending_app_id,
            "application_name": "Gunter Analytics Dashboard",
            "api_id": "payments",
            "api_name": "Payments API",
            "api_version": "3.0.0",
            "tenant_id": DEMO_TENANT,
            "plan_id": "premium",
            "plan_name": "Premium Plan",
        }
        if consumer_ids.get("gunter-analytics"):
            sub_payload_pending["consumer_id"] = consumer_ids["gunter-analytics"]
        if plan_ids.get("premium"):
            sub_payload_pending["plan_id"] = plan_ids["premium"]
        try:
            resp = client.post("/v1/subscriptions", json=sub_payload_pending)
            if resp.status_code in (200, 201):
                data = resp.json()
                sub_id = data.get("subscription_id") or data.get("id")
                print(f"  [+] Subscription gunter-dashboard -> payments (sub: {sub_id})")
                print("      [~] Left PENDING (for demo approval flow)")
                results["gunter-dashboard:payments"] = "pending"
            elif resp.status_code == 409:
                print("  [=] Subscription gunter-dashboard -> payments already exists")
                results["gunter-dashboard:payments"] = "exists"
            else:
                print(f"  [-] Subscription failed: {resp.status_code}")
                results["gunter-dashboard:payments"] = "failed"
        except Exception as e:
            print(f"  [-] Subscription error: {e}")
            results["gunter-dashboard:payments"] = "error"

    return results


# =============================================================================
# Phase 7: Generate Metrics (sample API traffic for Grafana)
# =============================================================================


def generate_metrics(client: httpx.Client) -> dict[str, int]:
    """Make sample API calls to generate traffic metrics for Grafana dashboards."""
    results: dict[str, int] = {}

    print("\n=== Phase 7: Generating Metrics (sample API traffic) ===")

    calls = [
        ("GET", "/health/ready", None),
        ("GET", "/health/live", None),
        ("GET", "/health/startup", None),
        ("GET", "/v1/portal/apis", {"page_size": 10}),
        ("GET", "/v1/portal/apis", {"search": "petstore"}),
        ("GET", "/v1/portal/apis", {"search": "payment"}),
        ("GET", "/v1/portal/apis", {"category": "demo"}),
        ("GET", "/v1/portal/mcp-servers", None),
        ("GET", "/v1/portal/api-categories", None),
        ("GET", "/v1/portal/api-tags", None),
        ("GET", "/v1/portal/api-universes", None),
    ]

    # Multiple rounds to build up visible metrics
    rounds = 3
    total_ok = 0
    total_err = 0

    for r in range(rounds):
        for method, path, params in calls:
            try:
                if method == "GET":
                    resp = client.get(path, params=params)
                else:
                    resp = client.post(path)

                if resp.status_code < 400:
                    total_ok += 1
                else:
                    total_err += 1
            except Exception:
                total_err += 1

    print(f"  [+] {total_ok} successful calls, {total_err} errors ({rounds} rounds)")
    results["ok"] = total_ok
    results["errors"] = total_err
    return results


# =============================================================================
# Summary
# =============================================================================


def print_summary(
    apis: dict[str, bool],
    portal_count: int,
    plans: dict[str, str | None],
    consumers: dict[str, str | None],
    apps: dict[str, str | None],
    subs: dict[str, str],
    metrics: dict[str, int],
) -> None:
    """Print a summary of all seeded data."""
    print("\n" + "=" * 70)
    print("DEMO DATA SUMMARY")
    print("=" * 70)

    print("\nAPIs (portal-published):")
    for name, ok in apis.items():
        status = "[OK]" if ok else "[FAIL]"
        api_def = next((a for a in DEMO_APIS if a["name"] == name), {})
        version = api_def.get("version", "?")
        print(f"  {status} {name} v{version}")

    print(f"\nPortal catalog: {portal_count} APIs visible")

    print("\nPlans:")
    for slug, plan_id in plans.items():
        plan_def = next((p for p in DEMO_PLANS if p["slug"] == slug), {})
        rps = plan_def.get("rate_limit_per_second", "?")
        if plan_id:
            print(f"  [OK] {slug} ({rps} req/s, id: {plan_id[:8]}...)")
        else:
            print(f"  [--] {slug} ({rps} req/s)")

    print("\nConsumers:")
    for ext_id, consumer_id in consumers.items():
        if consumer_id:
            print(f"  [OK] {ext_id} (id: {consumer_id[:8]}...)")
        else:
            print(f"  [--] {ext_id}")

    print("\nApplications:")
    for name, app_id in apps.items():
        app_def = next((a for a in DEMO_APPS if a["name"] == name), {})
        expected = app_def.get("_status", "?")
        if app_id:
            print(f"  [OK] {name} (id: {app_id[:8]}...) \u2014 {expected}")
        else:
            print(f"  [--] {name} \u2014 skipped or already exists")

    print("\nSubscriptions:")
    for key, status in subs.items():
        print(f"  [{status.upper():^8s}] {key}")

    print("\nMetrics:")
    print(f"  {metrics.get('ok', 0)} API calls generated for Grafana")

    print("\n" + "=" * 70)
    print("DEMO ACCESS MATRIX")
    print("=" * 70)
    print(f"""
| Persona  | Tenant       | Role          | Demo Path                          |
|----------|-------------|---------------|------------------------------------|
| art3mis  | {DEMO_TENANT:<12s}| devops        | Portal: discover, search, test API |
| parzival | {DEMO_TENANT:<12s}| tenant-admin  | Console: approve subs, monitoring  |
| anorak   | * (all)      | cpi-admin     | Console: platform-wide admin       |

Portal APIs: petstore, account-management, payments
Plans:       standard (10 rps), premium (50 rps, approval required)
Consumers:   oasis-mobile-app (Petstore), gunter-analytics (Payments)
Active App:  oasis-mobile (subscribed to petstore, standard plan)
Pending App: gunter-dashboard (awaiting approval for payments, premium plan)
""")


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point."""
    print("=" * 70)
    print("STOA Platform \u2014 Demo Data Seeder (CAB-1061)")
    print("=" * 70)
    print(f"\nAPI URL:   {API_URL}")
    print(f"Keycloak:  {KEYCLOAK_URL}")
    print(f"Tenant:    {DEMO_TENANT}")
    print(f"User:      {SEED_USER}")

    if not SEED_PASSWORD:
        print("\n[ERROR] ANORAK_PASSWORD environment variable is required.")
        print("Usage: ANORAK_PASSWORD=<password> python scripts/seed-demo-data.py")
        return 1

    # Authenticate
    print("\n[Auth] Authenticating...")
    token = get_access_token()
    if not token:
        print("[ERROR] Authentication failed. Check credentials.")
        return 1
    print("  [+] Authenticated as cpi-admin")

    client = create_client(token)

    try:
        # Phase 0: Ensure tenant exists
        ensure_tenant(client)

        # Phase 1: APIs
        apis, used_offline = seed_apis(client)

        # Phase 2: Catalog sync (skip if offline mode — data already in catalog)
        if not used_offline:
            any_new = any(apis.values())
            if any_new:
                sync_ok = trigger_catalog_sync(client)
                if sync_ok:
                    wait_for_sync(client)
        else:
            print("\n=== Phase 2: Catalog sync SKIPPED (offline mode — data is in catalog) ===")

        # Verify portal visibility
        portal_count = verify_portal_apis(client)
        if portal_count >= 0:
            print(f"\n  [i] Portal catalog: {portal_count} APIs visible")
        else:
            print("\n  [!] Could not verify portal catalog")

        # Phase 3: Plans
        plans = seed_plans(client)

        # Phase 4: Consumers
        consumers = seed_consumers(client)

        # Phase 5: Applications
        apps = seed_applications(client)

        # Phase 6: Subscriptions
        subs = seed_subscriptions(client, apps, consumers, plans)

        # Phase 7: Metrics
        metrics = generate_metrics(client)

        # Summary
        print_summary(apis, portal_count, plans, consumers, apps, subs, metrics)

        # Exit code
        all_apis_ok = all(apis.values())
        has_portal_apis = portal_count > 0

        if all_apis_ok and has_portal_apis:
            print("[SUCCESS] Demo data seeded. Ready for presentation.")
            return 0
        elif all_apis_ok:
            print("[WARNING] APIs created but portal visibility not confirmed.")
            print("  Try: POST /v1/admin/catalog/sync to refresh portal cache.")
            return 0
        else:
            print("[WARNING] Some operations failed. Check logs above.")
            return 1

    except httpx.ConnectError:
        print(f"\n[ERROR] Could not connect to {API_URL}")
        print("Make sure the Control-Plane API is running.")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
