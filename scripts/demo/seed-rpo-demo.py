#!/usr/bin/env python3
"""
Ready Player One Demo Setup for STOA Platform.

Creates tenants, users, and subscriptions for the RPO-themed demo.
Presentation date: January 20, 2026

Usage:
    # With default settings (production)
    python scripts/demo/seed-rpo-demo.py

    # With custom URLs
    CONTROL_PLANE_URL=https://api.stoa.cab-i.com \
    KEYCLOAK_URL=https://auth.stoa.cab-i.com \
    python scripts/demo/seed-rpo-demo.py

Theme: Ready Player One
- high-five: Parzival's resistance team
- ioi: Innovative Online Industries (antagonists)
- oasis: Platform administration (Halliday)
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
API_URL = os.getenv("CONTROL_PLANE_URL", "https://api.stoa.cab-i.com")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.stoa.cab-i.com")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# =============================================================================
# RPO Demo Data
# =============================================================================

RPO_TENANTS = [
    {
        "id": "high-five",
        "name": "High Five",
        "display_name": "High Five - The Resistance",
        "description": "Parzival's team of elite gunters hunting for Halliday's Easter Egg",
        "owner_email": "parzival@highfive.oasis",
    },
    {
        "id": "ioi",
        "name": "IOI",
        "display_name": "Innovative Online Industries",
        "description": "The corporate antagonist seeking to monetize the OASIS",
        "owner_email": "sorrento@ioi.corp",
    },
    {
        "id": "oasis",
        "name": "OASIS",
        "display_name": "OASIS Platform Administration",
        "description": "Platform-level administration by Halliday's legacy",
        "owner_email": "halliday@oasis.admin",
    },
]

RPO_USERS = [
    {
        "username": "parzival",
        "email": "parzival@highfive.oasis",
        "firstName": "Wade",
        "lastName": "Watts",
        "tenant_id": "high-five",
        "roles": ["tenant-admin"],
        "password": "Wade2045!",
    },
    {
        "username": "sorrento",
        "email": "sorrento@ioi.corp",
        "firstName": "Nolan",
        "lastName": "Sorrento",
        "tenant_id": "ioi",
        "roles": ["tenant-admin"],
        "password": "Ioi2045!",
    },
    {
        "username": "halliday",
        "email": "halliday@oasis.admin",
        "firstName": "James",
        "lastName": "Halliday",
        "tenant_id": "oasis",
        "roles": ["cpi-admin"],
        "password": "Easter2045!",
    },
]

# User-Tenant assignments (for role binding)
USER_ASSIGNMENTS = [
    {"tenant_id": "high-five", "user_id": "parzival", "role": "admin"},
    {"tenant_id": "ioi", "user_id": "sorrento", "role": "admin"},
    {"tenant_id": "oasis", "user_id": "halliday", "role": "admin"},
]

# =============================================================================
# Keycloak Functions
# =============================================================================

def get_keycloak_admin_token() -> str | None:
    """Get admin access token from Keycloak master realm."""
    if not ADMIN_PASSWORD:
        print("  [!] ADMIN_PASSWORD not set, skipping Keycloak operations")
        return None

    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"

    try:
        resp = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            print(f"  [-] Failed to get Keycloak admin token: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  [-] Could not connect to Keycloak: {e}")
        return None


def create_keycloak_user(token: str, user: dict) -> bool:
    """Create a user in Keycloak."""
    users_url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"

    user_payload = {
        "username": user["username"],
        "email": user["email"],
        "firstName": user["firstName"],
        "lastName": user["lastName"],
        "enabled": True,
        "emailVerified": True,
        "attributes": {
            "tenant_id": [user["tenant_id"]],
        },
        "credentials": [
            {
                "type": "password",
                "value": user["password"],
                "temporary": False,
            }
        ],
    }

    try:
        resp = httpx.post(
            users_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=user_payload,
            timeout=10.0,
        )
        if resp.status_code == 201:
            return True
        elif resp.status_code == 409:
            print(f"      (already exists)")
            return True
        else:
            print(f"      Error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"      Error: {e}")
        return False


def get_user_id(token: str, username: str) -> str | None:
    """Get Keycloak user ID by username."""
    url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users?username={username}&exact=true"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            users = resp.json()
            if users:
                return users[0]["id"]
        return None
    except Exception:
        return None


def assign_realm_role(token: str, user_id: str, role_name: str) -> bool:
    """Assign a realm role to a user."""
    # Get role ID
    roles_url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/roles/{role_name}"
    try:
        resp = httpx.get(
            roles_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        if resp.status_code != 200:
            print(f"      Role '{role_name}' not found")
            return False
        role = resp.json()

        # Assign role
        assign_url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/role-mappings/realm"
        resp = httpx.post(
            assign_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=[role],
            timeout=10.0,
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"      Error assigning role: {e}")
        return False


def seed_keycloak_users(token: str) -> dict[str, bool]:
    """Create all RPO users in Keycloak."""
    results = {}

    print("\n=== Creating Keycloak Users ===")
    for user in RPO_USERS:
        print(f"  [+] Creating user '{user['username']}'...")
        success = create_keycloak_user(token, user)
        results[user["username"]] = success

        if success:
            # Assign roles
            user_id = get_user_id(token, user["username"])
            if user_id:
                for role in user["roles"]:
                    print(f"      Assigning role '{role}'...")
                    assign_realm_role(token, user_id, role)

    return results


# =============================================================================
# Control Plane API Functions
# =============================================================================

def get_api_token() -> str | None:
    """Get access token for Control Plane API."""
    if not ADMIN_PASSWORD:
        return None

    token_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

    try:
        resp = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": "control-plane-ui",
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            print(f"  [-] Failed to get API token: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  [-] Could not get API token: {e}")
        return None


def create_client(token: str | None) -> httpx.Client:
    """Create HTTP client with optional auth."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_URL, headers=headers, timeout=30.0)


