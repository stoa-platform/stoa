#!/usr/bin/env python3
"""Preuve locale d'isolation conteneur Linux Compose du relais stoactl.

Ce module utilise uniquement la bibliothèque standard Python et réutilise les
primitives de preuve existantes dans `relay_smoke.py` :
- `prepare` : génère un justificatif d'enrôlement aléatoire côté opérateur et
  écrit uniquement son empreinte SHA-256 pour la Gateway.
- `init-broker` : exécuté dans `relay-broker`, vérifie le durcissement du
  conteneur et les répertoires 0700, puis écrit `proof` (0600) et
  `relay-config.json` (0600, `max_children=1`, `gateway_url=http://127.0.0.1:8080`).
- `wait-broker` : exécuté dans `relay-broker`, attend les sockets 0600 du broker
  et vérifie le refus HTTP 401 d'un appel direct sans DPoP.
- `parent-check` : exécuté dans `relay-parent` (`network_mode: none`), vérifie
  l'isolation noyau/FS/env/socket et exécute le scénario parent via
  `stoactl relay connect --socket /run/stoa-relay/parent/parent.sock`.
- `delegate` : exécuté dans `relay-broker`, déclenche `POST /v1/delegate` sur le
  socket de contrôle privé et vérifie l'unicité/mode du socket enfant.
- `parent-probe-child` : exécuté dans `relay-parent` après délégation, prouve
  que le socket enfant créé reste invisible et inaccessible au parent.
- `child-check` : exécuté dans `relay-child` (`network_mode: none`), vérifie
  l'isolation noyau/FS/env/socket (dont le refus d'accès au socket parent) et
  exécute le scénario enfant borné via `stoactl relay connect --socket <enfant>`.
- `verify-upstream` : vérifie les compteurs exacts du mock amont (2 appels
  autorisés, 0 en-tête Authorization appelant).

Portée : preuve d'isolation entre conteneurs Linux Compose (`network_mode: none`,
`cap_drop: ALL`, volumes socket dédiés par agent) ; ne prouve pas l'isolation
d'agents exécutés nus sur l'hôte macOS.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import relay_smoke as rs  # noqa: E402

GATEWAY_INTERNAL_URL = "http://127.0.0.1:8080"
STOACTL_CONTAINER_BIN = "/usr/local/bin/stoactl"
RELAY_BASE_DIR = Path("/run/stoa-relay")
OP_DIR = RELAY_BASE_DIR / "op"
OP_HOME = OP_DIR / "home"
PROOF_FILE = OP_DIR / "proof"
CONFIG_FILE = OP_DIR / "relay-config.json"
CONTROL_SOCKET = OP_DIR / "control.sock"
PARENT_DIR = RELAY_BASE_DIR / "parent"
PARENT_SOCKET = PARENT_DIR / "parent.sock"
CHILD_DIR = RELAY_BASE_DIR / "child"
EXPECTED_UID = 1000
MAX_CHILDREN = 1
MAX_CAPTURED_STDERR_BYTES = 65536

DOCKER_SOCKET_PATHS = (
    Path("/var/run/docker.sock"),
    Path("/run/docker.sock"),
)

OP_PRIVATE_PATHS = (
    OP_DIR,
    PROOF_FILE,
    CONFIG_FILE,
    CONTROL_SOCKET,
)

FORBIDDEN_ENV_PREFIXES = ("STOA_",)
FORBIDDEN_ENV_FRAGMENTS = (
    "SECRET",
    "TOKEN",
    "API_KEY",
    "PROOF",
    "DPOP",
    "PASSWORD",
    "PRIVATE_KEY",
    "BOOTSTRAP",
    "AUTH",
)

SECRET_LEAK_PATTERNS = (
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("pem_private_key", re.compile(r"BEGIN [A-Z0-9 ]*PRIVATE KEY")),
    (
        "auth_header",
        re.compile(
            r"(?i)\b(authorization|dpop|x-api-key|x-stoa-poc-bootstrap-secret)\s*[:=]\s*[^\s,;\"']+"
        ),
    ),
    ("dpop_or_bearer", re.compile(r"(?i)\b(bearer|dpop)\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("long_hex_secret", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
)

EXPECTED_UPSTREAM_STATS = {
    "upstream_calls": 2,
    "refund_calls": 2,
    "valid_api_key_calls": 2,
    "accepted_skill_context_calls": 2,
    "caller_auth_headers_seen": 0,
    "fail_calls": 0,
    "forbidden_calls": 0,
    "redirect_target_calls": 0,
    "oauth2_calls": 0,
}


def build_broker_config() -> dict[str, Any]:
    return {
        "profile": rs.PROFILE_NAME,
        "gateway_url": GATEWAY_INTERNAL_URL,
        "proof_file": str(PROOF_FILE),
        "mcp_socket": str(PARENT_SOCKET),
        "control_socket": str(CONTROL_SOCKET),
        "children_dir": str(CHILD_DIR),
        "max_children": MAX_CHILDREN,
    }


def prepare_dock_runtime(runtime_root: Path) -> None:
    runtime_root = runtime_root.resolve()
    os.chmod(runtime_root, 0o700)

    op_dir = runtime_root / "op"
    gateway_dir = runtime_root / "gateway"
    op_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(op_dir, 0o700)
    gateway_dir.mkdir(mode=0o755, exist_ok=True)
    os.chmod(gateway_dir, 0o755)

    proof = secrets.token_hex(32)
    proof_sha256 = hashlib.sha256(proof.encode("ascii")).hexdigest()

    # Transféré une seule fois sur stdin vers relay-broker puis supprimé côté hôte.
    rs.write_private_file(op_dir / "proof", proof.encode("ascii"), 0o600)
    del proof

    enrollments = {
        "profiles": [
            {
                "name": rs.PROFILE_NAME,
                "subject": rs.SUBJECT_NAME,
                "tenant_id": rs.TENANT_ID,
                "role": rs.ROLE,
                "proof_sha256": proof_sha256,
            }
        ]
    }
    rs.write_private_file(
        gateway_dir / "relay-enrollments.json",
        (json.dumps(enrollments, indent=2) + "\n").encode("utf-8"),
        0o644,
    )


def validate_private_ipv4(ip_text: str) -> str:
    try:
        addr = ipaddress.IPv4Address(ip_text.strip())
    except ValueError:
        raise rs.SmokeError("Adresse IP privée du mock invalide.") from None
    if not addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        raise rs.SmokeError("L'adresse IP du mock doit être une IPv4 privée RFC1918.")
    return str(addr)


def assert_no_secrets_in_text(text: str, label: str) -> None:
    for kind, pattern in SECRET_LEAK_PATTERNS:
        if pattern.search(text):
            raise rs.SmokeError(f"{label} : fuite potentielle détectée ({kind}).")


ALLOWED_PYTHON_IMAGE_ENV_KEYS = frozenset(
    {
        "GPG_KEY",
        "PYTHON_SHA256",
        "PYTHON_VERSION",
        "PYTHON_PIP_VERSION",
        "PYTHON_GET_PIP_URL",
        "PYTHON_GET_PIP_SHA256",
    }
)


def check_clean_env(
    env: dict[str, str], label: str, *, allow_image_vars: bool = False
) -> None:
    for key, value in env.items():
        if allow_image_vars and key in ALLOWED_PYTHON_IMAGE_ENV_KEYS:
            continue
        upper = key.upper()
        if any(upper.startswith(prefix) for prefix in FORBIDDEN_ENV_PREFIXES):
            raise rs.SmokeError(f"{label} : variable d'environnement interdite présente ({key}).")
        if any(fragment in upper for fragment in FORBIDDEN_ENV_FRAGMENTS):
            raise rs.SmokeError(f"{label} : variable d'environnement sensible présente ({key}).")
        assert_no_secrets_in_text(value, f"{label} env[{key}]")


def check_proc_status_hardening(status_text: str, label: str) -> None:
    cap_eff: str | None = None
    no_new_privs: str | None = None
    for line in status_text.splitlines():
        if line.startswith("CapEff:"):
            cap_eff = line.split(":", 1)[1].strip()
        elif line.startswith("NoNewPrivs:"):
            no_new_privs = line.split(":", 1)[1].strip()
    if cap_eff is None or int(cap_eff, 16) != 0:
        raise rs.SmokeError(f"{label} : capabilities effectives non nulles ({cap_eff!r}).")
    if no_new_privs != "1":
        raise rs.SmokeError(f"{label} : NoNewPrivs non actif ({no_new_privs!r}).")


def check_container_hardening(label: str, *, probe_ro_dir: Path = Path("/app")) -> None:
    if os.getuid() != EXPECTED_UID or os.geteuid() != EXPECTED_UID:
        raise rs.SmokeError(
            f"{label} : UID inattendu (attendu {EXPECTED_UID}, obtenu {os.geteuid()})."
        )
    status_path = Path("/proc/self/status")
    try:
        status_text = status_path.read_text(encoding="utf-8")
    except OSError:
        raise rs.SmokeError(f"{label} : impossible de lire /proc/self/status.") from None
    check_proc_status_hardening(status_text, label)

    probe_file = probe_ro_dir / ".stoa-ro-probe"
    try:
        fd = os.open(probe_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        pass
    else:
        os.close(fd)
        try:
            probe_file.unlink()
        except OSError:
            pass
        raise rs.SmokeError(f"{label} : système de fichiers racine inscriptible.")


IFF_UP = 0x1
IFF_LOOPBACK = 0x8
IFF_RUNNING = 0x40
NETNS_PATTERN = re.compile(r"^net:\[\d+\]$")
FIB_LEAF_PATTERN = re.compile(r"^\s*\|--\s+(\d+\.\d+\.\d+\.\d+)\s*$")
FIB_ROUTE_PATTERN = re.compile(r"^\s*/(\d+)\s+\S+\s+([A-Z]+)\s*$")


def read_netns_id(proc_netns_path: Path = Path("/proc/self/ns/net")) -> str:
    try:
        target = os.readlink(proc_netns_path)
    except OSError:
        raise rs.SmokeError(f"impossible de lire le namespace réseau ({proc_netns_path}).") from None
    if not NETNS_PATTERN.match(target):
        raise rs.SmokeError(f"identifiant de namespace réseau inattendu ({target!r}).")
    return target


def check_ipv4_fib_trie(fib_text: str, label: str) -> None:
    local_addrs: set[ipaddress.IPv4Address] = set()
    current_ip: ipaddress.IPv4Address | None = None
    for line in fib_text.splitlines():
        leaf = FIB_LEAF_PATTERN.match(line)
        if leaf:
            try:
                current_ip = ipaddress.IPv4Address(leaf.group(1))
            except ValueError:
                current_ip = None
            continue
        route = FIB_ROUTE_PATTERN.match(line)
        if route and current_ip is not None:
            route_type = route.group(2)
            if route_type == "LOCAL":
                if not current_ip.is_loopback:
                    raise rs.SmokeError(
                        f"{label} : adresse IPv4 non-loopback configurée ({current_ip})."
                    )
                local_addrs.add(current_ip)
            elif route_type == "UNICAST" and not current_ip.is_loopback:
                raise rs.SmokeError(
                    f"{label} : route IPv4 unicast externe présente ({current_ip}/{route.group(1)})."
                )
            continue
        stripped = line.strip()
        if stripped.startswith("+--") or stripped.endswith(":"):
            current_ip = None

    if ipaddress.IPv4Address("127.0.0.1") not in local_addrs:
        raise rs.SmokeError(f"{label} : adresse loopback 127.0.0.1 absente de /proc/net/fib_trie.")


def check_ipv6_addresses(if_inet6_text: str, label: str) -> None:
    for line in if_inet6_text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) < 6:
            raise rs.SmokeError(f"{label} : entrée /proc/net/if_inet6 malformée.")
        addr_hex, iface = parts[0], parts[5]
        try:
            addr = ipaddress.IPv6Address(bytes.fromhex(addr_hex))
        except ValueError:
            raise rs.SmokeError(f"{label} : adresse IPv6 illisible dans /proc/net/if_inet6.") from None
        if iface != "lo" or not addr.is_loopback:
            raise rs.SmokeError(
                f"{label} : adresse IPv6 non-loopback configurée ({addr} sur {iface})."
            )


def check_ipv6_routes(ipv6_route_text: str, label: str) -> None:
    zero_nexthop = "0" * 32
    for line in ipv6_route_text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) < 10:
            raise rs.SmokeError(f"{label} : entrée /proc/net/ipv6_route malformée.")
        dest_hex, dest_plen, nexthop_hex, iface = parts[0], parts[1], parts[4], parts[9]
        if iface != "lo" or nexthop_hex != zero_nexthop:
            raise rs.SmokeError(
                f"{label} : route IPv6 externe détectée (iface={iface}, dest={dest_hex}/{dest_plen})."
            )


def check_network_none_kernel(
    label: str,
    *,
    disallowed_netns: tuple[str, ...] = (),
    sys_net_dir: Path = Path("/sys/class/net"),
    proc_route_path: Path = Path("/proc/net/route"),
    proc_fib_trie_path: Path = Path("/proc/net/fib_trie"),
    proc_if_inet6_path: Path = Path("/proc/net/if_inet6"),
    proc_ipv6_route_path: Path = Path("/proc/net/ipv6_route"),
    proc_netns_path: Path = Path("/proc/self/ns/net"),
) -> str:
    netns = read_netns_id(proc_netns_path)
    if netns in disallowed_netns:
        raise rs.SmokeError(
            f"{label} : namespace réseau partagé avec un autre conteneur ({netns})."
        )

    try:
        entries = sorted(sys_net_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        raise rs.SmokeError(f"{label} : impossible d'inspecter {sys_net_dir}.") from None

    # Ignore les fichiers d'attributs sysfs (ex. bonding_masters) qui ne sont pas des périphériques.
    devices = [entry for entry in entries if entry.is_dir()]
    lo_seen = False
    for dev in devices:
        try:
            flags = int((dev / "flags").read_text(encoding="ascii").strip(), 0)
            operstate = (dev / "operstate").read_text(encoding="ascii").strip().lower()
        except (OSError, ValueError):
            raise rs.SmokeError(
                f"{label} : impossible de lire flags/operstate pour le périphérique {dev.name}."
            ) from None

        if dev.name == "lo":
            lo_seen = True
            if (flags & IFF_UP) == 0 or (flags & IFF_LOOPBACK) == 0 or operstate == "down":
                raise rs.SmokeError(
                    f"{label} : interface lo non opérationnelle (flags={hex(flags)}, operstate={operstate})."
                )
        else:
            if (flags & (IFF_UP | IFF_RUNNING)) != 0 or operstate != "down":
                raise rs.SmokeError(
                    f"{label} : périphérique réseau non-lo actif détecté "
                    f"({dev.name}: flags={hex(flags)}, operstate={operstate})."
                )

    if not lo_seen:
        raise rs.SmokeError(f"{label} : interface loopback lo absente de {sys_net_dir}.")

    try:
        route_lines = [
            line.strip()
            for line in proc_route_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError:
        raise rs.SmokeError(f"{label} : impossible d'inspecter {proc_route_path}.") from None
    if len(route_lines) != 1:
        first_route = route_lines[1].split()[:2] if len(route_lines) > 1 else []
        raise rs.SmokeError(
            f"{label} : route IPv4 externe présente dans /proc/net/route ({first_route})."
        )

    try:
        fib_text = proc_fib_trie_path.read_text(encoding="utf-8")
    except OSError:
        raise rs.SmokeError(f"{label} : impossible d'inspecter {proc_fib_trie_path}.") from None
    check_ipv4_fib_trie(fib_text, label)

    if proc_if_inet6_path.exists():
        try:
            if_inet6_text = proc_if_inet6_path.read_text(encoding="utf-8")
        except OSError:
            raise rs.SmokeError(f"{label} : impossible d'inspecter {proc_if_inet6_path}.") from None
        check_ipv6_addresses(if_inet6_text, label)

    if proc_ipv6_route_path.exists():
        try:
            ipv6_route_text = proc_ipv6_route_path.read_text(encoding="utf-8")
        except OSError:
            raise rs.SmokeError(f"{label} : impossible d'inspecter {proc_ipv6_route_path}.") from None
        check_ipv6_routes(ipv6_route_text, label)

    return netns


def verify_docker_inspect(
    records: Any,
    *,
    gateway_id: str,
    broker_id: str,
    parent_id: str,
    child_id: str,
) -> None:
    if not isinstance(records, list):
        raise rs.SmokeError("docker inspect : sortie JSON inattendue.")
    by_id = {
        str(rec.get("Id", "")): rec
        for rec in records
        if isinstance(rec, dict) and isinstance(rec.get("Id"), str)
    }

    def lookup(cid: str, name: str) -> dict[str, Any]:
        for full_id, rec in by_id.items():
            if full_id == cid or full_id.startswith(cid):
                return rec
        raise rs.SmokeError(f"docker inspect : conteneur {name} introuvable.")

    gw = lookup(gateway_id, "stoa-gateway")
    gw_full_id = str(gw["Id"])
    broker = lookup(broker_id, "relay-broker")
    parent = lookup(parent_id, "relay-parent")
    child = lookup(child_id, "relay-child")

    def check_common_hardening(rec: dict[str, Any], name: str) -> None:
        hc = rec.get("HostConfig") or {}
        if hc.get("Privileged") is not False:
            raise rs.SmokeError(f"docker inspect : {name} ne doit pas être privilégié.")
        if hc.get("ReadonlyRootfs") is not True:
            raise rs.SmokeError(f"docker inspect : {name} doit avoir ReadonlyRootfs=true.")
        cap_drop = [str(c).upper() for c in (hc.get("CapDrop") or [])]
        if "ALL" not in cap_drop:
            raise rs.SmokeError(f"docker inspect : {name} doit avoir CapDrop=ALL.")
        for mount in rec.get("Mounts") or []:
            src = str(mount.get("Source", ""))
            dst = str(mount.get("Destination", ""))
            if "docker.sock" in src or "docker.sock" in dst:
                raise rs.SmokeError(f"docker inspect : montage docker.sock interdit sur {name}.")

    check_common_hardening(broker, "relay-broker")
    broker_net = str((broker.get("HostConfig") or {}).get("NetworkMode", ""))
    if broker_net not in (f"container:{gw_full_id}", f"container:{gateway_id}"):
        raise rs.SmokeError(
            f"docker inspect : relay-broker NetworkMode attendu container:<gateway>, reçu {broker_net!r}."
        )

    for name, rec in (("relay-parent", parent), ("relay-child", child)):
        check_common_hardening(rec, name)
        net_mode = str((rec.get("HostConfig") or {}).get("NetworkMode", ""))
        if net_mode != "none":
            raise rs.SmokeError(
                f"docker inspect : {name} NetworkMode attendu 'none', reçu {net_mode!r}."
            )
        ns = rec.get("NetworkSettings") or {}
        if ns.get("IPAddress") or ns.get("GlobalIPv6Address"):
            raise rs.SmokeError(f"docker inspect : {name} possède une adresse IP non vide.")
        for net_name, net_cfg in (ns.get("Networks") or {}).items():
            if net_name != "none":
                raise rs.SmokeError(
                    f"docker inspect : {name} attaché au réseau inattendu {net_name!r}."
                )
            if isinstance(net_cfg, dict) and (
                net_cfg.get("IPAddress") or net_cfg.get("GlobalIPv6Address")
            ):
                raise rs.SmokeError(
                    f"docker inspect : {name} possède une adresse IP sur le réseau {net_name!r}."
                )


def assert_tcp_refused(host: str, port: int, label: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            raise rs.SmokeError(f"{label} : connexion TCP vers {host}:{port} autorisée à tort.")
    except OSError:
        return


def assert_path_inaccessible(path: Path, label: str) -> None:
    try:
        st = os.lstat(path)
    except OSError:
        return
    if stat.S_ISSOCK(st.st_mode):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect(str(path))
        except OSError:
            raise rs.SmokeError(f"{label} : socket sensible visible dans le namespace FS ({path}).") from None
        finally:
            sock.close()
        raise rs.SmokeError(f"{label} : connexion au socket sensible réussie ({path}).")
    raise rs.SmokeError(f"{label} : chemin sensible visible dans le namespace FS ({path}).")


def assert_private_dir(path: Path, label: str, expected_uid: int = EXPECTED_UID) -> None:
    try:
        st = os.lstat(path)
    except OSError:
        raise rs.SmokeError(f"{label} : répertoire {path} introuvable.") from None
    if not stat.S_ISDIR(st.st_mode):
        raise rs.SmokeError(f"{label} : {path} n'est pas un répertoire.")
    if st.st_uid != expected_uid:
        raise rs.SmokeError(f"{label} : propriétaire inattendu sur {path} (uid={st.st_uid}).")
    if stat.S_IMODE(st.st_mode) != 0o700:
        raise rs.SmokeError(
            f"{label} : mode inattendu sur {path} ({oct(stat.S_IMODE(st.st_mode))}, attendu 0o700)."
        )


def assert_private_socket(path: Path, label: str, expected_uid: int = EXPECTED_UID) -> None:
    try:
        st = os.lstat(path)
    except OSError:
        raise rs.SmokeError(f"{label} : socket {path} introuvable.") from None
    if not stat.S_ISSOCK(st.st_mode):
        raise rs.SmokeError(f"{label} : {path} n'est pas un socket Unix.")
    if st.st_uid != expected_uid:
        raise rs.SmokeError(f"{label} : propriétaire inattendu sur {path} (uid={st.st_uid}).")
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise rs.SmokeError(
            f"{label} : mode inattendu sur {path} ({oct(stat.S_IMODE(st.st_mode))}, attendu 0o600)."
        )


class AuditedMcpStdioClient(rs.McpStdioClient):
    """Client stdio `stoactl relay connect` avec audit env/argv/stdout/stderr."""

    def __init__(
        self,
        stoactl_bin: str,
        socket_path: str,
        agent_home: Path,
        label: str,
        timeout: float = 15.0,
    ) -> None:
        super().__init__(stoactl_bin, socket_path, agent_home, label, timeout=timeout)
        self._captured_stdout: list[str] = []
        self._captured_stderr = bytearray()
        self._stderr_thread: threading.Thread | None = None
        self._launch_argv: list[str] = []
        self._launch_env: dict[str, str] = {}

    def __enter__(self) -> AuditedMcpStdioClient:
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(self._agent_home),
            "LC_ALL": "C",
        }
        argv = [self._stoactl_bin, "relay", "connect", "--socket", self._socket_path]
        check_clean_env(clean_env, f"{self._label} shim")
        for arg in argv:
            assert_no_secrets_in_text(arg, f"{self._label} shim argv")
        self._launch_argv = argv
        self._launch_env = clean_env

        try:
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=clean_env,
            )
        except OSError as exc:
            raise rs.SmokeError(
                f"{self._label} : lancement de stoactl relay connect impossible "
                f"({exc.strerror or type(exc).__name__})."
            ) from None

        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, name=f"{self._label}-stderr", daemon=True
        )
        self._stderr_thread.start()
        return self

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                chunk = proc.stderr.read(4096)
                if not chunk:
                    break
                remaining = MAX_CAPTURED_STDERR_BYTES - len(self._captured_stderr)
                if remaining > 0:
                    self._captured_stderr.extend(chunk[:remaining])
        except (OSError, ValueError):
            return

    def _read_message(self, deadline: float) -> dict[str, Any]:
        msg = super()._read_message(deadline)
        serialized = json.dumps(msg, separators=(",", ":"))
        assert_no_secrets_in_text(serialized, f"{self._label} shim stdout")
        self._captured_stdout.append(serialized)
        return msg

    def close(self) -> None:
        proc = self._proc
        if proc is not None:
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
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=2.0)
                self._stderr_thread = None
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        stderr_text = self._captured_stderr.decode("utf-8", errors="replace")
        assert_no_secrets_in_text(stderr_text, f"{self._label} shim stderr")


def cmd_init_broker() -> None:
    check_container_hardening("relay-broker")
    for docker_sock in DOCKER_SOCKET_PATHS:
        assert_path_inaccessible(docker_sock, "relay-broker docker.sock")
    for directory in (OP_DIR, PARENT_DIR, CHILD_DIR):
        assert_private_dir(directory, "relay-broker")

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        raise rs.SmokeError("relay-broker : charge d'initialisation JSON invalide.") from None
    proof = payload.get("proof") if isinstance(payload, dict) else None
    if not isinstance(proof, str) or len(proof) < 32:
        raise rs.SmokeError("relay-broker : justificatif d'enrôlement invalide.")

    OP_HOME.mkdir(mode=0o700, exist_ok=True)
    os.chmod(OP_HOME, 0o700)
    rs.write_private_file(PROOF_FILE, proof.encode("ascii"), 0o600)
    del proof

    cfg = build_broker_config()
    rs.write_private_file(
        CONFIG_FILE,
        (json.dumps(cfg, indent=2) + "\n").encode("utf-8"),
        0o600,
    )


def cmd_wait_broker(timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = True
        for sock_path in (PARENT_SOCKET, CONTROL_SOCKET):
            try:
                st = os.lstat(sock_path)
                if not stat.S_ISSOCK(st.st_mode):
                    ready = False
                    break
            except OSError:
                ready = False
                break
        if ready:
            assert_private_socket(PARENT_SOCKET, "relay-broker parent.sock")
            assert_private_socket(CONTROL_SOCKET, "relay-broker control.sock")
            rs.check_direct_without_dpop(GATEWAY_INTERNAL_URL)
            return read_netns_id()
        time.sleep(0.1)
    raise rs.SmokeError("relay-broker : sockets parent/contrôle non prêts dans le délai imparti.")


def cmd_parent_check(mock_ip: str, disallowed_netns: tuple[str, ...]) -> str:
    validated_ip = validate_private_ipv4(mock_ip)
    check_container_hardening("relay-parent")
    check_clean_env(dict(os.environ), "relay-parent", allow_image_vars=True)
    parent_netns = check_network_none_kernel("relay-parent", disallowed_netns=disallowed_netns)

    # Refus réseau : DNS amont/Gateway, IP privée réelle du mock, loopback Gateway isolé.
    assert_tcp_refused("upstream-mock", 9000, "relay-parent DNS upstream-mock")
    assert_tcp_refused("stoa-gateway", 8080, "relay-parent DNS stoa-gateway")
    assert_tcp_refused(validated_ip, 9000, "relay-parent IP privée mock")
    assert_tcp_refused("127.0.0.1", 8080, "relay-parent loopback Gateway")

    # Refus FS : socket Docker hôte, fichiers privés opérateur, espace enfant.
    for docker_sock in DOCKER_SOCKET_PATHS:
        assert_path_inaccessible(docker_sock, "relay-parent docker.sock")
    for op_path in OP_PRIVATE_PATHS:
        assert_path_inaccessible(op_path, "relay-parent op")
    assert_path_inaccessible(CHILD_DIR, "relay-parent child_dir")

    # Espace socket dédié parent : 0700, 1 seul socket 0600.
    assert_private_dir(PARENT_DIR, "relay-parent")
    parent_entries = sorted(p.name for p in PARENT_DIR.iterdir())
    if parent_entries != ["parent.sock"]:
        raise rs.SmokeError(f"relay-parent : contenu inattendu dans {PARENT_DIR} ({parent_entries}).")
    assert_private_socket(PARENT_SOCKET, "relay-parent")

    agent_home = Path("/tmp/agent-home")
    agent_home.mkdir(mode=0o700, exist_ok=True)
    os.chmod(agent_home, 0o700)

    with AuditedMcpStdioClient(
        STOACTL_CONTAINER_BIN, str(PARENT_SOCKET), agent_home, "parent"
    ) as parent:
        parent.initialize()
        parent_tools = parent.tools_list()
        if rs.TOOL not in parent_tools or rs.LIMITS_TOOL not in parent_tools:
            raise rs.SmokeError("Catalogue parent incomplet (refunds_create et stoa_security attendus).")
        rs.check_limits(
            parent,
            amount=rs.PARENT_LIMIT,
            customer=None,
            chain=2,
            caller=3,
            depth=0,
            label="parent",
        )
        rs.assert_refund_rejected(parent, rs.PARENT_LIMIT + 1, rs.OTHER_CUSTOMER, "parent >500 EUR")
        rs.assert_refund_accepted(parent, rs.PARENT_LIMIT, rs.OTHER_CUSTOMER, "parent 500 EUR")
    return parent_netns


def cmd_delegate() -> dict[str, Any]:
    delegated = rs.delegate_via_control(str(CONTROL_SOCKET), CHILD_DIR, str(PARENT_SOCKET))
    child_sock = Path(delegated["socket_path"])
    assert_private_socket(child_sock, "relay-broker child.sock")
    child_entries = sorted(p.name for p in CHILD_DIR.iterdir())
    if child_entries != [child_sock.name]:
        raise rs.SmokeError(
            f"relay-broker : attendu 1 seul socket dans {CHILD_DIR} (max_children=1), trouvé {len(child_entries)}."
        )
    return delegated


def cmd_parent_probe_child(child_socket: str) -> None:
    assert_path_inaccessible(CHILD_DIR, "relay-parent post-delegation child_dir")
    assert_path_inaccessible(Path(child_socket), "relay-parent post-delegation child_sock")


def cmd_child_check(
    mock_ip: str, child_socket: str, disallowed_netns: tuple[str, ...]
) -> str:
    validated_ip = validate_private_ipv4(mock_ip)
    check_container_hardening("relay-child")
    check_clean_env(dict(os.environ), "relay-child", allow_image_vars=True)
    child_netns = check_network_none_kernel("relay-child", disallowed_netns=disallowed_netns)

    # Refus réseau : DNS amont/Gateway, IP privée réelle du mock, loopback Gateway isolé.
    assert_tcp_refused("upstream-mock", 9000, "relay-child DNS upstream-mock")
    assert_tcp_refused("stoa-gateway", 8080, "relay-child DNS stoa-gateway")
    assert_tcp_refused(validated_ip, 9000, "relay-child IP privée mock")
    assert_tcp_refused("127.0.0.1", 8080, "relay-child loopback Gateway")

    # Refus FS : socket Docker hôte, fichiers privés opérateur, socket privilégié parent.
    for docker_sock in DOCKER_SOCKET_PATHS:
        assert_path_inaccessible(docker_sock, "relay-child docker.sock")
    for op_path in OP_PRIVATE_PATHS:
        assert_path_inaccessible(op_path, "relay-child op")
    assert_path_inaccessible(PARENT_DIR, "relay-child parent_dir")
    assert_path_inaccessible(PARENT_SOCKET, "relay-child parent_sock")

    # Espace socket dédié enfant : 0700, 1 seul socket 0600 (son propre socket).
    assert_private_dir(CHILD_DIR, "relay-child")
    child_sock_path = Path(child_socket).resolve()
    if CHILD_DIR.resolve() not in child_sock_path.parents:
        raise rs.SmokeError("relay-child : socket enfant hors de son volume dédié.")
    child_entries = sorted(p.name for p in CHILD_DIR.iterdir())
    if child_entries != [child_sock_path.name]:
        raise rs.SmokeError(
            f"relay-child : contenu inattendu dans {CHILD_DIR} ({len(child_entries)} entrée(s))."
        )
    assert_private_socket(child_sock_path, "relay-child")

    agent_home = Path("/tmp/agent-home")
    agent_home.mkdir(mode=0o700, exist_ok=True)
    os.chmod(agent_home, 0o700)

    with AuditedMcpStdioClient(
        STOACTL_CONTAINER_BIN, str(child_sock_path), agent_home, "enfant"
    ) as child:
        child.initialize()
        child_tools = child.tools_list()
        if rs.TOOL not in child_tools:
            raise rs.SmokeError("Catalogue enfant sans refunds_create.")
        if not set(child_tools).issubset({rs.TOOL, rs.LIMITS_TOOL}):
            raise rs.SmokeError("Catalogue enfant plus large que le périmètre délégué.")
        if rs.LIMITS_TOOL in child_tools:
            rs.check_limits(
                child,
                amount=rs.CHILD_LIMIT,
                customer=rs.DELEGATED_CUSTOMER,
                chain=1,
                caller=2,
                depth=1,
                label="enfant",
            )
        rs.assert_refund_rejected(
            child, rs.CHILD_EXCESS_AMOUNT, rs.DELEGATED_CUSTOMER, "enfant 80 EUR"
        )
        rs.assert_refund_rejected(
            child, rs.CHILD_LIMIT, rs.OTHER_CUSTOMER, "enfant mauvais client"
        )
        rs.assert_refund_accepted(
            child, rs.CHILD_ALLOWED_AMOUNT, rs.DELEGATED_CUSTOMER, "enfant 25 EUR"
        )
    return child_netns


def verify_upstream_stats(actual: Any) -> None:
    if not isinstance(actual, dict) or actual != EXPECTED_UPSTREAM_STATS:
        raise rs.SmokeError("Compteurs amont inattendus (2 remboursements et 0 auth appelant attendus).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preuve d'isolation Docker Compose du relais stoactl.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("runtime_root", type=Path)

    sub.add_parser("init-broker")

    p_wait = sub.add_parser("wait-broker")
    p_wait.add_argument("--timeout", type=float, default=15.0)

    p_parent = sub.add_parser("parent-check")
    p_parent.add_argument("--mock-ip", required=True)
    p_parent.add_argument("--disallowed-netns", action="append", default=[])

    sub.add_parser("delegate")

    p_probe = sub.add_parser("parent-probe-child")
    p_probe.add_argument("--child-socket", required=True)

    p_child = sub.add_parser("child-check")
    p_child.add_argument("--mock-ip", required=True)
    p_child.add_argument("--socket", required=True)
    p_child.add_argument("--disallowed-netns", action="append", default=[])

    p_insp = sub.add_parser("verify-inspect")
    p_insp.add_argument("--gateway-id", required=True)
    p_insp.add_argument("--broker-id", required=True)
    p_insp.add_argument("--parent-id", required=True)
    p_insp.add_argument("--child-id", required=True)

    sub.add_parser("verify-upstream")

    args = parser.parse_args()
    try:
        if args.cmd == "prepare":
            prepare_dock_runtime(args.runtime_root)
        elif args.cmd == "init-broker":
            cmd_init_broker()
        elif args.cmd == "wait-broker":
            broker_netns = cmd_wait_broker(args.timeout)
            print(broker_netns, flush=True)
        elif args.cmd == "parent-check":
            parent_netns = cmd_parent_check(args.mock_ip, tuple(args.disallowed_netns))
            print(parent_netns, flush=True)
        elif args.cmd == "delegate":
            delegated = cmd_delegate()
            print(json.dumps(delegated, separators=(",", ":")), flush=True)
        elif args.cmd == "parent-probe-child":
            cmd_parent_probe_child(args.child_socket)
        elif args.cmd == "child-check":
            child_netns = cmd_child_check(args.mock_ip, args.socket, tuple(args.disallowed_netns))
            print(child_netns, flush=True)
        elif args.cmd == "verify-inspect":
            try:
                records = json.load(sys.stdin)
            except ValueError:
                raise rs.SmokeError("docker inspect : JSON illisible.") from None
            verify_docker_inspect(
                records,
                gateway_id=args.gateway_id,
                broker_id=args.broker_id,
                parent_id=args.parent_id,
                child_id=args.child_id,
            )
        elif args.cmd == "verify-upstream":
            try:
                actual = json.load(sys.stdin)
            except ValueError:
                raise rs.SmokeError("Compteurs amont JSON illisibles.") from None
            verify_upstream_stats(actual)
    except rs.SmokeError as exc:
        print(f"ÉCHEC · {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
    except Exception as exc:
        print(f"ÉCHEC · erreur interne ({type(exc).__name__}).", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
