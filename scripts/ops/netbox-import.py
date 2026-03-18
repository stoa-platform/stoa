#!/usr/bin/env python3
"""Import STOA infrastructure into Netbox.

Usage:
    python3 scripts/ops/netbox-import.py --url https://netbox.gostoa.dev --token <TOKEN>
    python3 scripts/ops/netbox-import.py --url https://netbox.gostoa.dev --token <TOKEN> --dry-run

Supports both v1 tokens (Token <key>) and v2 tokens (Bearer nbt_<key>.<plaintext>).
"""

import argparse
import json
import ssl
import sys
import urllib.request
import urllib.error


class NetboxClient:
    """Minimal Netbox API client using stdlib only."""

    def __init__(self, url: str, token: str, dry_run: bool = False) -> None:
        self.base = url.rstrip("/") + "/api"
        self.dry_run = dry_run
        # v2 tokens start with nbt_ prefix
        if token.startswith("nbt_"):
            self._auth = f"Bearer {token}"
        else:
            self._auth = f"Token {token}"
        self._ctx = ssl.create_default_context()

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, context=self._ctx) as resp:
            return json.loads(resp.read().decode()) if resp.status != 204 else {}

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, data: dict) -> dict:
        return self._request("POST", path, data)

    def get_or_create(self, path: str, data: dict, lookup_field: str = "name") -> dict:
        """Get existing object by lookup_field or create it."""
        lookup_val = data[lookup_field]
        results = self.get(f"{path}?{lookup_field}={lookup_val}")
        if results.get("count", 0) > 0:
            obj = results["results"][0]
            print(f"  EXISTS: {path} '{lookup_val}' (id={obj['id']})")
            return obj
        if self.dry_run:
            print(f"  DRY-RUN: would create {path} '{lookup_val}'")
            return {"id": 0, "name": lookup_val}
        obj = self.post(path, data)
        print(f"  CREATED: {path} '{lookup_val}' (id={obj['id']})")
        return obj

    def get_or_create_by_slug(self, path: str, data: dict) -> dict:
        """Get existing object by slug or create it."""
        slug = data["slug"]
        results = self.get(f"{path}?slug={slug}")
        if results.get("count", 0) > 0:
            obj = results["results"][0]
            print(f"  EXISTS: {path} '{slug}' (id={obj['id']})")
            return obj
        if self.dry_run:
            print(f"  DRY-RUN: would create {path} '{slug}'")
            return {"id": 0, "slug": slug}
        obj = self.post(path, data)
        print(f"  CREATED: {path} '{slug}' (id={obj['id']})")
        return obj


