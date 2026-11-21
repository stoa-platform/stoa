#!/usr/bin/env python3
"""Orchestrateur Python stdlib pour le smoke d'onboarding local (Mac, sans profil réel).

Sous-commandes :
- `prepare`        : alloue 2 ports loopback libres (Gateway + Vault opérateur), génère les
                     marqueurs runtime privés (0600), les enrôlements Gateway (0644), le
                     Compose dédié (tags dédiés, montages :ro) et la config client synthétique.
- `onboard`        : chronomètre `stoactl init` (--plan-only puis --confirm <fingerprint_sha256>)
                     + smoke MCP stdio (< 120s), sans dupliquer les octets clairs sur disque.
- `post-restart`   : vérifie la persistance après redémarrage Gateway + relance broker.
- `doctor-restore` : exécute `stoactl doctor` sur une copie séparée (warning stderr, exit 0),
                     puis chronomètre `stoactl restore` sur la config fixture intacte et vérifie
                     SHA-256, taille et mode POSIX exacts.
- `verify-stats`   : valide les champs sûrs `/stats` de `onboarding-mcp` et `onboarding-vault`
                     (acteurs séparés, lecture seule Gateway, zéro fuite).
- `redact-log`     : affiche un extrait borné et expurgé d'un journal en mode debug.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

SUPPORTED_CLIENTS = ("cursor", "claude", "codex")
PROFILE_NAME = "fixture-local"
SUBJECT_NAME = "fixture-operator"
TENANT_ID = "acme"
ROLE_NAME = "onboarding_operator"
ALIAS_NAME = "legacy"
IMPORTED_TOOL = "legacy__account_lookup"
LIMITS_TOOL = "stoa_security"
CUSTOMER_ID = "C-1042"

MCP_INTERNAL_ORIGIN = "http://127.0.0.1:9000"
MCP_INTERNAL_ENDPOINT = f"{MCP_INTERNAL_ORIGIN}/mcp"
VAULT_INTERNAL_ORIGIN = "http://onboarding-vault:9000"
GATEWAY_VAULT_TOKEN_PATH = "/run/stoa-vault/gateway.token"
VAULT_TLS_CERT_PATH = "/run/vault-tls/server.crt"
VAULT_TLS_KEY_PATH = "/run/vault-tls/server.key"

GATEWAY_IMAGE = "stoa-roles-onboarding-local/gateway:onboarding"
FIXTURE_IMAGE = "stoa-roles-onboarding-local/fixture:onboarding"

ONBOARDING_SLO_SECONDS = 120.0
CANARY_KEY = "non_mcp_canary"
CANARY_VALUE = "stoa-onboarding-preserve-me"

HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SAFE_DIAG_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,48}$")

EXPECTED_VAULT_STATS_KEYS = frozenset(
    {
        "mode",
        "cas_writes_ok",
        "cas_conflicts",
        "cas_violations",
        "readbacks_ok",
        "readbacks_by_actor",
        "soft_deletes_ok",
        "auth_denied",
        "role_violations",
        "path_violations",
        "violations",
        "active_secrets",
        "deleted_secrets",
    }
)

REDACT_PATTERNS = (
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[JWT_REDACT]"),
    (
        re.compile(
            r"(?i)(authorization|dpop|x-vault-token|x-stoa-[a-z0-9-]+|x-api-key)\s*[:=]\s*[^\s,;\"']+"
        ),
        r"\1=[REDACT]",
    ),
    (re.compile(r"(?i)\b(bearer|dpop)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACT]"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "[HEX_REDACT]"),
)


class SmokeError(RuntimeError):
    """Erreur contrôlée et expurgée du smoke d'onboarding."""


def redact_line(line: str, max_len: int = 220) -> str:
    cleaned = line.rstrip("\r\n")
    for pattern, repl in REDACT_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned


def write_file_mode(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def pick_loopback_port(requested: int | None, exclude: set[int] | None = None) -> int:
    excluded = exclude or set()
    if requested is not None:
        if not 1024 <= requested <= 65535:
            raise SmokeError("Port loopback demandé hors plage 1024-65535.")
        if requested in excluded:
            raise SmokeError(f"Collision interne sur le port loopback {requested}.")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", requested))
            except OSError as exc:
                raise SmokeError(
                    f"Collision détectée sur 127.0.0.1:{requested} (port déjà utilisé)."
                ) from exc
        return requested

    for _ in range(32):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        if port in excluded:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
            check.settimeout(0.2)
            if check.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SmokeError("Impossible d'allouer un port loopback libre.")


def file_metadata_snapshot(path: Path) -> dict[str, Any]:
    """Capture uniquement SHA-256, taille et mode POSIX (sans stocker d'octets clairs)."""
    raw = path.read_bytes()
    st = os.stat(path)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mode": stat.S_IMODE(st.st_mode),
        "size": len(raw),
    }


def write_synthetic_client_config(
    client: str,
    project_dir: Path,
    user_dir: Path,
    mcp_bearer: str,
) -> tuple[Path, Path]:
    """Crée une copie synthétique isolée de config client + un fichier canari non-MCP."""
    canary_sibling = project_dir / ".stoa-non-mcp-canary.txt"
    write_file_mode(canary_sibling, f"{CANARY_VALUE}\n".encode("utf-8"), 0o600)

    if client == "cursor":
        cfg_path = project_dir / ".cursor" / "mcp.json"
        cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(cfg_path.parent, 0o700)
        doc = {
            CANARY_KEY: CANARY_VALUE,
            "mcpServers": {
                ALIAS_NAME: {
                    "url": MCP_INTERNAL_ENDPOINT,
                    "headers": {
                        "Authorization": f"Bearer {mcp_bearer}",
                    },
                }
            },
        }
        write_file_mode(cfg_path, (json.dumps(doc, indent=2) + "\n").encode("utf-8"), 0o600)
        return cfg_path, canary_sibling

    if client == "claude":
        cfg_path = project_dir / ".mcp.json"
        doc = {
            CANARY_KEY: CANARY_VALUE,
            "mcpServers": {
                ALIAS_NAME: {
                    "type": "http",
                    "url": MCP_INTERNAL_ENDPOINT,
                    "headers": {
                        "Authorization": f"Bearer {mcp_bearer}",
                    },
                }
            },
        }
        write_file_mode(cfg_path, (json.dumps(doc, indent=2) + "\n").encode("utf-8"), 0o600)
        return cfg_path, canary_sibling

    if client == "codex":
        cfg_path = user_dir / ".codex" / "config.toml"
        cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(cfg_path.parent, 0o700)
        toml_text = (
            f'[{CANARY_KEY}]\n'
            f'keep = "{CANARY_VALUE}"\n\n'
            f'[mcp_servers.{ALIAS_NAME}]\n'
            f'url = "{MCP_INTERNAL_ENDPOINT}"\n'
            f'http_headers = {{ Authorization = "Bearer {mcp_bearer}" }}\n'
        )
        write_file_mode(cfg_path, toml_text.encode("utf-8"), 0o600)
        return cfg_path, canary_sibling

    raise SmokeError(f"Client non supporté : {client}")


