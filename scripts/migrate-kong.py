#!/usr/bin/env python3
"""
Kong -> STOA Migration Adapter.

Migrates Kong Gateway declarative config (kong.yaml) or Kong Admin API
into STOA platform format.

Mapping:
  Kong service    -> STOA API
  Kong route      -> STOA API endpoint (resource)
  Kong plugin     -> STOA API policy
  Kong consumer   -> STOA tenant / application
  Kong upstream   -> STOA backend target

Usage:
  python migrate-kong.py --from kong.yaml --to stoa/
  python migrate-kong.py --from http://localhost:8001 --to stoa/
  python migrate-kong.py --from kong.yaml --dry-run
  python migrate-kong.py --from kong.yaml --to stoa/ --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

log = logging.getLogger("migrate-kong")


# ---------------------------------------------------------------------------
# UX helpers
# ---------------------------------------------------------------------------


class _UX:
    """Structured terminal output with progress indicators."""

    def __init__(self, *, verbose: bool = False, quiet: bool = False) -> None:
        self.verbose = verbose
        self.quiet = quiet

    # -- public primitives --------------------------------------------------

    def step(self, icon: str, msg: str) -> None:
        if not self.quiet:
            print(f"{icon} {msg}")

    def detail(self, msg: str) -> None:
        """Only printed in --verbose mode."""
        if self.verbose:
            print(f"  {msg}")

    # -- semantic helpers ---------------------------------------------------

    def connecting(self, source: str) -> None:
        self.step("\U0001f50d", f"Loading Kong config from {source} ...")

    def found(self, services: int, routes: int, plugins: int) -> None:
        self.step(
            "\u2714",
            f"Found {services} service(s), {routes} route(s), {plugins} plugin(s)",
        )

    def migrating(self) -> None:
        self.step("\U0001f4e6", "Migrating ...")

    def migrated_api(self, kong_name: str, stoa_id: str) -> None:
        self.step("\u2714", f"{kong_name} \u2192 API `{stoa_id}`")

    def warning(self, msg: str) -> None:
        self.step("\u26a0\ufe0f", msg)

    def skipped(self, msg: str) -> None:
        self.step("\u23ed", msg)

    def manual(self, msg: str) -> None:
        self.step("\u26a0\ufe0f", msg)

    def output_files(self, yaml_path: Path, report_path: Path, stats: dict[str, int]) -> None:
        print()
        self.step("\U0001f4c4", "Output:")
        api_count = stats.get("apis", 0)
        tenant_count = stats.get("tenants", 0)
        print(f"  \u2192 {yaml_path} ({api_count} APIs, {tenant_count} tenants)")
        print(f"  \u2192 {report_path}")

    def done(self) -> None:
        print()
        self.step("\u2705", "Migration complete. Run:  stoa apply -f <output>/stoa-apis.yaml")

    def dry_run_banner(self) -> None:
        print()
        self.step("\U0001f4cb", "DRY-RUN \u2014 showing what WOULD be migrated (no files written)")
        print()

    def dry_run_summary(self, stats: dict[str, int]) -> None:
        print()
        self.step(
            "\U0001f4cb",
            f"Would produce: {stats.get('apis', 0)} APIs, "
            f"{stats.get('policies', 0)} policies, "
            f"{stats.get('tenants', 0)} tenants, "
            f"{stats.get('applications', 0)} applications",
        )
        self.step(
            "\u26a0\ufe0f",
            f"{stats.get('manual', 0)} manual action(s), "
            f"{stats.get('skipped', 0)} skipped",
        )

    def error_connection(self, url: str, err: str) -> None:
        print(f"\u274c Cannot connect to Kong at {url}", file=sys.stderr)
        print(f"  \u2192 {err}", file=sys.stderr)
        if "localhost" in url or "127.0.0.1" in url:
            print(
                "  \u2192 Is Kong running? Try: docker-compose up -d kong",
                file=sys.stderr,
            )

    def error_file(self, path: str, err: str) -> None:
        print(f"\u274c Cannot read Kong config at {path}", file=sys.stderr)
        print(f"  \u2192 {err}", file=sys.stderr)
        print(
            "  \u2192 Expected: kong.yaml (declarative config, _format_version: '3.0')",
            file=sys.stderr,
        )

    def error_generic(self, err: str) -> None:
        print(f"\u274c {err}", file=sys.stderr)


ux = _UX()  # module-level singleton, reconfigured in main()


# ---------------------------------------------------------------------------
# Kong Config Loaders
# ---------------------------------------------------------------------------


def load_from_file(path: str) -> dict[str, Any]:
    """Load Kong declarative config from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with p.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid Kong config: expected mapping, got {type(data).__name__}")
    return data


