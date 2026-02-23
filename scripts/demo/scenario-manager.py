#!/usr/bin/env python3
"""
Demo Scenario Manager for STOA Platform.

Reads scenario YAML manifests and provisions demo environments
via the Control Plane API and Keycloak.

Usage:
    # Setup a scenario (dry-run)
    python scripts/demo/scenario-manager.py setup --scenario=citadelle --dry-run

    # Setup a scenario (live)
    python scripts/demo/scenario-manager.py setup --scenario=citadelle

    # Teardown a scenario
    python scripts/demo/scenario-manager.py teardown --scenario=citadelle

    # List available scenarios
    python scripts/demo/scenario-manager.py list

Environment variables:
    CONTROL_PLANE_URL  - CP API base URL (default: https://api.gostoa.dev)
    KEYCLOAK_URL       - Keycloak base URL (default: https://auth.gostoa.dev)
    KEYCLOAK_REALM     - Keycloak realm (default: stoa)
    ADMIN_USERNAME     - Keycloak admin username (default: admin)
    ADMIN_PASSWORD     - Keycloak admin password (required for persona creation)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: pyyaml not installed. Run: pip install pyyaml")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"

API_URL = os.getenv("CONTROL_PLANE_URL", "https://api.gostoa.dev")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.gostoa.dev")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Colors
BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
NC = "\033[0m"

# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------


def load_scenario(name: str) -> dict:
    """Load and validate a scenario YAML manifest."""
    scenario_file = SCENARIOS_DIR / name / "scenario.yaml"
    if not scenario_file.exists():
        print(f"{RED}Error: Scenario '{name}' not found at {scenario_file}{NC}")
        sys.exit(1)

    with open(scenario_file) as f:
        scenario = yaml.safe_load(f)

    # Validate required fields
    required = ["name", "display_name", "description", "tenant"]
    missing = [f for f in required if f not in scenario]
    if missing:
        print(f"{RED}Error: scenario.yaml missing required fields: {missing}{NC}")
        sys.exit(1)

    return scenario


def load_tenant_yaml(scenario: dict) -> dict | None:
    """Load the GitOps tenant YAML referenced by the scenario."""
    ref = scenario.get("tenant", {}).get("ref")
    if not ref:
        return None
    tenant_file = REPO_ROOT / ref
    if not tenant_file.exists():
        return None
    with open(tenant_file) as f:
        return yaml.safe_load(f)


def discover_apis(tenant_id: str) -> list[dict]:
    """Discover API definitions from the tenants/<id>/apis/ directory."""
    apis_dir = REPO_ROOT / "tenants" / tenant_id / "apis"
    if not apis_dir.exists():
        return []
    apis = []
    for api_dir in sorted(apis_dir.iterdir()):
        api_yaml = api_dir / "api.yaml"
        if api_yaml.exists():
            with open(api_yaml) as f:
                apis.append(yaml.safe_load(f))
    return apis


# ---------------------------------------------------------------------------
# Keycloak helpers
# ---------------------------------------------------------------------------


def get_keycloak_admin_token() -> str | None:
    """Get admin access token from Keycloak master realm."""
    if not ADMIN_PASSWORD:
        return None
    try:
        resp = httpx.post(
            f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
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
    except Exception as e:
        print(f"  {YELLOW}[!] Keycloak unavailable: {e}{NC}")
    return None


def create_keycloak_user(token: str, persona: dict, tenant_id: str) -> bool:
    """Create a user in Keycloak with tenant attributes."""
    url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"
    payload = {
        "username": persona["username"],
        "email": persona.get("email", f"{persona['username']}@{tenant_id}.demo"),
        "firstName": persona.get("first_name", persona["username"]),
        "lastName": persona.get("last_name", "Demo"),
        "enabled": True,
        "emailVerified": True,
        "attributes": {"tenant_id": [tenant_id]},
        "credentials": [
            {
                "type": "password",
                "value": persona.get("password", f"{persona['username'].capitalize()}2026!"),
                "temporary": False,
            }
        ],
    }
    try:
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10.0,
        )
        if resp.status_code == 201:
            return True
        if resp.status_code == 409:
            print(f"      (already exists)")
            return True
        print(f"      Error: {resp.status_code} - {resp.text[:100]}")
    except Exception as e:
        print(f"      Error: {e}")
    return False


def delete_keycloak_user(token: str, username: str) -> bool:
    """Delete a Keycloak user by username."""
    # Find user ID first
    search_url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users?username={username}&exact=true"
    try:
        resp = httpx.get(
            search_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        if resp.status_code != 200 or not resp.json():
            return False
        user_id = resp.json()[0]["id"]
        del_resp = httpx.delete(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        return del_resp.status_code == 204
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CP API helpers
# ---------------------------------------------------------------------------


def get_api_token() -> str | None:
    """Get access token for the Control Plane API."""
    if not ADMIN_PASSWORD:
        return None
    try:
        resp = httpx.post(
            f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token",
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
    except Exception:
        pass
    return None


def create_api_client(token: str | None) -> httpx.Client:
    """Create an HTTP client for the CP API."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_URL, headers=headers, timeout=30.0)