def inject_rogue_direct_server(client: str, cfg_path: Path) -> None:
    """Ajoute un serveur direct synthétique (jamais appelé) dans une copie isolée pour doctor."""
    rogue_url = "http://127.0.0.1:1/never-called"
    if client in ("cursor", "claude"):
        doc = json.loads(cfg_path.read_text(encoding="utf-8"))
        servers = doc.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise SmokeError("Structure mcpServers invalide dans la copie doctor.")
        entry: dict[str, Any] = {"url": rogue_url}
        if client == "claude":
            entry["type"] = "http"
        servers["rogue_direct"] = entry
        write_file_mode(cfg_path, (json.dumps(doc, indent=2) + "\n").encode("utf-8"), 0o600)
        return

    if client == "codex":
        current = cfg_path.read_text(encoding="utf-8")
        addition = f'\n[mcp_servers.rogue_direct]\nurl = "{rogue_url}"\n'
        write_file_mode(cfg_path, (current + addition).encode("utf-8"), 0o600)
        return

    raise SmokeError(f"Client non supporté : {client}")


def prepare_runtime(
    runtime_root: Path,
    repo_dir: Path,
    client: str,
    requested_gateway_port: int | None,
    requested_vault_port: int | None,
) -> tuple[int, int]:
    runtime_root = runtime_root.resolve()
    repo_dir = repo_dir.resolve()
    os.chmod(runtime_root, 0o700)

    gateway_port = pick_loopback_port(requested_gateway_port)
    vault_port = pick_loopback_port(requested_vault_port, exclude={gateway_port})
    gateway_url = f"http://127.0.0.1:{gateway_port}"
    vault_url = f"https://127.0.0.1:{vault_port}"

    mcp_dir = runtime_root / "mcp"
    op_dir = runtime_root / "op"
    tls_dir = op_dir / "tls"
    state_dir = op_dir / "state"
    children_dir = runtime_root / "ch"
    client_project = runtime_root / "client" / "project"
    client_user = runtime_root / "client" / "user"
    gateway_dir = runtime_root / "gateway"

    for private_dir in (
        mcp_dir,
        op_dir,
        tls_dir,
        state_dir,
        children_dir,
        runtime_root / "client",
        client_project,
        client_user,
    ):
        private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(private_dir, 0o700)
    gateway_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chmod(gateway_dir, 0o755)

    # Configurations OpenSSL/LibreSSL compatibles (sans -addext) pour CA + cert SAN IP:127.0.0.1.
    ca_cnf = (
        "[req]\n"
        "distinguished_name = dn\n"
        "x509_extensions = v3_ca\n"
        "prompt = no\n\n"
        "[dn]\n"
        "CN = stoa-onboarding-fixture-ca\n\n"
        "[v3_ca]\n"
        "basicConstraints = critical,CA:TRUE,pathlen:0\n"
        "keyUsage = critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier = hash\n"
    )
    server_cnf = (
        "[req]\n"
        "distinguished_name = dn\n"
        "prompt = no\n\n"
        "[dn]\n"
        "CN = 127.0.0.1\n"
    )
    server_ext = (
        "basicConstraints = critical,CA:FALSE\n"
        "keyUsage = critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage = serverAuth\n"
        "subjectAltName = IP:127.0.0.1\n"
    )
    write_file_mode(tls_dir / "ca.cnf", ca_cnf.encode("ascii"), 0o600)
    write_file_mode(tls_dir / "server.cnf", server_cnf.encode("ascii"), 0o600)
    write_file_mode(tls_dir / "server.ext", server_ext.encode("ascii"), 0o600)

    # Secrets runtime générés en stdlib uniquement (jamais affichés, jamais dans argv/Compose).
    proof = secrets.token_hex(32)
    proof_sha256 = hashlib.sha256(proof.encode("ascii")).hexdigest()
    proof_file = op_dir / "proof"
    write_file_mode(proof_file, proof.encode("ascii"), 0o600)
    del proof

    mcp_bearer = secrets.token_urlsafe(24)
    vault_operator_token = secrets.token_urlsafe(24)
    vault_gateway_token = secrets.token_urlsafe(24)

    write_file_mode(op_dir / "mcp.bearer", mcp_bearer.encode("ascii"), 0o600)
    write_file_mode(op_dir / "vault-operator.token", vault_operator_token.encode("ascii"), 0o600)
    write_file_mode(op_dir / "vault-gateway.token", vault_gateway_token.encode("ascii"), 0o600)

    # Fichiers d'environnement privés pour les services mocks (zéro secret dans Compose JSON).
    mcp_env_file = op_dir / "mcp.env"
    vault_env_file = op_dir / "vault.env"
    write_file_mode(
        mcp_env_file,
        f"ONBOARDING_MCP_BEARER_TOKEN={mcp_bearer}\n".encode("ascii"),
        0o600,
    )
    write_file_mode(
        vault_env_file,
        (
            f"ONBOARDING_VAULT_OPERATOR_TOKEN={vault_operator_token}\n"
            f"ONBOARDING_VAULT_GATEWAY_TOKEN={vault_gateway_token}\n"
        ).encode("ascii"),
        0o600,
    )

    cfg_path, canary_sibling = write_synthetic_client_config(
        client, client_project, client_user, mcp_bearer
    )

    # Fichier d'enrôlements monté en lecture seule dans la Gateway (empreinte uniquement, 0644).
    enrollments = {
        "profiles": [
            {
                "name": PROFILE_NAME,
                "subject": SUBJECT_NAME,
                "tenant_id": TENANT_ID,
                "role": ROLE_NAME,
                "proof_sha256": proof_sha256,
                "allow_import": True,
            }
        ]
    }
    enrollments_path = gateway_dir / "relay-enrollments.json"
    write_file_mode(
        enrollments_path,
        (json.dumps(enrollments, indent=2) + "\n").encode("utf-8"),
        0o644,
    )

    # Configuration relais unique partagée entre `stoactl relay serve` et `stoactl init`.
    relay_config = {
        "profile": PROFILE_NAME,
        "gateway_url": gateway_url,
        "proof_file": str(proof_file),
        "mcp_socket": str(mcp_dir / "parent.sock"),
        "control_socket": str(op_dir / "control.sock"),
        "children_dir": str(children_dir),
    }
    relay_config_path = op_dir / "relay-config.json"
    write_file_mode(
        relay_config_path,
        (json.dumps(relay_config, indent=2) + "\n").encode("utf-8"),
        0o600,
    )

    # Métadonnées non sensibles pour l'orchestration.
    meta = {
        "client": client,
        "gateway_url": gateway_url,
        "vault_url": vault_url,
        "vault_cacert": str(tls_dir / "ca.crt"),
        "project_dir": str(client_project),
        "user_dir": str(client_user),
        "client_config_path": str(cfg_path),
        "canary_sibling_path": str(canary_sibling),
        "relay_config_path": str(relay_config_path),
        "state_dir": str(state_dir),
        "vault_operator_token_file": str(op_dir / "vault-operator.token"),
        "mcp_socket": str(mcp_dir / "parent.sock"),
        "control_socket": str(op_dir / "control.sock"),
    }
    write_file_mode(
        op_dir / "meta.json",
        (json.dumps(meta, indent=2) + "\n").encode("utf-8"),
        0o600,
    )

    fixtures_dir = runtime_root / "fixtures"
    fixture_script = repo_dir / "scripts" / "onboarding_fixture.py"
    lab_http_origins = f"{MCP_INTERNAL_ORIGIN},{VAULT_INTERNAL_ORIGIN}"

    compose_doc = {
        "services": {
            "stoa-gateway": {
                "image": GATEWAY_IMAGE,
                "build": {
                    "context": str((repo_dir / ".." / ".." / "stoa-gateway").resolve()),
                    "dockerfile": "Dockerfile",
                    "target": "runtime-debian",
                },
                "network_mode": "service:onboarding-mcp",
                "environment": {
                    "STOA_HOST": "0.0.0.0",
                    "STOA_PORT": "8080",
                    "STOA_LOG_LEVEL": "${STOA_POC_LOG_LEVEL:-info}",
                    "STOA_AUTO_REGISTER": "false",
                    "STOA_ADMIN_ROUTES_DISABLED": "true",
                    "STOA_POLICY_ENABLED": "true",
                    "STOA_POLICY_PATH": "/etc/stoa/poc/opa/policy.rego",
                    "STOA_POLICY_TRUST_JWKS_FILE": "/etc/stoa/poc/trust-jwks.json",
                    "STOA_POLICY_LOCAL_ARTIFACTS_DIR": "/etc/stoa/poc/policies",
                    "STOA_POLICY_BOOT_TENANTS": TENANT_ID,
                    "STOA_POLICY_EXPECTED_ISSUER": "stoa-poc-policy",
                    "STOA_POLICY_AUDIENCE": "stoa-gateway",
                    "STOA_POC_AGENTS_ENABLED": "true",
                    "STOA_POC_BOOTSTRAP_SECRET": "${STOA_POC_BOOTSTRAP_SECRET}",
                    "STOA_POC_UAC_CONTRACTS_DIR": "/etc/stoa/poc/contracts",
                    "STOA_POC_CREDENTIALS_FILE": "/etc/stoa/poc/credentials.json",
                    "STOA_POC_PUBLIC_BASE_URL": gateway_url,
                    "STOA_POC_ROLE_ARTIFACTS_DIR": "/etc/stoa/poc/roles",
                    "STOA_POC_ROLE_FLOOR_DIR": "/tmp/stoa-poc-floors",
                    "STOA_POC_RELAY_ENROLLMENTS_FILE": "/etc/stoa/poc/relay-enrollments.json",
                    "STOA_POC_IMPORT_STATE_DIR": "/tmp/stoa-poc-floors/imports",
                    "STOA_POC_IMPORT_ALLOWED_ORIGINS": MCP_INTERNAL_ORIGIN,
                    "STOA_POC_IMPORT_LAB_HTTP_ORIGINS": lab_http_origins,
                    "STOA_POC_VAULT_ADDR": VAULT_INTERNAL_ORIGIN,
                    "STOA_POC_VAULT_TOKEN_FILE": GATEWAY_VAULT_TOKEN_PATH,
                    "STOA_POC_OUTBOUND_ALLOWED_ORIGINS": lab_http_origins,
                    "STOA_POC_CHAIN_BUDGET": "${STOA_POC_CHAIN_BUDGET:-20}",
                    "STOA_POC_CALLER_BUDGET": "${STOA_POC_CALLER_BUDGET:-40}",
                    "STOA_POC_MAX_REVOKED_CHAINS": "${STOA_POC_MAX_REVOKED_CHAINS:-100}",
                    "STOA_POC_MAX_ADMISSION_ENTRIES": "${STOA_POC_MAX_ADMISSION_ENTRIES:-1000}",
                    "STOA_POC_CALLER_BUDGET_WINDOW_SECS": "${STOA_POC_CALLER_BUDGET_WINDOW_SECS:-900}",
                    "STOA_POC_DECISIONS_DIR": "/tmp/stoa-poc-floors/decisions",
                    "STOA_POC_DECISIONS_MAX_BYTES": "${STOA_POC_DECISIONS_MAX_BYTES:-16777216}",
                    "STOA_POC_DECISIONS_MAX_FILES": "${STOA_POC_DECISIONS_MAX_FILES:-8}",
                },
                "volumes": [
                    "role-floors:/tmp/stoa-poc-floors",
                    "vault-token:/run/stoa-vault:ro",
                    f"{fixtures_dir}/trust-jwks.json:/etc/stoa/poc/trust-jwks.json:ro",
                    f"{fixtures_dir}/policies:/etc/stoa/poc/policies:ro",
                    f"{fixtures_dir}/roles:/etc/stoa/poc/roles:ro",
                    f"{fixtures_dir}/contracts:/etc/stoa/poc/contracts:ro",
                    f"{fixtures_dir}/credentials.json:/etc/stoa/poc/credentials.json:ro",
                    f"{fixtures_dir}/opa:/etc/stoa/poc/opa:ro",
                    f"{enrollments_path}:/etc/stoa/poc/relay-enrollments.json:ro",
                ],
                "healthcheck": {
                    "test": ["CMD", "curl", "-sf", "http://127.0.0.1:8080/ready"],
                    "interval": "2s",
                    "timeout": "3s",
                    "retries": 20,
                    "start_period": "2s",
                },
                "depends_on": ["onboarding-mcp", "onboarding-vault"],
            },
            "onboarding-mcp": {
                "image": FIXTURE_IMAGE,
                "build": {
                    "context": str(repo_dir),
                    "dockerfile": "Dockerfile.agent",
                },
                "command": [
                    "python3",
                    "-B",
                    "/app/onboarding_fixture.py",
                    "--mode",
                    "mcp",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "9000",
                    "--tenant",
                    TENANT_ID,
                ],
                "env_file": [str(mcp_env_file)],
                "networks": ["mcp-net", "upstream-net", "relay-net"],
                "ports": [f"127.0.0.1:{gateway_port}:8080"],
                "volumes": [
                    f"{fixture_script}:/app/onboarding_fixture.py:ro",
                ],
            },
            "onboarding-vault": {
                "image": FIXTURE_IMAGE,
                "build": {
                    "context": str(repo_dir),
                    "dockerfile": "Dockerfile.agent",
                },
                "command": [
                    "python3",
                    "-B",
                    "/app/onboarding_fixture.py",
                    "--mode",
                    "vault",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "9000",
                    "--tls-port",
                    "9443",
                    "--tls-cert",
                    VAULT_TLS_CERT_PATH,
                    "--tls-key",
                    VAULT_TLS_KEY_PATH,
                    "--tenant",
                    TENANT_ID,
                    "--vault-env",
                    PROFILE_NAME,
                ],
                "env_file": [str(vault_env_file)],
                "networks": ["upstream-net", "relay-net"],
                "ports": [f"127.0.0.1:{vault_port}:9443"],
                "volumes": [
                    f"{fixture_script}:/app/onboarding_fixture.py:ro",
                    "vault-tls:/run/vault-tls:ro",
                ],
            },
        },
        "volumes": {
            "role-floors": {},
            "vault-token": {},
            "vault-tls": {},
        },
        "networks": {
            "mcp-net": {"driver": "bridge", "internal": True},
            "upstream-net": {"driver": "bridge", "internal": True},
            "relay-net": {"driver": "bridge"},
        },
    }
    write_file_mode(
        runtime_root / "onboarding-compose.json",
        (json.dumps(compose_doc, indent=2) + "\n").encode("utf-8"),
        0o600,
    )

    # Override privé one-shot uniquement pour le staging initial (network_mode: none,
    # aucun réseau default orphelin, aucune surface de redémarrage implicite).
    staging_override = {
        "services": {
            "stoa-gateway-stage": {
                "image": GATEWAY_IMAGE,
                "restart": "no",
                "network_mode": "none",
                "volumes": [
                    "role-floors:/tmp/stoa-poc-floors",
                    "vault-token:/run/stoa-vault",
                ],
            },
            "onboarding-vault-stage": {
                "image": FIXTURE_IMAGE,
                "restart": "no",
                "network_mode": "none",
                "volumes": [
                    "vault-tls:/run/vault-tls",
                ],
            },
        }
    }
    write_file_mode(
        runtime_root / "staging-override.json",
        (json.dumps(staging_override, indent=2) + "\n").encode("utf-8"),
        0o600,
    )
    return gateway_port, vault_port


