#!/usr/bin/env python3
"""Preuve locale du relais stoactl (Mac, même UID) avec Compose Gateway + mock amont.

Ce script utilise uniquement la bibliothèque standard Python :
- `prepare` : choisit un port loopback libre (avec détection de collision), crée
  les répertoires privés séparés (parent MCP, opérateur contrôle+preuve, enfants),
  génère un justificatif d'enrôlement aléatoire (chmod 0600, jamais affiché) et son
  empreinte SHA-256 pour la Gateway, puis écrit la config Go et l'override Compose.
- `run` : vérifie le refus d'un appel direct sans DPoP, exécute le scénario parent
  et enfant via `stoactl relay connect --socket <socket>` (JSON-RPC stdio, zéro
  credential dans env/argv) et délègue via le socket Unix de contrôle (`POST /v1/delegate`).
- `redact-log` : affiche un extrait borné et expurgé d'un journal en mode debug.

Limites hôte Mac (même UID) :
Le broker local `stoactl relay serve` et les processus agents tournent sous le même
UID macOS ; les permissions POSIX (0700/0600) séparent les chemins mais n'offrent pas
d'isolation noyau inter-processus contre un autre processus du même utilisateur.
L'isolation complète par conteneur/UID Linux est prévue au chantier suivant.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import secrets
import select
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOOL = "refunds_create"
LIMITS_TOOL = "stoa_security"
ROLE = "refund_operator"
PROFILE_NAME = "fixture-local"
SUBJECT_NAME = "fixture-operator"
TENANT_ID = "acme"

PARENT_LIMIT = 500
CHILD_LIMIT = 50
CHILD_ALLOWED_AMOUNT = 25
CHILD_EXCESS_AMOUNT = 80
DELEGATED_CUSTOMER = "C-1042"
OTHER_CUSTOMER = "C-2077"
RELAY_REJECTED_CODE = -32003
RELAY_REJECTED_MESSAGE = "gateway tool call rejected"

FORBIDDEN_CONTROL_KEYS = frozenset(
    {"access_token", "token", "dpop", "private_key", "proof", "secret"}
)

REDACT_PATTERNS = (
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[JWT_REDACT]"),
    (
        re.compile(r"(?i)(authorization|dpop|x-stoa-[a-z0-9-]+|x-api-key)\s*[:=]\s*[^\s,;\"']+"),
        r"\1=[REDACT]",
    ),
    (re.compile(r"(?i)\b(bearer|dpop)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACT]"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "[HEX_REDACT]"),
)


class SmokeError(RuntimeError):
    """Erreur contrôlée et expurgée du scénario relais."""


def redact_line(line: str, max_len: int = 200) -> str:
    cleaned = line.rstrip("\r\n")
    for pattern, repl in REDACT_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned


def write_private_file(path: Path, content: bytes, mode: int = 0o600) -> None:
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


def pick_loopback_port(requested: int | None) -> int:
    if requested is not None:
        if not 1024 <= requested <= 65535:
            raise SmokeError("Port loopback demandé hors plage 1024-65535.")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", requested))
            except OSError as exc:
                raise SmokeError(
                    f"Collision détectée sur 127.0.0.1:{requested} (port déjà utilisé)."
                ) from exc
        return requested

    for _ in range(16):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        # Double vérification qu'aucun écouteur n'accepte sur ce port.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
            check.settimeout(0.2)
            if check.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SmokeError("Impossible d'allouer un port loopback libre.")


def prepare_runtime(runtime_root: Path, requested_port: int | None) -> int:
    runtime_root = runtime_root.resolve()
    os.chmod(runtime_root, 0o700)

    port = pick_loopback_port(requested_port)
    gateway_url = f"http://127.0.0.1:{port}"

    mcp_dir = runtime_root / "mcp"
    op_dir = runtime_root / "op"
    op_home = op_dir / "home"
    agent_home = runtime_root / "agent-home"
    children_dir = runtime_root / "ch"
    gateway_dir = runtime_root / "gateway"

    for private_dir in (mcp_dir, op_dir, op_home, agent_home, children_dir):
        private_dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(private_dir, 0o700)
    gateway_dir.mkdir(mode=0o755, exist_ok=True)
    os.chmod(gateway_dir, 0o755)

    # Justificatif d'enrôlement synthétique aléatoire : écrit uniquement côté opérateur (0600).
    proof = secrets.token_hex(32)
    proof_sha256 = hashlib.sha256(proof.encode("ascii")).hexdigest()
    proof_file = op_dir / "proof"
    write_private_file(proof_file, proof.encode("ascii"), 0o600)
    del proof

    # Fichier d'enrôlement monté en lecture seule dans la Gateway (empreinte uniquement).
    enrollments = {
        "profiles": [
            {
                "name": PROFILE_NAME,
                "subject": SUBJECT_NAME,
                "tenant_id": TENANT_ID,
                "role": ROLE,
                "proof_sha256": proof_sha256,
            }
        ]
    }
    enrollments_path = gateway_dir / "relay-enrollments.json"
    enrollments_bytes = (json.dumps(enrollments, indent=2) + "\n").encode("utf-8")
    write_private_file(enrollments_path, enrollments_bytes, 0o644)

    # Configuration privée Go pour `stoactl relay serve --config <path>`.
    relay_config = {
        "profile": PROFILE_NAME,
        "gateway_url": gateway_url,
        "proof_file": str(proof_file),
        "mcp_socket": str(mcp_dir / "parent.sock"),
        "control_socket": str(op_dir / "control.sock"),
        "children_dir": str(children_dir),
    }
    write_private_file(
        op_dir / "relay-config.json",
        (json.dumps(relay_config, indent=2) + "\n").encode("utf-8"),
        0o600,
    )

    # Surcharge Compose éphémère : écoute loopback uniquement, URL publique exacte,
    # fichier d'enrôlement monté en lecture seule, rôle signé et origine sortante inchangés.
    override = {
        "services": {
            "stoa-gateway": {
                "networks": ["mcp-net", "upstream-net", "relay-net"],
                "ports": [f"127.0.0.1:{port}:8080"],
                "environment": {
                    "STOA_POC_PUBLIC_BASE_URL": gateway_url,
                    "STOA_POC_RELAY_ENROLLMENTS_FILE": "/etc/stoa/poc/relay-enrollments.json",
                },
                "volumes": [
                    f"{enrollments_path}:/etc/stoa/poc/relay-enrollments.json:ro",
                ],
            },
            "upstream-mock": {
            },
        },
        "networks": {
            "relay-net": {
                "driver": "bridge",
            }
        },
    }
    override["services"]["stoa-gateway"]["image"] = "stoa-roles-relay-local/gateway:relay"
    override["services"]["upstream-mock"]["image"] = "stoa-roles-relay-local/mock:relay"
    write_private_file(
        runtime_root / "relay-override.json",
        (json.dumps(override, indent=2) + "\n").encode("utf-8"),
        0o600,
    )
    return port


class UnixHTTPConnection(http.client.HTTPConnection):
    """Client HTTP/1.1 stdlib sur socket Unix domaine local."""

    def __init__(self, socket_path: str, timeout: float = 15.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._socket_path)
        self.sock = sock


def check_direct_without_dpop(gateway_url: str) -> None:
    url = f"{gateway_url}/mcp/poc"
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    status: int
    try:
        with opener.open(req, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as err:
        status = err.code
        try:
            err.close()
        except Exception:
            pass
    except urllib.error.URLError as exc:
        raise SmokeError(f"Gateway injoignable sur {gateway_url} ({type(exc.reason).__name__}).") from None

    if status != 401:
        raise SmokeError(f"Appel direct sans DPoP attendu HTTP 401, reçu HTTP {status}.")


class McpStdioClient:
    """Client JSON-RPC stdio strict via `stoactl relay connect --socket <path>`."""

    def __init__(
        self,
        stoactl_bin: str,
        socket_path: str,
        agent_home: Path,
        label: str,
        timeout: float = 15.0,
    ) -> None:
        self._stoactl_bin = stoactl_bin
        self._socket_path = socket_path
        self._agent_home = agent_home
        self._label = label
        self._timeout = timeout
        self._next_id = 1
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> McpStdioClient:
        # Environnement minimal strict : aucun secret, aucune variable STOA_*, aucun profil utilisateur.
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self._agent_home),
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
                f"{self._label} : lancement de stoactl relay connect impossible ({exc.strerror or type(exc).__name__})."
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
                f"{self._label} : écriture stdio interrompue (code sous-processus={rc})."
            ) from None

    def _read_message(self, deadline: float) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        fd = self._proc.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SmokeError(f"{self._label} : délai dépassé en attente de réponse JSON-RPC.")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                raise SmokeError(f"{self._label} : délai dépassé en attente de réponse JSON-RPC.")
            raw = self._proc.stdout.readline()
            if not raw:
                rc = self._proc.poll()
                raise SmokeError(
                    f"{self._label} : fin de flux stdio inattendue (code sous-processus={rc})."
                )
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except ValueError:
                raise SmokeError(f"{self._label} : trame JSON-RPC invalide reçue.") from None
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
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "stoa-relay-smoke", "version": "1.0.0"},
            },
        )
        if "error" in resp or "result" not in resp:
            raise SmokeError(f"{self._label} : échec de initialize JSON-RPC.")
        self.notify("notifications/initialized", {})

    def tools_list(self) -> list[str]:
        resp = self.request("tools/list", {})
        if "error" in resp or "result" not in resp:
            raise SmokeError(f"{self._label} : échec de tools/list.")
        tools = resp["result"].get("tools")
        if not isinstance(tools, list):
            raise SmokeError(f"{self._label} : catalogue tools/list malformé.")
        names: list[str] = []
        for entry in tools:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                names.append(entry["name"])
        return names

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def refund_args(amount: int, customer: str) -> dict[str, Any]:
    return {"customer_id": customer, "amount_eur": amount, "currency": "EUR"}


def check_limits(
    client: McpStdioClient,
    *,
    amount: int,
    customer: str | None,
    chain: int,
    caller: int,
    depth: int,
    label: str,
) -> dict[str, Any]:
    resp = client.tools_call(LIMITS_TOOL, {})
    if "error" in resp or "result" not in resp:
        raise SmokeError(f"{label} : appel {LIMITS_TOOL} refusé ou invalide.")
    result = resp["result"]
    if not isinstance(result, dict) or result.get("isError"):
        raise SmokeError(f"{label} : {LIMITS_TOOL} a retourné une erreur.")

    view = result.get("structuredContent")
    content = result.get("content")
    if view is None and isinstance(content, list) and content:
        try:
            view = json.loads(content[0]["text"])
        except (KeyError, TypeError, ValueError):
            raise SmokeError(f"{label} : réponse {LIMITS_TOOL} illisible.") from None
    if not isinstance(view, dict):
        raise SmokeError(f"{label} : vue {LIMITS_TOOL} absente.")

    if isinstance(content, list) and content and isinstance(content[0], dict) and "text" in content[0]:
        try:
            if json.loads(content[0]["text"]) != view:
                raise SmokeError(f"{label} : incohérence content/structuredContent sur {LIMITS_TOOL}.")
        except ValueError:
            raise SmokeError(f"{label} : texte JSON {LIMITS_TOOL} invalide.") from None

    if view.get("role") != {"name": ROLE, "policy_version": 1}:
        raise SmokeError(f"{label} : rôle signé inattendu dans {LIMITS_TOOL}.")
    if view.get("allowed_tools") != [TOOL]:
        raise SmokeError(f"{label} : outils autorisés inattendus dans {LIMITS_TOOL}.")
    if view.get("budget") != {"chain_remaining": chain, "root_caller_remaining": caller}:
        raise SmokeError(f"{label} : budget restant inattendu dans {LIMITS_TOOL}.")
    if view.get("delegation_depth") != depth:
        raise SmokeError(f"{label} : profondeur de délégation inattendue dans {LIMITS_TOOL}.")

    fields = view.get("argument_constraints", {}).get(TOOL, {})
    amount_rules = fields.get("amount_eur", [])
    if not amount_rules or min(rule["max"] for rule in amount_rules) != amount:
        raise SmokeError(f"{label} : plafond amount_eur inattendu dans {LIMITS_TOOL}.")
    currency_rules = fields.get("currency", [])
    if not currency_rules or not all(rule.get("values") == ["EUR"] for rule in currency_rules):
        raise SmokeError(f"{label} : contrainte currency inattendue dans {LIMITS_TOOL}.")
    if customer is not None:
        if fields.get("customer_id") != [{"type": "allowed_values", "values": [customer]}]:
            raise SmokeError(f"{label} : contrainte customer_id inattendue dans {LIMITS_TOOL}.")
    elif "customer_id" in fields:
        raise SmokeError(f"{label} : contrainte customer_id imprévue pour le parent.")
    return view


def assert_refund_accepted(
    client: McpStdioClient, amount: int, customer: str, label: str
) -> None:
    args = refund_args(amount, customer)
    resp = client.tools_call(TOOL, args)
    if "error" in resp or "result" not in resp:
        raise SmokeError(f"{label} : remboursement {amount} € sur {customer} refusé.")
    result = resp["result"]
    if not isinstance(result, dict) or result.get("isError"):
        raise SmokeError(f"{label} : remboursement {amount} € en erreur outil.")
    content = result.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        raise SmokeError(f"{label} : réponse remboursement vide.")
    try:
        parsed = json.loads(content[0]["text"])
    except (KeyError, TypeError, ValueError):
        raise SmokeError(f"{label} : réponse remboursement non JSON.") from None
    expected = {**args, "status": "simulated"}
    if parsed != expected:
        raise SmokeError(f"{label} : charge utile de remboursement inattendue.")


def assert_refund_rejected(
    client: McpStdioClient, amount: int, customer: str, label: str
) -> None:
    resp = client.tools_call(TOOL, refund_args(amount, customer))
    err = resp.get("error")
    if not isinstance(err, dict):
        raise SmokeError(f"{label} : appel accepté alors qu'un refus relais était attendu.")
    code = err.get("code")
    msg = err.get("message")
    if not isinstance(code, int) or isinstance(code, bool) or code != RELAY_REJECTED_CODE:
        raise SmokeError(
            f"{label} : code de refus relais inattendu (attendu {RELAY_REJECTED_CODE}, reçu {code!r})."
        )
    if not isinstance(msg, str) or msg != RELAY_REJECTED_MESSAGE:
        raise SmokeError(f"{label} : texte de refus relais inattendu (code {RELAY_REJECTED_CODE}).")


def delegate_via_control(
    control_socket: str, children_dir: Path, parent_socket: str
) -> dict[str, Any]:
    payload = {
        "sub": "relay-child",
        "target_tool": TOOL,
        "allowed_tools": [TOOL],
        "arg_constraints": {
            "customer_id": {"type": "allowed_values", "values": [DELEGATED_CUSTOMER]},
            "amount_eur": {"type": "max_number", "max": CHILD_LIMIT},
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    conn = UnixHTTPConnection(control_socket, timeout=15.0)
    try:
        conn.request(
            "POST",
            "/v1/delegate",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        status = resp.status
        raw = resp.read()
    except OSError as exc:
        raise SmokeError(
            f"Socket de contrôle indisponible ({exc.strerror or type(exc).__name__})."
        ) from None
    finally:
        conn.close()

    if status not in (200, 201):
        raise SmokeError(f"POST /v1/delegate refusé (HTTP {status}).")

    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise SmokeError("Réponse /v1/delegate non JSON.") from None

    if not isinstance(data, dict):
        raise SmokeError("Réponse /v1/delegate malformée.")
    if FORBIDDEN_CONTROL_KEYS.intersection(data):
        raise SmokeError("Réponse /v1/delegate contient un champ sensible interdit.")

    session_id = data.get("session_id")
    socket_path = data.get("socket_path")
    expires_in = data.get("expires_in")
    if not isinstance(session_id, str) or not session_id:
        raise SmokeError("Réponse /v1/delegate sans session_id valide.")
    if not isinstance(socket_path, str) or not socket_path:
        raise SmokeError("Réponse /v1/delegate sans socket_path valide.")
    if not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool) or expires_in <= 0:
        raise SmokeError("Réponse /v1/delegate sans expires_in positif.")

    child_sock = Path(socket_path).resolve()
    expected_dir = children_dir.resolve()
    parent_sock = Path(parent_socket).resolve()
    if child_sock == parent_sock:
        raise SmokeError("La session enfant ne doit pas réutiliser le socket parent.")
    if expected_dir not in child_sock.parents:
        raise SmokeError("Le socket enfant est hors du répertoire children_dir.")
    try:
        mode = os.stat(child_sock).st_mode
    except OSError:
        raise SmokeError("Le socket enfant annoncé par /v1/delegate est introuvable.") from None
    if not stat.S_ISSOCK(mode):
        raise SmokeError("Le chemin enfant annoncé par /v1/delegate n'est pas un socket Unix.")

    return {
        "session_id": session_id,
        "socket_path": str(child_sock),
        "expires_in": int(expires_in),
    }


def run_smoke(stoactl_bin: str, runtime_root: Path, gateway_url: str) -> None:
    if not os.path.isabs(stoactl_bin) or not os.path.isfile(stoactl_bin) or not os.access(stoactl_bin, os.X_OK):
        raise SmokeError("STOA_POC_STOACTL_BIN doit être un chemin absolu vers un binaire exécutable.")

    config_path = runtime_root / "op" / "relay-config.json"
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SmokeError("Configuration relais introuvable ou illisible.") from None

    mcp_socket = str(cfg["mcp_socket"])
    control_socket = str(cfg["control_socket"])
    children_dir = Path(cfg["children_dir"])
    agent_home = runtime_root / "agent-home"

    t0 = time.monotonic()

    def report(step_label: str) -> None:
        elapsed = time.monotonic() - t0
        print(f"{step_label} ({elapsed:.1f}s)", flush=True)

    # 1. Appel direct Gateway sans DPoP -> refus 401
    check_direct_without_dpop(gateway_url)
    report("1/6  Sécurité     · appel direct sans DPoP refusé (HTTP 401)")

    with McpStdioClient(stoactl_bin, mcp_socket, agent_home, "parent") as parent:
        # 2. Parent via stoactl relay connect (JSON-RPC stdio, zéro secret en env/argv)
        parent.initialize()
        parent_tools = parent.tools_list()
        if TOOL not in parent_tools or LIMITS_TOOL not in parent_tools:
            raise SmokeError("Catalogue parent incomplet (refunds_create et stoa_security attendus).")

        check_limits(
            parent,
            amount=PARENT_LIMIT,
            customer=None,
            chain=2,
            caller=3,
            depth=0,
            label="parent",
        )
        assert_refund_rejected(parent, PARENT_LIMIT + 1, OTHER_CUSTOMER, "parent >500 EUR")
        assert_refund_accepted(parent, PARENT_LIMIT, OTHER_CUSTOMER, "parent 500 EUR")
        report(
            f"2/6  Parent       · rôle signé {ROLE}, plafond {PARENT_LIMIT} €, "
            f"{PARENT_LIMIT + 1} € refusés, {PARENT_LIMIT} € acceptés"
        )

        # 3. Délégation sur socket Unix de contrôle opérateur
        delegated = delegate_via_control(control_socket, children_dir, mcp_socket)
        report(
            f"3/6  Délégation   · socket enfant dédié créé (TTL {delegated['expires_in']}s, "
            f"{DELEGATED_CUSTOMER}, plafond {CHILD_LIMIT} €)"
        )

        # 4-6. Enfant connecté exclusivement sur son propre socket
        with McpStdioClient(
            stoactl_bin, delegated["socket_path"], agent_home, "enfant"
        ) as child:
            child.initialize()
            child_tools = child.tools_list()
            if TOOL not in child_tools:
                raise SmokeError("Catalogue enfant sans refunds_create.")
            if not set(child_tools).issubset({TOOL, LIMITS_TOOL}):
                raise SmokeError("Catalogue enfant plus large que le périmètre délégué.")

            limits_note = "catalogue refunds_create"
            if LIMITS_TOOL in child_tools:
                check_limits(
                    child,
                    amount=CHILD_LIMIT,
                    customer=DELEGATED_CUSTOMER,
                    chain=1,
                    caller=2,
                    depth=1,
                    label="enfant",
                )
                limits_note = f"catalogue {TOOL} + {LIMITS_TOOL} vérifiés"
            report(f"4/6  Enfant       · connexion sur socket dédié, {limits_note}")

            assert_refund_rejected(
                child, CHILD_EXCESS_AMOUNT, DELEGATED_CUSTOMER, "enfant 80 EUR"
            )
            assert_refund_rejected(
                child, CHILD_LIMIT, OTHER_CUSTOMER, "enfant mauvais client"
            )
            report(
                f"5/6  Refus enfant · {CHILD_EXCESS_AMOUNT} € sur {DELEGATED_CUSTOMER} "
                f"et {CHILD_LIMIT} € sur {OTHER_CUSTOMER} refusés"
            )

            assert_refund_accepted(
                child, CHILD_ALLOWED_AMOUNT, DELEGATED_CUSTOMER, "enfant 25 EUR"
            )
            report(
                f"6/6  Enfant OK    · remboursement de {CHILD_ALLOWED_AMOUNT} € sur "
                f"{DELEGATED_CUSTOMER} accepté (fermeture locale enfant != révocation Gateway)"
            )


def verify_decisions(decisions_dir: Path) -> None:
    health_path = decisions_dir / "decisions.health.json"
    ndjson_path = decisions_dir / "decisions.ndjson"
    try:
        health = json.loads(health_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SmokeError("decisions.health.json introuvable ou illisible.") from None
    if (
        not isinstance(health, dict)
        or health.get("status") != "healthy"
        or health.get("dropped_records") != 0
    ):
        raise SmokeError("État du journal de décisions non sain.")

    try:
        raw_lines = ndjson_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise SmokeError("decisions.ndjson introuvable ou illisible.") from None

    matched_depths: list[int] = []
    matched_count = 0
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            raise SmokeError("Entrée NDJSON invalide dans decisions.ndjson.") from None
        if not isinstance(rec, dict):
            raise SmokeError("Entrée NDJSON non objet dans decisions.ndjson.")
        if rec.get("reason") != "argument_constraint_denied":
            continue
        tool = rec.get("tool") if isinstance(rec.get("tool"), str) else rec.get("tool_name")
        if tool != TOOL:
            continue
        decision = rec.get("decision")
        if decision is not None and decision != "deny":
            raise SmokeError("Décision inattendue sur un refus argument_constraint_denied.")
        outcome = rec.get("outcome")
        if outcome is not None and outcome not in ("deny", "denied"):
            raise SmokeError("Statut inattendu sur un refus argument_constraint_denied.")
        matched_count += 1
        depth = rec.get("delegation_depth")
        if depth is None:
            depth = rec.get("depth")
        if isinstance(depth, int) and not isinstance(depth, bool):
            matched_depths.append(depth)

    if matched_count != 3:
        raise SmokeError(
            f"Journal de décisions : 3 refus argument_constraint_denied attendus pour {TOOL}, trouvé {matched_count}."
        )
    if len(matched_depths) == 3:
        if matched_depths.count(0) != 1 or matched_depths.count(1) != 2:
            raise SmokeError(
                f"Journal de décisions : répartition parent/enfant inattendue sur {TOOL}."
            )
        print(
            f"Décisions    · 3 refus argument_constraint_denied vérifiés pour {TOOL} (1 parent, 2 enfant)",
            flush=True,
        )
    else:
        print(
            f"Décisions    · 3 refus argument_constraint_denied vérifiés pour {TOOL}",
            flush=True,
        )


def redact_log_file(log_path: Path, max_lines: int) -> None:
    if not log_path.is_file():
        return
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-max_lines:] if max_lines > 0 else []
    if not tail:
        return
    print(f"\n[debug] Extrait expurgé du broker ({len(tail)} dernières lignes) :", file=sys.stderr)
    for line in tail:
        print(f"  {redact_line(line)}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrateur de preuve relais stoactl.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("runtime_root", type=Path)
    p_prep.add_argument("--port", type=int, default=None)

    p_run = sub.add_parser("run")
    p_run.add_argument("--stoactl", required=True)
    p_run.add_argument("--runtime-root", type=Path, required=True)
    p_run.add_argument("--gateway-url", required=True)

    p_log = sub.add_parser("redact-log")
    p_log.add_argument("log_path", type=Path)
    p_log.add_argument("--max-lines", type=int, default=20)

    p_dec = sub.add_parser("verify-decisions")
    p_dec.add_argument("decisions_dir", type=Path)

    args = parser.parse_args()
    try:
        if args.cmd == "prepare":
            port = prepare_runtime(args.runtime_root, args.port)
            print(port, flush=True)
        elif args.cmd == "run":
            run_smoke(args.stoactl, args.runtime_root, args.gateway_url)
        elif args.cmd == "redact-log":
            redact_log_file(args.log_path, args.max_lines)
        elif args.cmd == "verify-decisions":
            verify_decisions(args.decisions_dir)
    except SmokeError as exc:
        print(f"ÉCHEC · {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
    except Exception as exc:
        print(f"ÉCHEC · erreur interne ({type(exc).__name__}).", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