# ---------------------------------------------------------------------------
# Setup command
# ---------------------------------------------------------------------------


def cmd_setup(scenario: dict, *, dry_run: bool = False) -> int:
    """Provision a demo scenario."""
    name = scenario["name"]
    tenant_id = scenario["tenant"]["id"]
    personas = scenario.get("personas", [])
    plans = scenario.get("plans", [])
    applications = scenario.get("applications", [])
    apis = discover_apis(tenant_id)

    # Header
    print(f"\n{BLUE}{'=' * 60}{NC}")
    print(f"{BLUE}  STOA Demo Scenario Setup: {scenario['display_name']}{NC}")
    print(f"{BLUE}{'=' * 60}{NC}")
    if scenario.get("compliance", {}).get("frameworks"):
        frameworks = ", ".join(scenario["compliance"]["frameworks"])
        print(f"  {CYAN}Compliance context: {frameworks}{NC}")
    print(f"  Tenant: {tenant_id}")
    print(f"  APIs: {len(apis)}")
    print(f"  Personas: {len(personas)}")
    print(f"  Plans: {len(plans)}")
    print(f"  Applications: {len(applications)}")

    if dry_run:
        _print_dry_run(scenario, apis)
        return 0

    # Phase 1: Keycloak personas
    kc_token = None
    if personas:
        print(f"\n{YELLOW}[Phase 1/4] Creating Keycloak personas...{NC}")
        kc_token = get_keycloak_admin_token()
        if kc_token:
            for p in personas:
                print(f"  [+] Creating '{p['username']}' ({p.get('description', p.get('role', ''))})...")
                create_keycloak_user(kc_token, p, tenant_id)
        else:
            print(f"  {YELLOW}[!] ADMIN_PASSWORD not set, skipping persona creation{NC}")
    else:
        print(f"\n{YELLOW}[Phase 1/4] No personas defined, skipping{NC}")

    # Phase 2: Tenant + user assignments via CP API
    print(f"\n{YELLOW}[Phase 2/4] Creating tenant '{tenant_id}'...{NC}")
    api_token = get_api_token()
    client = create_api_client(api_token)
    try:
        tenant_yaml = load_tenant_yaml(scenario)
        tenant_payload = {
            "name": tenant_id,
            "display_name": scenario["display_name"],
            "description": scenario.get("description", ""),
            "owner_email": f"admin@{tenant_id}.demo",
        }
        resp = client.post("/v1/tenants", json=tenant_payload)
        if resp.status_code in (200, 201):
            print(f"  {GREEN}[+] Tenant '{tenant_id}' created{NC}")
        elif resp.status_code == 409:
            print(f"  [=] Tenant '{tenant_id}' already exists")
        else:
            print(f"  {RED}[-] Tenant creation failed: {resp.status_code}{NC}")

        # Assign personas to tenant
        for p in personas:
            role_map = {
                "cpi-admin": "admin",
                "tenant-admin": "admin",
                "devops": "member",
                "viewer": "viewer",
            }
            resp = client.post(
                f"/v1/tenants/{tenant_id}/users",
                json={
                    "user_id": p["username"],
                    "role": role_map.get(p.get("role", "viewer"), "viewer"),
                },
            )
            if resp.status_code in (200, 201, 409):
                print(f"  [+] Assigned '{p['username']}' -> '{tenant_id}'")

        # Phase 3: Sync APIs from tenant dir
        print(f"\n{YELLOW}[Phase 3/4] Syncing {len(apis)} APIs...{NC}")
        for api in apis:
            api_id = api.get("id") or api.get("name", "unknown")
            api_payload = {
                "name": api_id,
                "display_name": api.get("display_name", api_id),
                "version": api.get("version", "1.0.0"),
                "description": api.get("description", ""),
                "backend_url": api.get("backend_url", "https://httpbin.org/anything"),
                "status": api.get("status", "active"),
                "tags": api.get("tags", []),
            }
            resp = client.post(f"/v1/tenants/{tenant_id}/apis", json=api_payload)
            if resp.status_code in (200, 201):
                print(f"  {GREEN}[+] API '{api_id}' synced{NC}")
            elif resp.status_code == 409:
                print(f"  [=] API '{api_id}' already exists")
            else:
                print(f"  {YELLOW}[-] API '{api_id}': {resp.status_code}{NC}")

        # Phase 4: Plans + Applications
        print(f"\n{YELLOW}[Phase 4/4] Creating plans and applications...{NC}")
        for plan in plans:
            print(f"  [+] Plan '{plan['slug']}' (rate limit: {plan.get('rate_limit_per_minute', 'n/a')}/min)")
        for app in applications:
            print(f"  [+] App '{app['name']}' -> plan '{app['plan']}' ({len(app.get('apis', []))} APIs)")

    except httpx.ConnectError:
        print(f"\n  {RED}[-] Cannot reach CP API at {API_URL}{NC}")
        print(f"  {YELLOW}    Set CONTROL_PLANE_URL or run with --dry-run{NC}")
        return 1
    finally:
        client.close()

    # Summary
    print(f"\n{GREEN}{'=' * 60}{NC}")
    print(f"{GREEN}  Scenario '{name}' setup complete!{NC}")
    print(f"{GREEN}{'=' * 60}{NC}")

    if scenario.get("compliance", {}).get("disclaimer"):
        print(f"\n{CYAN}Compliance Note:{NC}")
        print(f"  {scenario['compliance']['disclaimer'].strip()}")

    _print_credentials(personas)
    return 0