class McpStdioClient:
    """Client JSON-RPC stdio strict via `stoactl relay connect --socket <path>`."""

    def __init__(
        self,
        stoactl_bin: str,
        socket_path: str,
        label: str,
        timeout: float = 15.0,
    ) -> None:
        self._stoactl_bin = stoactl_bin
        self._socket_path = socket_path
        self._label = label
        self._timeout = timeout
        self._next_id = 1
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> McpStdioClient:
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
        }
        try:
            self._proc = subprocess.Popen(
                [self._stoactl_bin, "relay", "connect", "--socket", self._socket_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=clean_env,
            )
        except OSError as exc:
            raise SmokeError(
                f"{self._label} : lancement stoactl relay connect impossible ({exc.strerror or type(exc).__name__})."
            ) from None
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _send(self, payload: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except OSError:
            rc = self._proc.poll()
            raise SmokeError(
                f"{self._label} : écriture stdio interrompue (code={rc})."
            ) from None

    def _read_message(self, deadline: float) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        fd = self._proc.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SmokeError(f"{self._label} : délai dépassé en attente JSON-RPC.")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                raise SmokeError(f"{self._label} : délai dépassé en attente JSON-RPC.")
            raw = self._proc.stdout.readline()
            if not raw:
                rc = self._proc.poll()
                raise SmokeError(
                    f"{self._label} : fin de flux stdio inattendue (code={rc})."
                )
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except ValueError:
                raise SmokeError(f"{self._label} : trame JSON-RPC invalide.") from None
            if not isinstance(msg, dict):
                raise SmokeError(f"{self._label} : message JSON-RPC non objet.")
            return msg

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        deadline = time.monotonic() + self._timeout
        while True:
            msg = self._read_message(deadline)
            if "id" not in msg:
                continue
            if msg.get("id") == req_id:
                return msg

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def initialize(self) -> None:
        resp = self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "stoa-onboarding-smoke", "version": "1.0.0"},
            },
        )
        if "error" in resp or "result" not in resp:
            raise SmokeError(f"{self._label} : échec initialize JSON-RPC.")
        self.notify("notifications/initialized", {})

    def tools_list(self) -> list[str]:
        resp = self.request("tools/list", {})
        if "error" in resp or "result" not in resp:
            raise SmokeError(f"{self._label} : échec tools/list.")
        tools = resp["result"].get("tools")
        if not isinstance(tools, list):
            raise SmokeError(f"{self._label} : catalogue tools/list malformé.")
        return [t["name"] for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def assert_account_lookup_via_relay(
    stoactl_bin: str,
    mcp_socket: str,
    label: str,
) -> None:
    with McpStdioClient(stoactl_bin, mcp_socket, label) as client:
        client.initialize()
        tools = client.tools_list()
        if IMPORTED_TOOL not in tools:
            raise SmokeError(f"{label} : outil {IMPORTED_TOOL} absent de tools/list.")
        resp = client.tools_call(IMPORTED_TOOL, {"customer_id": CUSTOMER_ID})
        if "error" in resp or "result" not in resp:
            raise SmokeError(f"{label} : appel {IMPORTED_TOOL} refusé ou en erreur.")
        result = resp["result"]
        if not isinstance(result, dict) or result.get("isError"):
            raise SmokeError(f"{label} : {IMPORTED_TOOL} a retourné isError=true.")
        content = result.get("content")
        if not isinstance(content, list) or not content or not isinstance(content[0], dict):
            raise SmokeError(f"{label} : réponse {IMPORTED_TOOL} vide.")
        try:
            decoded = json.loads(content[0]["text"])
        except (KeyError, TypeError, ValueError):
            raise SmokeError(f"{label} : contenu texte {IMPORTED_TOOL} non JSON.") from None
        if decoded.get("customer_id") != CUSTOMER_ID or decoded.get("tier") != "synthetic":
            raise SmokeError(f"{label} : charge utile synthétique {IMPORTED_TOOL} inattendue.")


def check_socket_permissions(mcp_socket: Path, control_socket: Path, token_file: Path) -> None:
    for sock_path in (mcp_socket, control_socket):
        try:
            st = os.stat(sock_path)
            parent_mode = stat.S_IMODE(os.stat(sock_path.parent).st_mode)
        except OSError:
            raise SmokeError(f"Socket introuvable : {sock_path.name}.") from None
        if not stat.S_ISSOCK(st.st_mode):
            raise SmokeError(f"Chemin non socket Unix : {sock_path.name}.")
        if parent_mode != 0o700:
            raise SmokeError(
                f"Permissions répertoire socket non 0700 ({oct(parent_mode)}) sur {sock_path.parent.name}."
            )
    tok_mode = stat.S_IMODE(os.stat(token_file).st_mode)
    if tok_mode != 0o600:
        raise SmokeError(f"Permissions fichier jeton Vault non 0600 ({oct(tok_mode)}).")


def extract_fingerprint(plan_doc: dict[str, Any]) -> str:
    """Extrait le champ exact `fingerprint_sha256` (64 hex) du JSON `--plan-only -o json`."""
    nested = plan_doc.get("plan")
    primary_candidates: list[Any] = [plan_doc.get("fingerprint_sha256")]
    if isinstance(nested, dict):
        primary_candidates.append(nested.get("fingerprint_sha256"))
    for cand in primary_candidates:
        if isinstance(cand, str):
            val = cand.strip()
            if HEX64_RE.fullmatch(val):
                return val
            raise SmokeError("Champ fingerprint_sha256 invalide (64 caractères hex attendus).")
    raise SmokeError(
        "Champ fingerprint_sha256 absent de la sortie JSON de `stoactl init --plan-only -o json`."
    )


def extract_transaction_id(apply_doc: dict[str, Any]) -> str | None:
    for key in ("transaction_id", "transaction", "tx_id"):
        val = apply_doc.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def extract_safe_blocking_reasons(doc: dict[str, Any]) -> list[str]:
    """Extrait uniquement les codes allowlistés de `blocking_reasons` (jamais de donnée d'entrée)."""
    raw = doc.get("blocking_reasons")
    if raw is None and isinstance(doc.get("plan"), dict):
        raw = doc["plan"].get("blocking_reasons")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        cand: Any = None
        if isinstance(item, str):
            cand = item.strip()
        elif isinstance(item, dict):
            cand = item.get("code") or item.get("reason")
            if isinstance(cand, str):
                cand = cand.strip()
        if isinstance(cand, str) and SAFE_DIAG_CODE_RE.fullmatch(cand):
            out.append(cand)
        if len(out) >= 5:
            break
    return out


def safe_init_failure_code(
    res: subprocess.CompletedProcess[str],
    prefix: str = "INIT_PLAN",
) -> str:
    """Produit un code diagnostic allowlisté stable et sûr sans jamais imprimer de donnée brute."""
    parsed = None
    for stream in (res.stdout, res.stderr):
        if stream and stream.strip().startswith("{"):
            try:
                candidate = json.loads(stream)
            except ValueError:
                candidate = None
            if isinstance(candidate, dict):
                parsed = candidate
                break

    parts: list[str] = []
    if isinstance(parsed, dict):
        code = parsed.get("code") or parsed.get("error_code") or parsed.get("error")
        if isinstance(code, str) and SAFE_DIAG_CODE_RE.fullmatch(code.strip()):
            parts.append(f"{prefix}_CODE_{code.strip()}")
        reasons = extract_safe_blocking_reasons(parsed)
        if reasons:
            parts.append("blocking=" + ",".join(reasons))
    if not parts:
        combined = (res.stderr or "") + "\n" + (res.stdout or "")
        for known in ("smoke_verify_failed", "not_eligible_for_apply"):
            if known in combined:
                parts.append(f"{prefix}_CODE_{known}")
                break
    if not parts:
        if res.returncode == 2:
            parts.append(f"{prefix}_USAGE_OR_FLAG_ERROR")
        else:
            parts.append(f"{prefix}_EXIT_{res.returncode}")
    return " ".join(parts)


def assert_no_secret_leak(text: str, secrets_list: list[str], context: str) -> None:
    for secret in secrets_list:
        if secret and secret in text:
            raise SmokeError(f"Fuite de secret détectée dans {context}.")


def run_cli(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SmokeError(f"Délai dépassé pour {cmd[0]} {' '.join(cmd[1:3])}.") from None
    except OSError as exc:
        raise SmokeError(
            f"Exécution impossible ({exc.strerror or type(exc).__name__})."
        ) from None


def build_init_base_cmd(
    stoactl_bin: str,
    meta: dict[str, Any],
    codex_bin: str | None,
) -> list[str]:
    cmd = [
        stoactl_bin,
        "init",
        "--client",
        meta["client"],
        "--project-dir",
        meta["project_dir"],
        "--user-dir",
        meta["user_dir"],
        "--relay-config",
        meta["relay_config_path"],
        "--state-dir",
        meta["state_dir"],
    ]
    if codex_bin:
        cmd.extend(["--codex-bin", codex_bin])
    return cmd


def run_phase_onboard(
    stoactl_bin: str,
    runtime_root: Path,
    codex_bin: str | None,
) -> None:
    op_dir = runtime_root / "op"
    meta = json.loads((op_dir / "meta.json").read_text(encoding="utf-8"))
    cfg_path = Path(meta["client_config_path"])
    canary_sibling = Path(meta["canary_sibling_path"])

    secrets_list = [
        (op_dir / "mcp.bearer").read_text(encoding="ascii").strip(),
        (op_dir / "vault-operator.token").read_text(encoding="ascii").strip(),
        (op_dir / "vault-gateway.token").read_text(encoding="ascii").strip(),
        (op_dir / "proof").read_text(encoding="ascii").strip(),
    ]

    check_socket_permissions(
        Path(meta["mcp_socket"]),
        Path(meta["control_socket"]),
        Path(meta["vault_operator_token_file"]),
    )
    print("PASS · Sockets protégés (0700) et fichier jeton opérateur (0600) vérifiés", flush=True)

    # Stocke uniquement SHA-256, taille et mode POSIX (aucune copie des octets clairs sur disque).
    before_snap = file_metadata_snapshot(cfg_path)
    before_canary = file_metadata_snapshot(canary_sibling)
    write_file_mode(
        op_dir / "before-snapshot.json",
        json.dumps(
            {
                "sha256": before_snap["sha256"],
                "mode": before_snap["mode"],
                "size": before_snap["size"],
                "canary_sha256": before_canary["sha256"],
                "canary_mode": before_canary["mode"],
            },
            indent=2,
        ).encode("utf-8"),
        0o600,
    )

    # Environnement minimal strict sans override HOME ; VAULT_ADDR (https), VAULT_CACERT et VAULT_TOKEN_FILE.
    cli_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "VAULT_ADDR": meta["vault_url"],
        "VAULT_CACERT": meta["vault_cacert"],
        "VAULT_TOKEN_FILE": meta["vault_operator_token_file"],
    }

    base_init = build_init_base_cmd(stoactl_bin, meta, codex_bin)

    # Début du chronomètre monotonic juste avant `stoactl init --plan-only -o json`.
    t_start = time.monotonic()

    plan_res = run_cli([*base_init, "--plan-only", "-o", "json"], env=cli_env)
    assert_no_secret_leak(plan_res.stdout + plan_res.stderr, secrets_list, "init --plan-only")
    if plan_res.returncode != 0:
        diag_code = safe_init_failure_code(plan_res, "INIT_PLAN")
        raise SmokeError(
            f"stoactl init --plan-only a échoué (diag={diag_code}, exit={plan_res.returncode})."
        )
    try:
        plan_doc = json.loads(plan_res.stdout)
    except ValueError:
        raise SmokeError("Sortie JSON invalide de stoactl init --plan-only (diag=INIT_PLAN_BAD_JSON).") from None
    if not isinstance(plan_doc, dict):
        raise SmokeError("Sortie JSON non objet de stoactl init --plan-only (diag=INIT_PLAN_NOT_OBJECT).")
    blocking = extract_safe_blocking_reasons(plan_doc)
    if plan_doc.get("eligible") is False or blocking:
        detail = f" blocking={','.join(blocking)}" if blocking else ""
        raise SmokeError(
            f"stoactl init --plan-only non éligible (diag=INIT_PLAN_NOT_ELIGIBLE{detail})."
        )
    fingerprint = extract_fingerprint(plan_doc)

    apply_res = run_cli([*base_init, "--confirm", fingerprint, "-o", "json"], env=cli_env)
    assert_no_secret_leak(apply_res.stdout + apply_res.stderr, secrets_list, "init --confirm")
    if apply_res.returncode != 0:
        diag_code = safe_init_failure_code(apply_res, "INIT_CONFIRM")
        raise SmokeError(
            f"stoactl init --confirm a échoué (diag={diag_code}, exit={apply_res.returncode})."
        )
    try:
        apply_doc = json.loads(apply_res.stdout)
    except ValueError:
        raise SmokeError("Sortie JSON invalide de stoactl init --confirm.") from None
    if not isinstance(apply_doc, dict):
        raise SmokeError("Sortie JSON non objet de stoactl init --confirm.")
    tx_id = extract_transaction_id(apply_doc)

    t_after_swap = time.monotonic()

    # Vérifier préservation du canari non-MCP et retrait du secret Bearer en clair.
    swapped_text = cfg_path.read_text(encoding="utf-8")
    if CANARY_VALUE not in swapped_text:
        raise SmokeError("Canari non-MCP perdu dans le fichier client après swap.")
    if secrets_list[0] in swapped_text:
        raise SmokeError("Le marqueur Bearer en clair est encore présent dans la config client après swap.")
    if file_metadata_snapshot(canary_sibling)["sha256"] != before_canary["sha256"]:
        raise SmokeError("Fichier canari non-MCP altéré pendant le swap.")

    # Smoke MCP via le seul trajet `stoactl relay connect` (zéro agent natif externe).
    assert_account_lookup_via_relay(stoactl_bin, meta["mcp_socket"], "smoke post-swap")

    t_end = time.monotonic()
    t_init_swap = t_after_swap - t_start
    t_smoke = t_end - t_after_swap
    t_total = t_end - t_start

    if t_total >= ONBOARDING_SLO_SECONDS:
        raise SmokeError(
            f"Budget temps onboarding dépassé : {t_total:.2f}s >= {ONBOARDING_SLO_SECONDS:.0f}s."
        )

    write_file_mode(
        op_dir / "onboard-result.json",
        json.dumps(
            {
                "transaction_id": tx_id or "latest",
                "t_init_swap": round(t_init_swap, 3),
                "t_smoke": round(t_smoke, 3),
                "t_total": round(t_total, 3),
            },
            indent=2,
        ).encode("utf-8"),
        0o600,
    )

    print(
        f"PASS · Onboarding {meta['client']} (plan+swap {t_init_swap:.2f}s, smoke {t_smoke:.2f}s, "
        f"total {t_total:.2f}s < {ONBOARDING_SLO_SECONDS:.0f}s)",
        flush=True,
    )
    print("PASS · Canari non-MCP préservé et secret Bearer retiré de la config synthétique", flush=True)


def run_phase_post_restart(stoactl_bin: str, runtime_root: Path) -> None:
    op_dir = runtime_root / "op"
    meta = json.loads((op_dir / "meta.json").read_text(encoding="utf-8"))
    assert_account_lookup_via_relay(
        stoactl_bin, meta["mcp_socket"], "persistance post-restart"
    )
    print(
        "PASS · Persistance Gateway restart vérifiée (account_lookup OK via nouveau broker)",
        flush=True,
    )


def run_phase_doctor_and_restore(
    stoactl_bin: str,
    runtime_root: Path,
    codex_bin: str | None,
) -> None:
    op_dir = runtime_root / "op"
    meta = json.loads((op_dir / "meta.json").read_text(encoding="utf-8"))
    before_meta = json.loads((op_dir / "before-snapshot.json").read_text(encoding="utf-8"))
    onboard_res = json.loads((op_dir / "onboard-result.json").read_text(encoding="utf-8"))

    cfg_path = Path(meta["client_config_path"])
    canary_sibling = Path(meta["canary_sibling_path"])

    secrets_list = [
        (op_dir / "mcp.bearer").read_text(encoding="ascii").strip(),
        (op_dir / "vault-operator.token").read_text(encoding="ascii").strip(),
        (op_dir / "vault-gateway.token").read_text(encoding="ascii").strip(),
        (op_dir / "proof").read_text(encoding="ascii").strip(),
    ]

    # 1. Copier l'arborescence appliquée dans une copie isolée pour `stoactl doctor`
    #    sans modifier la vraie config fixture avant le `restore` chronométré.
    doctor_root = runtime_root / "doctor-copy"
    doctor_project = doctor_root / "project"
    doctor_user = doctor_root / "user"
    doctor_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(doctor_root, 0o700)
    shutil.copytree(Path(meta["project_dir"]), doctor_project)
    shutil.copytree(Path(meta["user_dir"]), doctor_user)

    rel_cfg = (
        cfg_path.relative_to(Path(meta["user_dir"]))
        if meta["client"] == "codex"
        else cfg_path.relative_to(Path(meta["project_dir"]))
    )
    doctor_cfg_path = (doctor_user if meta["client"] == "codex" else doctor_project) / rel_cfg
    inject_rogue_direct_server(meta["client"], doctor_cfg_path)

    doctor_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
    }
    doctor_cmd = [
        stoactl_bin,
        "doctor",
        "--client",
        meta["client"],
        "--project-dir",
        str(doctor_project),
        "--user-dir",
        str(doctor_user),
    ]
    if codex_bin:
        doctor_cmd.extend(["--codex-bin", codex_bin])

    doctor_res = run_cli(doctor_cmd, env=doctor_env)
    assert_no_secret_leak(doctor_res.stdout + doctor_res.stderr, secrets_list, "doctor")
    if doctor_res.returncode != 0:
        raise SmokeError(
            f"stoactl doctor attendu exit 0 sur avertissement, reçu {doctor_res.returncode}."
        )
    stderr_lower = doctor_res.stderr.lower()
    if not stderr_lower.strip() or (
        "rogue_direct" not in stderr_lower
        and "direct" not in stderr_lower
        and "warn" not in stderr_lower
    ):
        raise SmokeError("stoactl doctor n'a pas émis d'avertissement stderr lié au serveur direct.")
    print(
        "PASS · stoactl doctor sur copie séparée (exit 0, warning stderr serveur direct safe)",
        flush=True,
    )

    # 2. Vérifier la confidentialité du state-dir (backup chiffré + journal privés, zéro secret en clair)
    #    puis chronométrer `stoactl restore --state-dir` hors-ligne (env minimal PATH/LC_ALL, pointeur par défaut).
    state_root = Path(meta["state_dir"])
    state_files: list[Path] = []
    secret_bytes = [s.encode("ascii") for s in secrets_list if s]
    for entry in state_root.rglob("*"):
        if entry.is_symlink():
            raise SmokeError("Lien symbolique inattendu dans le state-dir fixture.")
        st = os.stat(entry)
        mode = stat.S_IMODE(st.st_mode)
        if mode & 0o077:
            raise SmokeError(
                f"Permissions trop larges ({oct(mode)}) dans le state-dir fixture."
            )
        if entry.is_file():
            state_files.append(entry)
            raw = entry.read_bytes()
            for marker in secret_bytes:
                if marker in raw:
                    raise SmokeError(
                        "Marqueur secret en clair détecté dans le backup ou le journal du state-dir."
                    )
    if not state_files or not any(p.stat().st_size > 0 for p in state_files):
        raise SmokeError("Backup chiffré/journal absent ou vide dans le state-dir fixture.")
    print(
        f"PASS · State-dir privé vérifié ({len(state_files)} fichiers <=0600, backup/journal sans secret en clair)",
        flush=True,
    )

    restore_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
    }
    restore_cmd = [
        stoactl_bin,
        "restore",
        "--state-dir",
        meta["state_dir"],
    ]

    t_restore_start = time.monotonic()
    restore_res = run_cli(restore_cmd, env=restore_env)
    t_restore = time.monotonic() - t_restore_start
    assert_no_secret_leak(restore_res.stdout + restore_res.stderr, secrets_list, "restore")
    if restore_res.returncode != 0:
        raise SmokeError(f"stoactl restore a échoué (exit={restore_res.returncode}).")

    after_snap = file_metadata_snapshot(cfg_path)
    after_canary = file_metadata_snapshot(canary_sibling)
    if after_snap["sha256"] != before_meta["sha256"] or after_snap["size"] != before_meta["size"]:
        raise SmokeError("Restore inexact : SHA-256 ou taille différents de l'état initial.")
    if after_snap["mode"] != before_meta["mode"]:
        raise SmokeError(
            f"Restore inexact : mode {oct(after_snap['mode'])} != {oct(before_meta['mode'])}."
        )
    if after_canary["sha256"] != before_meta["canary_sha256"]:
        raise SmokeError("Fichier canari non-MCP altéré après restore.")

    print(
        f"PASS · Restore exact vérifié ({t_restore:.2f}s, octets={after_snap['size']}, "
        f"mode={oct(after_snap['mode'])}, sha256 identique)",
        flush=True,
    )