def load_from_admin_api(url: str) -> dict[str, Any]:
    """Load Kong config from Admin API (http://host:8001)."""
    import urllib.error
    import urllib.request

    def _get(endpoint: str) -> dict[str, Any]:
        full = f"{url.rstrip('/')}{endpoint}"
        log.debug("GET %s", full)
        resp = urllib.request.urlopen(full, timeout=10)  # noqa: S310
        return json.loads(resp.read())

    try:
        _get("/")  # connectivity check
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(str(exc)) from exc

    services_resp = _get("/services")
    services_data = services_resp.get("data", [])

    services = []
    for svc in services_data:
        svc_id = svc.get("id", svc.get("name"))

        routes_resp = _get(f"/services/{svc_id}/routes")
        svc["routes"] = routes_resp.get("data", [])

        plugins_resp = _get(f"/services/{svc_id}/plugins")
        svc["plugins"] = plugins_resp.get("data", [])

        services.append(svc)

    upstreams_resp = _get("/upstreams")
    upstreams = upstreams_resp.get("data", [])
    for ups in upstreams:
        ups_name = ups.get("name") or ups.get("id")
        targets_resp = _get(f"/upstreams/{ups_name}/targets")
        ups["targets"] = targets_resp.get("data", [])

    consumers_resp = _get("/consumers")
    consumers = consumers_resp.get("data", [])
    for consumer in consumers:
        c_name = consumer.get("username") or consumer.get("id")
        try:
            cred_resp = _get(f"/consumers/{c_name}/key-auth")
            consumer["keyauth_credentials"] = cred_resp.get("data", [])
        except Exception:
            consumer["keyauth_credentials"] = []
        try:
            plugins_resp = _get(f"/consumers/{c_name}/plugins")
            consumer["plugins"] = plugins_resp.get("data", [])
        except Exception:
            consumer["plugins"] = []

    global_plugins_resp = _get("/plugins")
    global_plugins = [
        p
        for p in global_plugins_resp.get("data", [])
        if not p.get("service") and not p.get("consumer")
    ]

    return {
        "_format_version": "admin-api",
        "services": services,
        "upstreams": upstreams,
        "consumers": consumers,
        "plugins": global_plugins,
    }


def load_kong_config(source: str) -> dict[str, Any]:
    """Load Kong config from file path or Admin API URL."""
    if source.startswith("http://") or source.startswith("https://"):
        return load_from_admin_api(source)
    return load_from_file(source)


# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------


def _count_kong_objects(cfg: dict[str, Any]) -> tuple[int, int, int]:
    """Return (services, routes, plugins) counts from a Kong config."""
    services = cfg.get("services", [])
    routes = sum(len(s.get("routes", [])) for s in services)
    plugins = sum(len(s.get("plugins", [])) for s in services) + len(cfg.get("plugins", []))
    return len(services), routes, plugins


# ---------------------------------------------------------------------------
# Kong -> STOA Mappers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")


def _map_rate_limit_plugin(config: dict[str, Any]) -> dict[str, Any]:
    """Map Kong rate-limiting plugin config to STOA policy config."""
    stoa_config: dict[str, Any] = {"by": "token"}
    if "minute" in config:
        stoa_config["requests"] = config["minute"]
        stoa_config["window"] = 60
    elif "hour" in config:
        stoa_config["requests"] = config["hour"]
        stoa_config["window"] = 3600
    elif "second" in config:
        stoa_config["requests"] = config["second"]
        stoa_config["window"] = 1
    return stoa_config


def _map_cors_plugin(config: dict[str, Any]) -> dict[str, Any]:
    """Map Kong cors plugin config to STOA policy config."""
    return {
        "allowOrigins": config.get("origins", ["*"]),
        "allowMethods": config.get("methods", ["GET", "POST", "PUT", "DELETE", "OPTIONS"]),
        "allowHeaders": config.get("headers", ["Authorization", "Content-Type"]),
        "maxAge": config.get("max_age", 3600),
    }