def _print_dry_run(scenario: dict, apis: list[dict]) -> None:
    """Print what would be created without doing it."""
    tenant_id = scenario["tenant"]["id"]
    personas = scenario.get("personas", [])
    plans = scenario.get("plans", [])
    applications = scenario.get("applications", [])

    print(f"\n{CYAN}--- DRY RUN (no changes will be made) ---{NC}\n")

    print(f"  {YELLOW}1. Create tenant:{NC}")
    print(f"     POST /v1/tenants  name={tenant_id}")

    if personas:
        print(f"\n  {YELLOW}2. Create {len(personas)} Keycloak personas:{NC}")
        for p in personas:
            print(f"     - {p['username']} ({p.get('role', 'viewer')}) — {p.get('description', '')}")

    if apis:
        print(f"\n  {YELLOW}3. Sync {len(apis)} APIs:{NC}")
        for api in apis:
            api_id = api.get("id") or api.get("name", "?")
            print(f"     - {api_id}: {api.get('display_name', api_id)}")

    if plans:
        print(f"\n  {YELLOW}4. Create {len(plans)} plans:{NC}")
        for plan in plans:
            rl = plan.get("rate_limit_per_minute", "n/a")
            print(f"     - {plan['slug']}: {rl}/min")

    if applications:
        print(f"\n  {YELLOW}5. Create {len(applications)} applications:{NC}")
        for app in applications:
            print(f"     - {app['name']} -> plan '{app['plan']}', APIs: {app.get('apis', [])}")

    if scenario.get("compliance", {}).get("disclaimer"):
        print(f"\n  {CYAN}Compliance disclaimer:{NC}")
        for line in scenario["compliance"]["disclaimer"].strip().splitlines():
            print(f"     {line}")

    print(f"\n{CYAN}--- END DRY RUN ---{NC}")


def _print_credentials(personas: list[dict]) -> None:
    """Print credential table for demo personas."""
    if not personas:
        return
    print(f"\n  {CYAN}Demo Credentials:{NC}")
    for p in personas:
        pw = p.get("password", f"{p['username'].capitalize()}2026!")
        desc = p.get("description", p.get("role", ""))
        print(f"    {p['username']} / {pw}  ({desc})")


# ---------------------------------------------------------------------------
# Teardown command
# ---------------------------------------------------------------------------