def verify_stats(
    runtime_root: Path,
    mcp_stats_json: str,
    vault_url: str,
    min_mcp_calls: int,
) -> None:
    op_dir = runtime_root / "op"
    secrets_list = [
        (op_dir / "mcp.bearer").read_text(encoding="ascii").strip(),
        (op_dir / "vault-operator.token").read_text(encoding="ascii").strip(),
        (op_dir / "vault-gateway.token").read_text(encoding="ascii").strip(),
        (op_dir / "proof").read_text(encoding="ascii").strip(),
    ]

    try:
        mcp_stats = json.loads(mcp_stats_json)
    except ValueError:
        raise SmokeError("Compteurs /stats de onboarding-mcp illisibles.") from None
    assert_no_secret_leak(mcp_stats_json, secrets_list, "mcp /stats")

    meta = json.loads((op_dir / "meta.json").read_text(encoding="utf-8"))
    ssl_ctx = ssl.create_default_context(cafile=meta["vault_cacert"])
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl_ctx),
    )
    try:
        with opener.open(f"{vault_url}/stats", timeout=5) as resp:
            vault_raw = resp.read().decode("utf-8")
    except (OSError, urllib.error.URLError, ssl.SSLError):
        raise SmokeError("Compteurs /stats TLS de onboarding-vault injoignables ou certificat invalide.") from None
    assert_no_secret_leak(vault_raw, secrets_list, "vault /stats")
    try:
        vault_stats = json.loads(vault_raw)
    except ValueError:
        raise SmokeError("Compteurs /stats de onboarding-vault non JSON.") from None

    if not isinstance(vault_stats, dict) or set(vault_stats.keys()) != EXPECTED_VAULT_STATS_KEYS:
        raise SmokeError("Champs /stats de onboarding-vault inattendus ou non conformes.")
    if vault_stats.get("mode") != "vault":
        raise SmokeError("Mode /stats Vault inattendu.")

    if mcp_stats.get("forwarded_auth_caller") != 0:
        raise SmokeError(
            f"Fuite auth appelant vers MCP : forwarded_auth_caller={mcp_stats.get('forwarded_auth_caller')}."
        )
    if mcp_stats.get("auth_denied") != 0:
        raise SmokeError(f"Refus auth inattendu côté MCP : auth_denied={mcp_stats.get('auth_denied')}.")
    if mcp_stats.get("initialize_ok", 0) < 1 or mcp_stats.get("tools_list_ok", 0) < 1:
        raise SmokeError("Séquence MCP initialize/tools_list incomplète dans /stats.")
    if mcp_stats.get("tools_call_ok", 0) < min_mcp_calls:
        raise SmokeError(
            f"Appels account_lookup insuffisants ({mcp_stats.get('tools_call_ok')} < {min_mcp_calls})."
        )

    if vault_stats.get("cas_writes_ok") != 1:
        raise SmokeError(f"Vault CAS writes attendu 1, reçu {vault_stats.get('cas_writes_ok')}.")
    readbacks = vault_stats.get("readbacks_by_actor")
    if (
        not isinstance(readbacks, dict)
        or set(readbacks.keys()) != {"operator", "gateway"}
        or readbacks.get("gateway", 0) < 1
    ):
        raise SmokeError("Vault readbacks acteur gateway (lecture seule) attendu >= 1.")
    if vault_stats.get("soft_deletes_ok") != 0:
        raise SmokeError(
            f"Vault soft_deletes_ok attendu 0 (restore local hors ligne), reçu {vault_stats.get('soft_deletes_ok')}."
        )
    if (
        vault_stats.get("violations") != 0
        or vault_stats.get("role_violations") != 0
        or vault_stats.get("auth_denied") != 0
    ):
        raise SmokeError(
            f"Violations Vault non nulles (violations={vault_stats.get('violations')}, "
            f"role_violations={vault_stats.get('role_violations')}, "
            f"auth_denied={vault_stats.get('auth_denied')})."
        )
    if vault_stats.get("active_secrets") != 1 or vault_stats.get("deleted_secrets") != 0:
        raise SmokeError(
            f"État final des secrets Vault inattendu (active={vault_stats.get('active_secrets')}, "
            f"deleted={vault_stats.get('deleted_secrets')}, attendu active=1/deleted=0)."
        )

    print(
        f"PASS · Compteurs MCP   · init={mcp_stats['initialize_ok']}, list={mcp_stats['tools_list_ok']}, "
        f"call={mcp_stats['tools_call_ok']}, input_denied={mcp_stats['input_denied']}, "
        f"forwarded_auth_caller={mcp_stats['forwarded_auth_caller']}",
        flush=True,
    )
    print(
        f"PASS · Compteurs Vault · cas_writes={vault_stats['cas_writes_ok']}, "
        f"readbacks(op={readbacks['operator']}, gw={readbacks['gateway']}), "
        f"soft_deletes={vault_stats['soft_deletes_ok']}, active={vault_stats['active_secrets']}, "
        f"deleted={vault_stats['deleted_secrets']}, violations={vault_stats['violations']}",
        flush=True,
    )