def import_all(client: NetboxClient) -> None:
    """Import the full STOA infrastructure."""

    # --- Manufacturers ---
    print("\n=== Manufacturers ===")
    manufacturers = {}
    for name, slug in [("OVH", "ovh"), ("Hetzner", "hetzner"), ("Contabo", "contabo")]:
        m = client.get_or_create_by_slug(
            "/dcim/manufacturers/", {"name": name, "slug": slug}
        )
        manufacturers[slug] = m["id"]

    # --- Sites ---
    print("\n=== Sites ===")
    sites = {}
    site_defs = [
        {"name": "OVH GRA9 (MKS Prod)", "slug": "ovh-gra9", "status": "active"},
        {"name": "Hetzner NBG1 (K3s Staging)", "slug": "hetzner-nbg1", "status": "decommissioned"},
        {"name": "Contabo NUE (HEGEMON Workers)", "slug": "contabo-nue", "status": "active"},
        {"name": "OVH GRA-VPS (Gateways + Tools)", "slug": "ovh-gra-vps", "status": "active"},
    ]
    for s in site_defs:
        obj = client.get_or_create_by_slug("/dcim/sites/", s)
        sites[s["slug"]] = obj["id"]

    # --- Device Roles ---
    print("\n=== Device Roles ===")
    roles = {}
    role_defs = [
        {"name": "Kubernetes Node", "slug": "k8s-node", "color": "0077b6"},
        {"name": "VPS Gateway", "slug": "vps-gateway", "color": "f77f00"},
        {"name": "VPS Tools", "slug": "vps-tools", "color": "7209b7"},
        {"name": "Worker Agent", "slug": "worker-agent", "color": "e63946"},
    ]
    for r in role_defs:
        obj = client.get_or_create_by_slug("/dcim/device-roles/", r)
        roles[r["slug"]] = obj["id"]

    # --- Device Types ---
    print("\n=== Device Types ===")
    types = {}
    type_defs = [
        {
            "manufacturer": manufacturers["ovh"],
            "model": "B2-15",
            "slug": "ovh-b2-15",
            "u_height": 0,
            "is_full_depth": False,
        },
        {
            "manufacturer": manufacturers["hetzner"],
            "model": "CX32",
            "slug": "hetzner-cx32",
            "u_height": 0,
            "is_full_depth": False,
        },
        {
            "manufacturer": manufacturers["contabo"],
            "model": "VPS L",
            "slug": "contabo-vps-l",
            "u_height": 0,
            "is_full_depth": False,
        },
        {
            "manufacturer": manufacturers["ovh"],
            "model": "VPS Value",
            "slug": "ovh-vps-value",
            "u_height": 0,
            "is_full_depth": False,
        },
    ]
    for t in type_defs:
        obj = client.get_or_create_by_slug("/dcim/device-types/", t)
        types[t["slug"]] = obj["id"]

    # --- Devices ---
    print("\n=== Devices ===")
    devices = [
        # OVH MKS Prod (3 nodes)
        {
            "name": "mks-node-1",
            "device_type": types["ovh-b2-15"],
            "role": roles["k8s-node"],
            "site": sites["ovh-gra9"],
            "status": "active",
        },
        {
            "name": "mks-node-2",
            "device_type": types["ovh-b2-15"],
            "role": roles["k8s-node"],
            "site": sites["ovh-gra9"],
            "status": "active",
        },
        {
            "name": "mks-node-3",
            "device_type": types["ovh-b2-15"],
            "role": roles["k8s-node"],
            "site": sites["ovh-gra9"],
            "status": "active",
        },
        # Hetzner K3s Staging
        {
            "name": "k3s-master-1",
            "device_type": types["hetzner-cx32"],
            "role": roles["k8s-node"],
            "site": sites["hetzner-nbg1"],
            "status": "active",
        },
        # Contabo HEGEMON Workers
        {
            "name": "hegemon-w1",
            "device_type": types["contabo-vps-l"],
            "role": roles["worker-agent"],
            "site": sites["contabo-nue"],
            "status": "active",
        },
        {
            "name": "hegemon-w2",
            "device_type": types["contabo-vps-l"],
            "role": roles["worker-agent"],
            "site": sites["contabo-nue"],
            "status": "active",
        },
        {
            "name": "hegemon-w3",
            "device_type": types["contabo-vps-l"],
            "role": roles["worker-agent"],
            "site": sites["contabo-nue"],
            "status": "active",
        },
        {
            "name": "hegemon-w4",
            "device_type": types["contabo-vps-l"],
            "role": roles["worker-agent"],
            "site": sites["contabo-nue"],
            "status": "active",
        },
        {
            "name": "hegemon-w5",
            "device_type": types["contabo-vps-l"],
            "role": roles["worker-agent"],
            "site": sites["contabo-nue"],
            "status": "active",
        },
        # OVH VPS Fleet
        {
            "name": "kong-vps",
            "device_type": types["ovh-vps-value"],
            "role": roles["vps-gateway"],
            "site": sites["ovh-gra-vps"],
            "status": "active",
        },
        {
            "name": "gravitee-vps",
            "device_type": types["ovh-vps-value"],
            "role": roles["vps-gateway"],
            "site": sites["ovh-gra-vps"],
            "status": "active",
        },
        {
            "name": "n8n-vps",
            "device_type": types["ovh-vps-value"],
            "role": roles["vps-tools"],
            "site": sites["ovh-gra-vps"],
            "status": "active",
        },
    ]
    for d in devices:
        client.get_or_create("/dcim/devices/", d)

    print(f"\n=== Import complete ===")
    total = (
        len(manufacturers)
        + len(site_defs)
        + len(role_defs)
        + len(type_defs)
        + len(devices)
    )
    print(f"Total objects: {total}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import STOA infra into Netbox")
    parser.add_argument("--url", required=True, help="Netbox URL")
    parser.add_argument("--token", required=True, help="API token (v1 or v2 nbt_*)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    client = NetboxClient(args.url, args.token, dry_run=args.dry_run)

    # Verify connectivity
    try:
        status = client.get("/status/")
        print(f"Connected to Netbox {status.get('netbox-version', '?')}")
    except Exception as e:
        print(f"ERROR: Cannot connect to {args.url}: {e}", file=sys.stderr)
        sys.exit(1)

    import_all(client)


if __name__ == "__main__":
    main()
