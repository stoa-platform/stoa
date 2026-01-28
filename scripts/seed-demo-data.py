#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
CAB-279: Seed demo data for STOA MVP presentation.

This script creates demo tenants and subscriptions via the Control-Plane API.
It uses the E2E test users from CAB-238.

Usage:
    # With default settings (localhost)
    python scripts/seed-demo-data.py

    # With custom API URL
    CONTROL_PLANE_URL=https://api.gostoa.dev python scripts/seed-demo-data.py

    # With authentication
    KEYCLOAK_URL=https://auth.gostoa.dev \
    ADMIN_USERNAME=e2e-admin \
    ADMIN_PASSWORD=Admin123! \
    python scripts/seed-demo-data.py
"""

import os
import sys
import json
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# Configuration
API_URL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8180")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "e2e-admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!")

# Demo Tenants
TENANTS = [
    {
        "id": "team-alpha",
        "name": "Team Alpha - Sales & Finance",
        "description": "Demo tenant for CRM and Billing tools",
        "contact_email": "alice@demo.stoa.io",
        "quota": {
            "max_subscriptions": 10,
            "max_requests_per_day": 10000,
        },
    },
    {
        "id": "team-beta",
        "name": "Team Beta - Operations",
        "description": "Demo tenant for Inventory and Notifications tools",
        "contact_email": "bob@demo.stoa.io",
        "quota": {
            "max_subscriptions": 10,
            "max_requests_per_day": 10000,
        },
    },
]

# Demo Subscriptions
SUBSCRIPTIONS = [
    # Team Alpha subscriptions
    {
        "tenant_id": "team-alpha",
        "api_id": "crm-search",
        "subscriber_id": "e2e-tenant-admin",
        "application_id": "demo-app-alpha",
        "plan_id": "standard",
    },
    {
        "tenant_id": "team-alpha",
        "api_id": "billing-invoice",
        "subscriber_id": "e2e-tenant-admin",
        "application_id": "demo-app-alpha",
        "plan_id": "standard",
    },
    # Team Beta subscriptions
    {
        "tenant_id": "team-beta",
        "api_id": "inventory-lookup",
        "subscriber_id": "e2e-devops",
        "application_id": "demo-app-beta",
        "plan_id": "standard",
    },
    {
        "tenant_id": "team-beta",
        "api_id": "notifications-send",
        "subscriber_id": "e2e-devops",
        "application_id": "demo-app-beta",
        "plan_id": "standard",
    },
]

# User-Tenant assignments
USER_ASSIGNMENTS = [
    {"tenant_id": "team-alpha", "user_id": "e2e-tenant-admin", "role": "admin"},
    {"tenant_id": "team-alpha", "user_id": "e2e-viewer", "role": "viewer"},
    {"tenant_id": "team-beta", "user_id": "e2e-devops", "role": "admin"},
    {"tenant_id": "team-beta", "user_id": "e2e-viewer", "role": "viewer"},
]


def get_access_token() -> str | None:
    """Get admin access token from Keycloak."""
    token_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

    try:
        resp = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": "stoa-admin",
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            print(f"Warning: Failed to get token: {resp.status_code}")
            return None
    except Exception as e:
        print(f"Warning: Could not connect to Keycloak: {e}")
        return None


def create_client(token: str | None) -> httpx.Client:
    """Create HTTP client with optional auth."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_URL, headers=headers, timeout=30.0)


def seed_tenants(client: httpx.Client) -> dict[str, bool]:
    """Create demo tenants."""
    results = {}

    print("\n=== Creating Tenants ===")
    for tenant in TENANTS:
        try:
            resp = client.post("/v1/tenants", json=tenant)
            if resp.status_code in (200, 201):
                print(f"  [+] Tenant '{tenant['id']}' created")
                results[tenant["id"]] = True
            elif resp.status_code == 409:
                print(f"  [=] Tenant '{tenant['id']}' already exists")
                results[tenant["id"]] = True
            else:
                print(f"  [-] Tenant '{tenant['id']}' failed: {resp.status_code} - {resp.text}")
                results[tenant["id"]] = False
        except Exception as e:
            print(f"  [-] Tenant '{tenant['id']}' error: {e}")
            results[tenant["id"]] = False

    return results


def seed_user_assignments(client: httpx.Client) -> dict[str, bool]:
    """Assign users to tenants."""
    results = {}

    print("\n=== Assigning Users to Tenants ===")
    for assignment in USER_ASSIGNMENTS:
        key = f"{assignment['user_id']}@{assignment['tenant_id']}"
        try:
            resp = client.post(
                f"/v1/tenants/{assignment['tenant_id']}/users",
                json={
                    "user_id": assignment["user_id"],
                    "role": assignment["role"],
                },
            )
            if resp.status_code in (200, 201):
                print(f"  [+] User '{assignment['user_id']}' -> '{assignment['tenant_id']}' ({assignment['role']})")
                results[key] = True
            elif resp.status_code == 409:
                print(f"  [=] User '{assignment['user_id']}' already in '{assignment['tenant_id']}'")
                results[key] = True
            else:
                print(f"  [-] Assignment failed: {resp.status_code}")
                results[key] = False
        except Exception as e:
            print(f"  [-] Assignment error: {e}")
            results[key] = False

    return results