def redact_log_file(log_path: Path, max_lines: int) -> None:
    if not log_path.is_file():
        return
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-max_lines:] if max_lines > 0 else []
    if not tail:
        return
    print(
        f"\n[debug] Extrait expurgé ({log_path.name}, {len(tail)} dernières lignes) :",
        file=sys.stderr,
    )
    for line in tail:
        print(f"  {redact_line(line)}", file=sys.stderr)


def summarize_log_file(log_path: Path, runtime_root: Path | None) -> str:
    if not log_path.is_file():
        return ""
    lines = [
        line.strip()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    if not lines:
        return ""
    chosen = lines[-1]
    for line in reversed(lines):
        low = line.lower()
        if "error" in low or "fail" in low or "exited" in low or "invalid" in low:
            chosen = line
            break
    sanitized = redact_line(chosen, max_len=160)
    sanitized = re.sub(r"/tmp/stoa-poc-onboarding\.[A-Za-z0-9]+", "<runtime>", sanitized)
    if runtime_root is not None:
        op_dir = runtime_root / "op"
        for name in ("mcp.bearer", "vault-operator.token", "vault-gateway.token", "proof"):
            secret_file = op_dir / name
            if secret_file.is_file():
                val = secret_file.read_text(encoding="ascii", errors="ignore").strip()
                if val:
                    sanitized = sanitized.replace(val, "[REDACT]")
    return sanitized


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("runtime_root", type=Path)
    p_prep.add_argument("--repo-dir", type=Path, required=True)
    p_prep.add_argument("--client", choices=SUPPORTED_CLIENTS, default="cursor")
    p_prep.add_argument("--gateway-port", type=int, default=None)
    p_prep.add_argument("--vault-port", type=int, default=None)

    p_onboard = sub.add_parser("onboard")
    p_onboard.add_argument("--stoactl", required=True)
    p_onboard.add_argument("--runtime-root", type=Path, required=True)
    p_onboard.add_argument("--codex-bin", default=None)

    p_post = sub.add_parser("post-restart")
    p_post.add_argument("--stoactl", required=True)
    p_post.add_argument("--runtime-root", type=Path, required=True)

    p_restore = sub.add_parser("doctor-restore")
    p_restore.add_argument("--stoactl", required=True)
    p_restore.add_argument("--runtime-root", type=Path, required=True)
    p_restore.add_argument("--codex-bin", default=None)

    p_stats = sub.add_parser("verify-stats")
    p_stats.add_argument("--runtime-root", type=Path, required=True)
    p_stats.add_argument("--vault-url", required=True)
    p_stats.add_argument("--min-mcp-calls", type=int, default=2)

    p_log = sub.add_parser("redact-log")
    p_log.add_argument("log_path", type=Path)
    p_log.add_argument("--max-lines", type=int, default=20)

    p_sum = sub.add_parser("summarize-log")
    p_sum.add_argument("log_path", type=Path)
    p_sum.add_argument("--runtime-root", type=Path, default=None)

    args = parser.parse_args()
    try:
        if args.cmd == "prepare":
            gw_port, vlt_port = prepare_runtime(
                args.runtime_root,
                args.repo_dir,
                args.client,
                args.gateway_port,
                args.vault_port,
            )
            print(f"{gw_port} {vlt_port}", flush=True)
        elif args.cmd == "onboard":
            run_phase_onboard(args.stoactl, args.runtime_root, args.codex_bin)
        elif args.cmd == "post-restart":
            run_phase_post_restart(args.stoactl, args.runtime_root)
        elif args.cmd == "doctor-restore":
            run_phase_doctor_and_restore(args.stoactl, args.runtime_root, args.codex_bin)
        elif args.cmd == "verify-stats":
            mcp_raw = sys.stdin.read()
            verify_stats(args.runtime_root, mcp_raw, args.vault_url, args.min_mcp_calls)
        elif args.cmd == "redact-log":
            redact_log_file(args.log_path, args.max_lines)
        elif args.cmd == "summarize-log":
            summary = summarize_log_file(args.log_path, args.runtime_root)
            if summary:
                print(summary, flush=True)
    except SmokeError as exc:
        print(f"FAIL · {exc}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