def seed_tenants(client: httpx.Client) -> dict[str, bool]:
    """Create RPO tenants."""
    results = {}

    print("\n=== Creating Tenants ===")
    for tenant in RPO_TENANTS:
        tenant_payload = {
            "name": tenant["id"],
            "display_name": tenant["display_name"],
            "description": tenant["description"],
            "owner_email": tenant["owner_email"],
        }
        try:
            resp = client.post("/v1/tenants", json=tenant_payload)
            if resp.status_code in (200, 201):
                print(f"  [+] Tenant '{tenant['id']}' created")
                results[tenant["id"]] = True
            elif resp.status_code == 409:
                print(f"  [=] Tenant '{tenant['id']}' already exists")
                results[tenant["id"]] = True
            else:
                print(f"  [-] Tenant '{tenant['id']}' failed: {resp.status_code} - {resp.text[:100]}")
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


# =============================================================================
# Summary
# =============================================================================

def print_summary(
    keycloak_users: dict[str, bool],
    tenants: dict[str, bool],
    assignments: dict[str, bool],
) -> None:
    """Print summary of seeded data."""
    print("\n" + "=" * 70)
    print("READY PLAYER ONE DEMO - SUMMARY")
    print("=" * 70)

    print("\nKeycloak Users:")
    for username, success in keycloak_users.items():
        status = "[OK]" if success else "[FAIL]"
        user = next((u for u in RPO_USERS if u["username"] == username), None)
        if user:
            print(f"  {status} {username} ({user['firstName']} {user['lastName']}) - {user['email']}")

    print("\nTenants:")
    for tenant_id, success in tenants.items():
        status = "[OK]" if success else "[FAIL]"
        tenant = next((t for t in RPO_TENANTS if t["id"] == tenant_id), None)
        if tenant:
            print(f"  {status} {tenant_id} - {tenant['display_name']}")

    print("\nUser Assignments:")
    for key, success in assignments.items():
        user_id, tenant_id = key.split("@")
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {user_id} -> {tenant_id}")

    print("\n" + "=" * 70)
    print("ACCESS MATRIX - Ready Player One Demo")
    print("=" * 70)
    print("""
| User     | Tenant     | Role          | MCP Tools Access                    |
|----------|------------|---------------|-------------------------------------|
| parzival | high-five  | tenant-admin  | artifact_search, scoreboard_tracker |
| sorrento | ioi        | tenant-admin  | sixers_inventory, surveillance_feed |
| halliday | oasis      | cpi-admin     | ALL (platform admin)                |

Demo Credentials:
  - parzival / Wade2045!   (High Five - resistance)
  - sorrento / Ioi2045!    (IOI - corporation)
  - halliday / Easter2045! (OASIS - platform admin)

Demo Flow:
  1. Portal (Parzival): See all tools, can only use High Five tools
  2. Console (Sorrento): Approve/reject cross-tenant subscription requests
  3. Grafana (Halliday): Platform-wide observability
""")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    """Main entry point."""
    print("=" * 70)
    print("STOA Platform - Ready Player One Demo Setup")
    print("=" * 70)
    print(f"\nAPI URL: {API_URL}")
    print(f"Keycloak: {KEYCLOAK_URL}")
    print(f"Realm: {KEYCLOAK_REALM}")

    # Initialize results
    keycloak_users = {}
    tenants = {}
    assignments = {}

    # Step 1: Keycloak users
    print("\n[Phase 1] Authenticating to Keycloak...")
    kc_token = get_keycloak_admin_token()
    if kc_token:
        print("  [+] Keycloak admin authenticated")
        keycloak_users = seed_keycloak_users(kc_token)
    else:
        print("  [!] Skipping Keycloak user creation (no admin password)")
        for user in RPO_USERS:
            keycloak_users[user["username"]] = False

    # Step 2: Get API token
    print("\n[Phase 2] Authenticating to Control Plane API...")
    api_token = get_api_token()
    if api_token:
        print("  [+] API authenticated")
    else:
        print("  [!] Running API calls without authentication")

    # Step 3: Create tenants
    client = create_client(api_token)
    try:
        tenants = seed_tenants(client)
        assignments = seed_user_assignments(client)
    finally:
        client.close()

    # Print summary
    print_summary(keycloak_users, tenants, assignments)

    # Check for failures
    all_ok = (
        all(keycloak_users.values())
        and all(tenants.values())
        and all(assignments.values())
    )

    if all_ok:
        print("\n[SUCCESS] Ready Player One demo data seeded successfully!")
        return 0
    else:
        print("\n[WARNING] Some operations failed. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