def seed_subscriptions(client: httpx.Client) -> dict[str, str | None]:
    """Create tool subscriptions and return API keys."""
    results = {}

    print("\n=== Creating Subscriptions ===")
    for sub in SUBSCRIPTIONS:
        key = f"{sub['api_id']}@{sub['tenant_id']}"
        try:
            resp = client.post("/v1/subscriptions", json=sub)
            if resp.status_code in (200, 201):
                data = resp.json()
                api_key = data.get("api_key")
                print(f"  [+] Subscription '{sub['api_id']}' for '{sub['tenant_id']}'")
                if api_key:
                    print(f"      API Key: {api_key[:20]}...")
                results[key] = api_key
            elif resp.status_code == 409:
                print(f"  [=] Subscription '{sub['api_id']}' already exists for '{sub['tenant_id']}'")
                results[key] = None
            else:
                print(f"  [-] Subscription failed: {resp.status_code} - {resp.text}")
                results[key] = None
        except Exception as e:
            print(f"  [-] Subscription error: {e}")
            results[key] = None

    return results


def approve_subscriptions(client: httpx.Client) -> None:
    """Auto-approve all pending subscriptions."""
    print("\n=== Approving Pending Subscriptions ===")

    for tenant in TENANTS:
        try:
            resp = client.get(f"/v1/subscriptions/tenant/{tenant['id']}/pending")
            if resp.status_code == 200:
                pending = resp.json().get("subscriptions", [])
                for sub in pending:
                    sub_id = sub.get("id")
                    approve_resp = client.post(f"/v1/subscriptions/{sub_id}/approve")
                    if approve_resp.status_code == 200:
                        print(f"  [+] Approved subscription {sub_id}")
                    else:
                        print(f"  [-] Failed to approve {sub_id}")
        except Exception as e:
            print(f"  [-] Error checking pending: {e}")


def print_summary(
    tenants: dict[str, bool],
    assignments: dict[str, bool],
    subscriptions: dict[str, str | None],
) -> None:
    """Print summary of seeded data."""
    print("\n" + "=" * 60)
    print("DEMO DATA SUMMARY")
    print("=" * 60)

    print("\nTenants:")
    for tenant_id, success in tenants.items():
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {tenant_id}")

    print("\nUser Assignments:")
    for key, success in assignments.items():
        user, tenant = key.split("@")
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {user} -> {tenant}")

    print("\nSubscriptions:")
    for key, api_key in subscriptions.items():
        tool, tenant = key.split("@")
        if api_key:
            print(f"  [OK] {tool} ({tenant}) - Key: {api_key[:15]}...")
        else:
            print(f"  [--] {tool} ({tenant}) - No key (already existed)")

    print("\n" + "=" * 60)
    print("ACCESS MATRIX")
    print("=" * 60)
    print("""
| User             | Tenant     | Tools                              |
|------------------|------------|-------------------------------------|
| e2e-tenant-admin | team-alpha | crm-search, billing-invoice        |
| e2e-devops       | team-beta  | inventory-lookup, notifications-send|
| e2e-viewer       | both       | Read-only access                    |
| e2e-admin        | all        | Full admin access (Grafana)         |
""")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("STOA Demo Data Seeder (CAB-279)")
    print("=" * 60)
    print(f"\nAPI URL: {API_URL}")
    print(f"Keycloak: {KEYCLOAK_URL}")

    # Get auth token
    print("\nAuthenticating...")
    token = get_access_token()
    if token:
        print("  [+] Authenticated as admin")
    else:
        print("  [!] Running without authentication (may fail)")

    # Create client
    client = create_client(token)

    try:
        # Seed data
        tenants = seed_tenants(client)
        assignments = seed_user_assignments(client)
        subscriptions = seed_subscriptions(client)

        # Auto-approve subscriptions
        approve_subscriptions(client)

        # Print summary
        print_summary(tenants, assignments, subscriptions)

        # Check for failures
        all_ok = (
            all(tenants.values())
            and all(assignments.values())
        )

        if all_ok:
            print("\n[SUCCESS] Demo data seeded successfully!")
            return 0
        else:
            print("\n[WARNING] Some operations failed. Check logs above.")
            return 1

    except httpx.ConnectError:
        print(f"\n[ERROR] Could not connect to {API_URL}")
        print("Make sure the Control-Plane API is running.")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