# Plugins that map cleanly to STOA policies
PLUGIN_MAPPERS: dict[str, tuple[str, Any]] = {
    "rate-limiting": ("rate-limit", _map_rate_limit_plugin),
    "rate-limiting-advanced": ("rate-limit", _map_rate_limit_plugin),
    "cors": ("cors", _map_cors_plugin),
}

# Plugins that signal subscription requirement
AUTH_PLUGINS = {"key-auth", "oauth2", "jwt", "basic-auth", "hmac-auth"}

# Plugins that cannot be auto-migrated
UNSUPPORTED_PLUGINS = {
    "request-transformer",
    "response-transformer",
    "request-termination",
    "ip-restriction",
    "acl",
    "bot-detection",
    "ldap-auth",
    "session",
    "proxy-cache",
    "grpc-gateway",
    "grpc-web",
    "aws-lambda",
    "azure-functions",
    "opentelemetry",
    "zipkin",
}


class MigrationReport:
    """Accumulates migration events for the final report."""

    def __init__(self) -> None:
        self.migrated: list[str] = []
        self.warnings: list[str] = []
        self.skipped: list[str] = []
        self.manual_actions: list[str] = []

    def add_migrated(self, msg: str) -> None:
        self.migrated.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_skipped(self, msg: str) -> None:
        self.skipped.append(msg)

    def add_manual(self, msg: str) -> None:
        self.manual_actions.append(msg)

    def render(self) -> str:
        """Render the report as Markdown."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            "# Kong \u2192 STOA Migration Report",
            "",
            f"**Generated**: {now}",
            "",
            "---",
            "",
        ]

        lines.append(f"## Migrated ({len(self.migrated)})")
        lines.append("")
        for m in self.migrated:
            lines.append(f"- {m}")
        lines.append("")

        if self.warnings:
            lines.append(f"## Warnings ({len(self.warnings)})")
            lines.append("")
            for w in self.warnings:
                lines.append(f"- \u26a0\ufe0f {w}")
            lines.append("")

        if self.skipped:
            lines.append(f"## Skipped ({len(self.skipped)})")
            lines.append("")
            for s in self.skipped:
                lines.append(f"- {s}")
            lines.append("")

        if self.manual_actions:
            lines.append(f"## Manual Actions Required ({len(self.manual_actions)})")
            lines.append("")
            for a in self.manual_actions:
                lines.append(f"- [ ] {a}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## Migration Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Migrated | {len(self.migrated)} |")
        lines.append(f"| Warnings | {len(self.warnings)} |")
        lines.append(f"| Skipped | {len(self.skipped)} |")
        lines.append(f"| Manual actions | {len(self.manual_actions)} |")
        lines.append("")

        return "\n".join(lines)


class KongToStoaMigrator:
    """Converts Kong declarative config into STOA platform resources."""

    def __init__(self, kong_config: dict[str, Any]) -> None:
        self.kong = kong_config
        self.report = MigrationReport()

        # Collected STOA resources
        self.apis: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []
        self.tenants: list[dict[str, Any]] = []
        self.applications: list[dict[str, Any]] = []
        self.subscriptions: list[dict[str, Any]] = []

        # Track upstreams by name for cross-reference
        self._upstreams: dict[str, dict[str, Any]] = {}

    # -- public ---------------------------------------------------------

    def migrate(self) -> None:
        """Run the full migration pipeline."""
        self._index_upstreams()
        self._migrate_services()
        self._migrate_consumers()
        self._migrate_global_plugins()

    def stats(self) -> dict[str, int]:
        """Return counts of migrated resources."""
        return {
            "apis": len(self.apis),
            "policies": len(self.policies),
            "tenants": len(self.tenants),
            "applications": len(self.applications),
            "migrated": len(self.report.migrated),
            "warnings": len(self.report.warnings),
            "skipped": len(self.report.skipped),
            "manual": len(self.report.manual_actions),
        }

    def to_stoa_yaml(self) -> str:
        """Serialize all collected resources into a single STOA YAML doc."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc: dict[str, Any] = {
            "apiVersion": "stoa.io/v1",
            "kind": "StoaExport",
            "metadata": {
                "name": "kong-migration",
                "timestamp": now,
                "source": "kong-declarative",
            },
        }

        spec: dict[str, Any] = {}
        if self.tenants:
            spec["tenants"] = self.tenants
        if self.apis:
            spec["apis"] = self.apis
        if self.policies:
            spec["policies"] = self.policies
        if self.applications:
            spec["applications"] = self.applications
        if self.subscriptions:
            spec["subscriptions"] = self.subscriptions

        doc["spec"] = spec
        return yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # -- internals ------------------------------------------------------

    def _index_upstreams(self) -> None:
        for ups in self.kong.get("upstreams", []):
            name = ups.get("name", "")
            self._upstreams[name] = ups

    def _migrate_services(self) -> None:
        for svc in self.kong.get("services", []):
            self._migrate_one_service(svc)

    def _migrate_one_service(self, svc: dict[str, Any]) -> None:
        svc_name = svc.get("name", "unnamed-service")
        slug = _slugify(svc_name)

        # Determine backend URL
        backend_url = svc.get("url", "")
        if not backend_url:
            proto = svc.get("protocol", "https")
            host = svc.get("host", "localhost")
            port = svc.get("port", 443)
            path = svc.get("path", "")
            backend_url = f"{proto}://{host}:{port}{path}"

        # Check if there's a matching upstream
        upstream_info = self._resolve_upstream(svc)

        # Build resources (endpoints) from routes
        resources = self._map_routes(svc.get("routes", []))

        # Map plugins
        plugins = svc.get("plugins", [])
        policies, requires_subscription = self._map_plugins(plugins, context=svc_name)

        tags = svc.get("tags", [])

        api: dict[str, Any] = {
            "id": slug,
            "name": slug,
            "displayName": svc_name.replace("-", " ").title(),
            "version": "1.0.0",
            "description": f"Migrated from Kong service: {svc_name}",
            "backend_url": backend_url,
            "status": "draft",
            "tags": tags,
        }

        if resources:
            api["resources"] = resources
        if policies:
            api["policies"] = [p["name"] for p in policies]
        if requires_subscription:
            api["auth"] = {"type": "api-key", "required": True}
        if upstream_info:
            api["backend"] = upstream_info

        self.apis.append(api)
        self.policies.extend(policies)
        self.report.add_migrated(f"Service `{svc_name}` \u2192 API `{slug}`")

        ux.migrated_api(svc_name, slug)
        for route in svc.get("routes", []):
            route_name = route.get("name", "unnamed-route")
            self.report.add_migrated(f"Route `{route_name}` \u2192 resource in API `{slug}`")
            ux.detail(f"route `{route_name}` \u2192 resource")

    def _map_routes(self, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resources = []
        for route in routes:
            paths = route.get("paths", ["/"])
            methods = route.get("methods") or ["GET", "POST", "PUT", "DELETE"]
            route_name = route.get("name", "")
            for path in paths:
                res: dict[str, Any] = {
                    "path": path + "/*" if not path.endswith("*") else path,
                    "methods": methods,
                }
                if route_name:
                    res["description"] = f"From Kong route: {route_name}"
                resources.append(res)
        return resources

    def _map_plugins(
        self,
        plugins: list[dict[str, Any]],
        context: str = "",
    ) -> tuple[list[dict[str, Any]], bool]:
        """Map Kong plugins to STOA policies.

        Returns (policies, requires_subscription).
        """
        policies: list[dict[str, Any]] = []
        requires_subscription = False

        for plugin in plugins:
            plugin_name = plugin.get("name", "")
            config = plugin.get("config", {})

            if plugin_name in AUTH_PLUGINS:
                requires_subscription = True
                self.report.add_migrated(
                    f"Plugin `{plugin_name}` on `{context}` \u2192 subscription required"
                )
                ux.detail(f"plugin `{plugin_name}` \u2192 subscription required")
                continue

            if plugin_name in PLUGIN_MAPPERS:
                policy_type, mapper_fn = PLUGIN_MAPPERS[plugin_name]
                policy_slug = _slugify(f"{context}-{policy_type}")
                policy = {
                    "apiVersion": "stoa.io/v1",
                    "kind": "Policy",
                    "name": policy_slug,
                    "type": policy_type,
                    "config": mapper_fn(config),
                }
                policies.append(policy)
                self.report.add_migrated(
                    f"Plugin `{plugin_name}` on `{context}` \u2192 policy `{policy_slug}`"
                )
                ux.detail(f"plugin `{plugin_name}` \u2192 policy `{policy_slug}`")
            elif plugin_name in UNSUPPORTED_PLUGINS:
                self.report.add_manual(
                    f"Plugin `{plugin_name}` on `{context}` has no STOA equivalent \u2014 "
                    f"configure manually. Config: {json.dumps(config, default=str)}"
                )
                ux.manual(f"`{plugin_name}` plugin on `{context}` \u2192 manual action required")
            elif plugin_name in ("prometheus", "datadog", "statsd"):
                self.report.add_skipped(
                    f"Observability plugin `{plugin_name}` \u2014 "
                    f"STOA uses built-in metering pipeline"
                )
                ux.skipped(f"`{plugin_name}` plugin \u2192 skipped (STOA built-in)")
            elif plugin_name in ("file-log", "tcp-log", "http-log", "syslog", "udp-log"):
                self.report.add_skipped(
                    f"Logging plugin `{plugin_name}` \u2014 "
                    f"STOA uses built-in logging policy"
                )
                ux.skipped(f"`{plugin_name}` plugin \u2192 skipped (STOA built-in)")
            else:
                self.report.add_warning(
                    f"Unknown plugin `{plugin_name}` on `{context}` \u2014 skipped"
                )
                ux.warning(f"Unknown plugin `{plugin_name}` on `{context}` \u2014 skipped")

        return policies, requires_subscription

    def _resolve_upstream(self, svc: dict[str, Any]) -> dict[str, Any] | None:
        """Check if a Kong upstream matches this service's host."""
        host = svc.get("host", "")
        ups = self._upstreams.get(host)
        if not ups:
            svc_name = svc.get("name", "")
            for ups_name, ups_data in self._upstreams.items():
                if svc_name in ups_name or ups_name in svc_name:
                    ups = ups_data
                    break
        if not ups:
            return None

        targets = []
        for t in ups.get("targets", []):
            target_entry: dict[str, Any] = {"url": t.get("target", "")}
            weight = t.get("weight")
            if weight is not None:
                target_entry["weight"] = weight
            targets.append(target_entry)

        result: dict[str, Any] = {
            "algorithm": ups.get("algorithm", "round-robin"),
            "targets": targets,
        }

        healthchecks = ups.get("healthchecks", {})
        active = healthchecks.get("active", {})
        if active.get("http_path"):
            result["healthCheck"] = {
                "path": active["http_path"],
                "interval": active.get("healthy", {}).get("interval", 30),
            }

        ups_name = ups.get("name", "unnamed")
        self.report.add_migrated(f"Upstream `{ups_name}` \u2192 backend targets in API")
        ux.detail(f"upstream `{ups_name}` \u2192 backend targets")

        return result

    def _migrate_consumers(self) -> None:
        for consumer in self.kong.get("consumers", []):
            self._migrate_one_consumer(consumer)

    def _migrate_one_consumer(self, consumer: dict[str, Any]) -> None:
        username = consumer.get("username", "unnamed")
        custom_id = consumer.get("custom_id", "")
        tags = consumer.get("tags", [])

        is_service_account = "service-account" in tags or custom_id.startswith("svc-")

        if is_service_account:
            app_slug = _slugify(username)
            app: dict[str, Any] = {
                "apiVersion": "stoa.io/v1",
                "kind": "Application",
                "id": app_slug,
                "displayName": username.replace("-", " ").title(),
                "type": "service",
                "tags": tags,
            }
            self.applications.append(app)
            self.report.add_migrated(
                f"Consumer `{username}` (service) \u2192 application `{app_slug}`"
            )
            ux.detail(f"consumer `{username}` \u2192 application `{app_slug}`")
        else:
            tenant_slug = _slugify(custom_id or username)
            tenant: dict[str, Any] = {
                "apiVersion": "stoa.io/v1",
                "kind": "Tenant",
                "id": tenant_slug,
                "displayName": username.replace("-", " ").title(),
                "tags": tags,
                "settings": {},
            }

            consumer_plugins = consumer.get("plugins", [])
            for plugin in consumer_plugins:
                if plugin.get("name") in ("rate-limiting", "rate-limiting-advanced"):
                    cfg = plugin.get("config", {})
                    tenant["settings"]["rateLimit"] = _map_rate_limit_plugin(cfg)
                    self.report.add_migrated(
                        f"Consumer rate-limit for `{username}` \u2192 tenant settings"
                    )

            self.tenants.append(tenant)
            self.report.add_migrated(f"Consumer `{username}` \u2192 tenant `{tenant_slug}`")
            ux.detail(f"consumer `{username}` \u2192 tenant `{tenant_slug}`")

            if consumer.get("keyauth_credentials"):
                self.report.add_manual(
                    f"Consumer `{username}` has API keys \u2014 create STOA subscriptions "
                    f"and issue new API keys via the portal"
                )

    def _migrate_global_plugins(self) -> None:
        for plugin in self.kong.get("plugins", []):
            plugin_name = plugin.get("name", "")
            if plugin_name in ("prometheus", "datadog", "statsd"):
                self.report.add_skipped(
                    f"Global plugin `{plugin_name}` \u2014 STOA uses built-in metering"
                )
                ux.skipped(f"`{plugin_name}` global plugin \u2192 skipped (STOA built-in)")
            elif plugin_name in ("file-log", "tcp-log", "http-log", "syslog", "udp-log"):
                self.report.add_skipped(
                    f"Global plugin `{plugin_name}` \u2014 STOA uses built-in logging"
                )
                ux.skipped(f"`{plugin_name}` global plugin \u2192 skipped (STOA built-in)")
            else:
                self.report.add_warning(
                    f"Global plugin `{plugin_name}` \u2014 review for manual configuration"
                )
                ux.warning(
                    f"Global plugin `{plugin_name}` \u2014 review for manual configuration"
                )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    global ux

    parser = argparse.ArgumentParser(
        description="Kong \u2192 STOA Migration Adapter",
        epilog=(
            "Examples:\n"
            "  python migrate-kong.py --from kong.yaml --to stoa/\n"
            "  python migrate-kong.py --from http://localhost:8001 --to stoa/\n"
            "  python migrate-kong.py --from kong.yaml --dry-run\n"
            "  python migrate-kong.py --from kong.yaml --to stoa/ --verbose\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--from",
        dest="source",
        required=True,
        help="Kong config source: path to kong.yaml or Admin API URL (http://host:8001)",
    )
    parser.add_argument(
        "--to",
        dest="output_dir",
        default=None,
        help="Output directory for STOA files (required unless --dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output for each migrated resource",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (only errors)",
    )
    args = parser.parse_args(argv)

    source: str = args.source
    dry_run: bool = args.dry_run
    verbose: bool = args.verbose
    quiet: bool = args.quiet

    # Validate args
    if not dry_run and not args.output_dir:
        parser.error("--to is required unless --dry-run is set")

    # Configure UX + logging
    ux = _UX(verbose=verbose, quiet=quiet)
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="  [debug] %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    if dry_run:
        ux.dry_run_banner()

    # Load Kong config
    ux.connecting(source)
    try:
        kong_config = load_kong_config(source)
    except ConnectionError as e:
        ux.error_connection(source, str(e))
        return 1
    except FileNotFoundError as e:
        ux.error_file(source, str(e))
        return 1
    except Exception as e:
        ux.error_generic(str(e))
        return 1

    svc_count, route_count, plugin_count = _count_kong_objects(kong_config)
    ux.found(svc_count, route_count, plugin_count)

    # Run migration
    ux.migrating()
    migrator = KongToStoaMigrator(kong_config)
    migrator.migrate()

    st = migrator.stats()

    if dry_run:
        ux.dry_run_summary(st)
        return 0

    # Write outputs
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stoa_yaml_path = output_dir / "stoa-apis.yaml"
    stoa_yaml_path.write_text(migrator.to_stoa_yaml())

    report_path = output_dir / "migration-report.md"
    report_path.write_text(migrator.report.render())

    ux.output_files(stoa_yaml_path, report_path, st)
    ux.done()

    return 0


if __name__ == "__main__":
    sys.exit(main())