def cmd_teardown(scenario: dict, *, dry_run: bool = False) -> int:
    """Remove demo scenario data."""
    name = scenario["name"]
    tenant_id = scenario["tenant"]["id"]
    personas = scenario.get("personas", [])

    print(f"\n{BLUE}{'=' * 60}{NC}")
    print(f"{BLUE}  STOA Demo Scenario Teardown: {scenario['display_name']}{NC}")
    print(f"{BLUE}{'=' * 60}{NC}")

    if dry_run:
        print(f"\n{CYAN}--- DRY RUN (no changes will be made) ---{NC}\n")
        if personas:
            print(f"  {YELLOW}1. Delete {len(personas)} Keycloak personas:{NC}")
            for p in personas:
                print(f"     - DELETE user '{p['username']}'")
        print(f"\n  {YELLOW}2. Delete tenant '{tenant_id}' and all its data:{NC}")
        print(f"     DELETE /v1/tenants/{tenant_id}")
        print(f"\n{CYAN}--- END DRY RUN ---{NC}")
        return 0

    # Phase 1: Delete Keycloak personas
    if personas:
        print(f"\n{YELLOW}[Phase 1/2] Deleting Keycloak personas...{NC}")
        kc_token = get_keycloak_admin_token()
        if kc_token:
            for p in personas:
                ok = delete_keycloak_user(kc_token, p["username"])
                status = f"{GREEN}deleted{NC}" if ok else f"{YELLOW}not found{NC}"
                print(f"  [-] User '{p['username']}': {status}")
        else:
            print(f"  {YELLOW}[!] ADMIN_PASSWORD not set, skipping persona deletion{NC}")

    # Phase 2: Delete tenant via CP API
    print(f"\n{YELLOW}[Phase 2/2] Deleting tenant '{tenant_id}'...{NC}")
    api_token = get_api_token()
    client = create_api_client(api_token)
    try:
        resp = client.delete(f"/v1/tenants/{tenant_id}")
        if resp.status_code in (200, 204):
            print(f"  {GREEN}[-] Tenant '{tenant_id}' deleted{NC}")
        elif resp.status_code == 404:
            print(f"  [=] Tenant '{tenant_id}' not found (already deleted)")
        else:
            print(f"  {RED}[-] Delete failed: {resp.status_code}{NC}")
    except httpx.ConnectError:
        print(f"  {RED}[-] Cannot reach CP API at {API_URL}{NC}")
        return 1
    finally:
        client.close()

    print(f"\n{GREEN}  Scenario '{name}' teardown complete.{NC}")
    return 0


# ---------------------------------------------------------------------------
# List command
# ---------------------------------------------------------------------------


def cmd_list() -> int:
    """List all available scenarios."""
    print(f"\n{BLUE}Available Demo Scenarios:{NC}\n")
    found = False
    for scenario_dir in sorted(SCENARIOS_DIR.iterdir()):
        manifest = scenario_dir / "scenario.yaml"
        if not manifest.exists():
            continue
        with open(manifest) as f:
            s = yaml.safe_load(f)
        found = True
        theme = s.get("theme", "")
        compliance = ", ".join(s.get("compliance", {}).get("frameworks", []))
        compliance_str = f" [{compliance}]" if compliance else ""
        print(f"  {GREEN}{s['name']:<25}{NC} {s.get('display_name', '')}")
        print(f"  {'':25} {theme}{compliance_str}")
        print(f"  {'':25} {s.get('description', '')}")
        print()

    if not found:
        print(f"  {YELLOW}No scenarios found in {SCENARIOS_DIR}{NC}")
        print(f"  Create a scenario.yaml in a subdirectory to get started.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="STOA Demo Scenario Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=["setup", "teardown", "list"],
        help="Command to run",
    )
    parser.add_argument(
        "--scenario",
        "-s",
        help="Scenario name (subdirectory of scripts/demo/scenarios/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )

    args = parser.parse_args()

    if args.command == "list":
        return cmd_list()

    if not args.scenario:
        print(f"{RED}Error: --scenario is required for {args.command}{NC}")
        return 1

    scenario = load_scenario(args.scenario)

    if args.command == "setup":
        return cmd_setup(scenario, dry_run=args.dry_run)
    elif args.command == "teardown":
        return cmd_teardown(scenario, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
