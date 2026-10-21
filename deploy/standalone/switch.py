#!/usr/bin/env python3
"""Point api.gostoa.dev at the STOA gateway, or put it back on APISIX.

Service/gateway in namespace stoa is not in this repo. Its selector is a map,
and `kubectl apply` merges map keys, so an apply of `app: stoa-gateway` would
leave the APISIX keys in place and the Service would match nothing (502).
This script `kubectl replace`s the live objects after editing them in memory.

  python3 deploy/standalone/switch.py stoa
  python3 deploy/standalone/switch.py apisix

The first `stoa` run saves the live selector, the port-9080 targetPort, and
the api.gostoa.dev Ingress paths into ConfigMap stoa-gateway-switch-backup.
`apisix` restores that ConfigMap. A later `kubectl apply -k deploy/standalone`
does not include Service/gateway, the Ingress, or the backup ConfigMap, so
it cannot undo a rollback or repeat a switch.

`apisix` restores the selector, targetPort and Ingress paths saved on the
first `stoa` run. With no backup it applies the versioned APISIX baseline:
selector `app=apisix`, port 9080 targetPort 9080, Ingress `stoa-api` host
`api.gostoa.dev` path Prefix `/`. Root `kubectl apply -k` does not include
those objects, so it cannot undo this.

`python3 deploy/standalone/switch.py --self-test` checks the public path
without talking to a cluster.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

NS = "stoa"
SERVICE = "gateway"
INGRESS = "stoa-api"
HOST = "api.gostoa.dev"
BACKUP = "stoa-gateway-switch-backup"
PUBLIC_PORT = 9080
STOA_SELECTOR = {"app": "stoa-gateway"}
APISIX_SELECTOR = {"app": "apisix"}
STOA_TARGET_PORT = 8080
APISIX_TARGET_PORT = 9080
# Anonymous call measured on APISIX before the switch. Rollback puts this
# path back on gateway:9080 (Prefix /). The gateway itself would 404 it.
LEGACY_ANON_PATH = "/demo-customer-referential/v1/customers/C-1001"
LEGACY_ANON_STATUS = 401


def kubectl_bin() -> str:
    """Operator binary. The review host sets K=~/stoa-deploy-bin/kubectl-stoa.

    `KUBECTL` wins, then `K`, then `kubectl-stoa` on PATH, then `kubectl`.
    """
    for key in ("KUBECTL", "K"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return os.path.expanduser(raw)
    found = shutil.which("kubectl-stoa")
    if found:
        return found
    return "kubectl"


def ingress_matches(rule: dict, request_path: str) -> bool:
    """Kubernetes Ingress Prefix match. Prefix `/` matches every path."""
    path = rule["path"]
    if rule.get("pathType") != "Prefix":
        return request_path == path
    if path == "/":
        return request_path.startswith("/")
    base = path.rstrip("/")
    return request_path == base or request_path.startswith(base + "/")


def legacy_anonymous_status(rule: dict, request_path: str) -> int:
    """Status of an anonymous call after rollback, without contacting the cluster.

    Prefix `/` to port 9080 is the APISIX route. That route answers 401.
    Any other backend (the STOA targetPort 8080) does not serve this URL.
    """
    port = rule["backend"]["service"]["port"]["number"]
    if port == APISIX_TARGET_PORT and ingress_matches(rule, request_path):
        return LEGACY_ANON_STATUS
    return 404


def stoa_paths() -> list[dict]:
    """The only public path. /admin is not in this list."""
    return [
        {
            "path": "/apis",
            "pathType": "Prefix",
            "backend": {
                "service": {"name": SERVICE, "port": {"number": PUBLIC_PORT}}
            },
        }
    ]


def apisix_catch_all_paths() -> list[dict]:
    return [
        {
            "path": "/",
            "pathType": "Prefix",
            "backend": {
                "service": {"name": SERVICE, "port": {"number": PUBLIC_PORT}}
            },
        }
    ]


def kubectl_json(*args: str) -> dict:
    out = subprocess.check_output([kubectl_bin(), *args, "-o", "json"], text=True)
    return json.loads(out)


def kubectl_replace(obj: dict) -> None:
    subprocess.run(
        [kubectl_bin(), "replace", "-f", "-"],
        input=json.dumps(obj),
        text=True,
        check=True,
    )


def backup_exists() -> bool:
    result = subprocess.run(
        [kubectl_bin(), "-n", NS, "get", "configmap", BACKUP],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def load_backup() -> dict | None:
    if not backup_exists():
        return None
    cm = kubectl_json("-n", NS, "get", "configmap", BACKUP)
    raw = (cm.get("data") or {}).get("backup")
    if not raw:
        sys.exit(f"ConfigMap {NS}/{BACKUP} has no data.backup")
    return json.loads(raw)


def save_backup(payload: dict) -> None:
    cm = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": BACKUP,
            "namespace": NS,
            "labels": {"app.kubernetes.io/part-of": "stoa-gateway-switch"},
        },
        "data": {"backup": json.dumps(payload)},
    }
    subprocess.run(
        [kubectl_bin(), "create", "-f", "-"],
        input=json.dumps(cm),
        text=True,
        check=True,
    )


def port_index(service: dict) -> int:
    for index, port in enumerate(service.get("spec", {}).get("ports") or []):
        if port.get("port") == PUBLIC_PORT:
            return index
    sys.exit(
        f"Service {NS}/{SERVICE} has no port {PUBLIC_PORT}. "
        "Refusing to change targetPort."
    )


def matching_rules(ingress_list: dict) -> list[tuple[dict, int]]:
    items = ingress_list.get("items")
    if items is None and ingress_list.get("kind") == "Ingress":
        items = [ingress_list]
    found: list[tuple[dict, int]] = []
    for item in items or []:
        if item.get("metadata", {}).get("name") != INGRESS:
            continue
        rules = (item.get("spec") or {}).get("rules") or []
        for index, rule in enumerate(rules):
            if rule.get("host") == HOST:
                found.append((item, index))
    if not found:
        sys.exit(
            f"Ingress {NS}/{INGRESS} has no rule for host {HOST}. "
            f"Check `kubectl -n {NS} get ingress {INGRESS} -o yaml`. "
            "Nothing was changed."
        )
    return found


def set_rule_paths(ingress: dict, rule_index: int, paths: list) -> None:
    ingress["spec"]["rules"][rule_index]["http"]["paths"] = paths


def apply_service(selector: dict, target_port) -> None:
    service = kubectl_json("-n", NS, "get", "svc", SERVICE)
    index = port_index(service)
    service["spec"]["selector"] = selector
    port = service["spec"]["ports"][index]
    port["targetPort"] = target_port
    if not port.get("name"):
        port["name"] = "http"
    kubectl_replace(service)
    print(
        f"Service {NS}/{SERVICE} selector={json.dumps(selector)} "
        f"port {PUBLIC_PORT} targetPort={target_port}"
    )


def apply_ingress_paths(paths_by_key: dict[tuple[str, int], list]) -> None:
    """paths_by_key maps (ingress name, rule index) to the replacement paths."""
    listing = kubectl_json("-n", NS, "get", "ingress")
    by_name = {item["metadata"]["name"]: item for item in listing.get("items") or []}
    touched: dict[str, dict] = {}
    for (name, rule_index), paths in paths_by_key.items():
        ingress = by_name.get(name)
        if ingress is None:
            sys.exit(f"Ingress {NS}/{name} disappeared before replace")
        obj = touched.setdefault(name, ingress)
        rules = (obj.get("spec") or {}).get("rules") or []
        if rule_index >= len(rules) or rules[rule_index].get("host") != HOST:
            sys.exit(
                f"Ingress {NS}/{name} rule {rule_index} is no longer host {HOST}"
            )
        set_rule_paths(obj, rule_index, paths)
    for name, obj in touched.items():
        kubectl_replace(obj)
        print(f"Ingress {NS}/{name} host {HOST} paths replaced")


def current_rule_paths() -> dict[tuple[str, int], list]:
    listing = kubectl_json("-n", NS, "get", "ingress")
    captured: dict[tuple[str, int], list] = {}
    for item, index in matching_rules(listing):
        name = item["metadata"]["name"]
        paths = ((item["spec"]["rules"][index].get("http") or {}).get("paths")) or []
        captured[(name, index)] = paths
    return captured


def switch_to_stoa() -> None:
    service = kubectl_json("-n", NS, "get", "svc", SERVICE)
    index = port_index(service)
    selector = (service.get("spec") or {}).get("selector") or {}
    if not backup_exists():
        if selector.get("app") == "stoa-gateway":
            sys.exit(
                f"Service {NS}/{SERVICE} already selects app=stoa-gateway and "
                f"ConfigMap {BACKUP} does not exist. Refusing to save this "
                "selector as the APISIX baseline."
            )
        rules = current_rule_paths()
        payload = {
            "selector": selector,
            "targetPort": service["spec"]["ports"][index].get("targetPort"),
            "rules": [
                {"name": name, "ruleIndex": rule_index, "paths": paths}
                for (name, rule_index), paths in rules.items()
            ],
        }
        save_backup(payload)
        print(f"saved ConfigMap {NS}/{BACKUP}")
    paths = {key: stoa_paths() for key in current_rule_paths()}
    apply_service(STOA_SELECTOR, STOA_TARGET_PORT)
    apply_ingress_paths(paths)
    print("switched api.gostoa.dev to stoa-gateway (8080, /apis only)")


def versioned_apisix_paths() -> dict[tuple[str, int], list]:
    """Original stoa-api rule: Prefix `/` to gateway:9080 (APISIX)."""
    return {key: apisix_catch_all_paths() for key in current_rule_paths()}


def switch_to_apisix() -> None:
    """Versioned rollback: selector app=apisix, targetPort 9080, stoa-api path `/`.

    A backup captured by the first switch wins when it has a selector and
    rules, so a non-default APISIX selector is not flattened. Without a
    backup the versioned baseline above is applied. `kubectl apply -k
    deploy/standalone` does not include Service/gateway or Ingress/stoa-api.
    """
    saved = load_backup()
    selector = APISIX_SELECTOR
    target = APISIX_TARGET_PORT
    paths = None
    if saved:
        print("backup", json.dumps(saved))
        backed_selector = saved.get("selector")
        if isinstance(backed_selector, dict) and backed_selector:
            selector = backed_selector
        if saved.get("targetPort") is not None:
            target = saved["targetPort"]
        restored = {
            (rule["name"], rule["ruleIndex"]): rule["paths"]
            for rule in saved.get("rules") or []
            if rule.get("paths")
        }
        if restored:
            paths = restored
    if paths is None:
        paths = versioned_apisix_paths()
        selector = APISIX_SELECTOR
        target = APISIX_TARGET_PORT
    apply_service(selector, target)
    apply_ingress_paths(paths)
    print(
        f"rolled back {INGRESS} to selector={json.dumps(selector)} "
        f"targetPort={target}"
    )


SENTINEL = "REPLACE_WITH_INGRESS_NGINX_POD_IPS"
INGRESS_NS = "ingress-nginx"
INGRESS_LABEL = "app.kubernetes.io/name=ingress-nginx"
IMAGE_REFS = (
    "docker.io/library/stoa-gateway:standalone",
    "stoa-gateway:standalone",
)
REVISION_LABEL = "org.opencontainers.image.revision"
HERE = Path(__file__).resolve().parent


class PreflightError(Exception):
    """Switch refused before any live Service or Ingress change."""


def ingress_pod_ips(pod_list: dict) -> list[str]:
    """Pod IPs of Running ingress-nginx pods. Never a node prefix."""
    ips: list[str] = []
    for item in pod_list.get("items") or []:
        status = item.get("status") or {}
        if status.get("phase") != "Running":
            continue
        ip = status.get("podIP")
        if not isinstance(ip, str) or not ip or "/" in ip:
            continue
        ipaddress.ip_address(ip)
        ips.append(ip)
    if not ips:
        raise PreflightError(
            "no Running ingress-nginx pod IP; refusing to switch"
        )
    return sorted(set(ips))


def proxy_value(ips: list[str]) -> str:
    """Comma-separated host addresses. A prefix wider than one host is refused."""
    if not ips:
        raise PreflightError("no ingress-nginx pod IP")
    for ip in ips:
        if "/" in ip:
            raise PreflightError(f"refusing prefix {ip}; use the pod IP only")
        ipaddress.ip_address(ip)
    return ",".join(ips)


def assert_host_only(value: str) -> None:
    """Accept bare IPs and /32 or /128. Refuse the sentinel and any wider prefix."""
    if SENTINEL in value or not value.strip():
        raise PreflightError(
            "STOA_TRUSTED_PROXIES still contains the sentinel "
            f"{SENTINEL}; refusing to switch"
        )
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise PreflightError("STOA_TRUSTED_PROXIES is empty; refusing to switch")
    for part in parts:
        if "/" not in part:
            ipaddress.ip_address(part)
            continue
        network = ipaddress.ip_network(part, strict=False)
        if network.prefixlen != network.max_prefixlen:
            raise PreflightError(
                f"refusing {part}: only the ingress-nginx pod IP is allowed, "
                "never a node /24"
            )


def find_revision(node) -> str | None:
    """OCI revision label anywhere in a ctr/crictl inspect document."""
    if isinstance(node, dict):
        labels = node.get("Labels")
        if isinstance(labels, dict) and labels.get(REVISION_LABEL):
            return str(labels[REVISION_LABEL])
        info = node.get("info")
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except json.JSONDecodeError:
                info = None
            if info is not None:
                found = find_revision(info)
                if found:
                    return found
        for value in node.values():
            found = find_revision(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_revision(value)
            if found:
                return found
    return None


def manifest_digest(inspect: dict) -> str:
    target = inspect.get("Target") or inspect.get("target") or {}
    digest = target.get("digest") or target.get("Digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise PreflightError(f"image inspect has no manifest digest ({digest!r})")
    return digest


def config_digest(manifest: dict) -> str:
    digest = (manifest.get("config") or {}).get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise PreflightError(f"image manifest has no config digest ({digest!r})")
    return digest


def expected_revision() -> str:
    override = os.environ.get("STOA_EXPECTED_REVISION", "").strip()
    if override:
        return override
    path = HERE / "IMAGE-REVISION"
    if not path.is_file():
        raise PreflightError(
            f"missing {path}. Run deploy/standalone/build-image.sh and import "
            "that tar on worker-3."
        )
    line = path.read_text().strip().splitlines()[0].strip()
    if not re.fullmatch(r"[0-9a-f]{40}", line):
        raise PreflightError(f"{path} is not a 40-character git SHA ({line!r})")
    return line


def _ssh(host: str, script: str) -> str:
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            host,
            script,
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PreflightError(detail or f"ssh {host} failed")
    return result.stdout


def _ctr_json(host: str, script: str) -> dict:
    raw = _ssh(host, script).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PreflightError(f"ctr on {host} did not return JSON: {exc}") from exc


def image_revision_on_node(host: str) -> str:
    """Read org.opencontainers.image.revision from the imported image."""
    inspect = None
    chosen = None
    for ref in IMAGE_REFS:
        try:
            inspect = _ctr_json(
                host,
                f"sudo k3s ctr -n k8s.io images inspect {ref}",
            )
            chosen = ref
            break
        except PreflightError:
            continue
    if inspect is None or chosen is None:
        raise PreflightError(
            f"{host} has no stoa-gateway:standalone image in k3s containerd. "
            "Import the tar from build-image.sh before switching. "
            "imagePullPolicy is Never."
        )
    manifest = _ctr_json(
        host,
        f"sudo k3s ctr -n k8s.io content get {manifest_digest(inspect)}",
    )
    config = _ctr_json(
        host,
        f"sudo k3s ctr -n k8s.io content get {config_digest(manifest)}",
    )
    found = find_revision(config)
    if not found:
        raise PreflightError(
            f"{chosen} on {host} has no {REVISION_LABEL} label. "
            "Import the image built by deploy/standalone/build-image.sh."
        )
    return found


def confirm_image(host: str, revision: str) -> None:
    found = image_revision_on_node(host)
    if found != revision:
        raise PreflightError(
            f"image on {host} is revision {found}, expected {revision}. "
            "Import the tar from that build before switching."
        )
    print(f"image on {host}: stoa-gateway:standalone revision {found}")


def trusted_proxy_value() -> str:
    cm = kubectl_json("-n", NS, "get", "configmap", "stoa-gateway")
    value = (cm.get("data") or {}).get("STOA_TRUSTED_PROXIES")
    if not isinstance(value, str):
        raise PreflightError("ConfigMap stoa-gateway has no STOA_TRUSTED_PROXIES")
    return value


def install_ingress_pod_ips() -> str:
    """Write the current ingress-nginx pod IPs into the live ConfigMap."""
    pods = kubectl_json(
        "-n",
        INGRESS_NS,
        "get",
        "pods",
        "-l",
        INGRESS_LABEL,
    )
    value = proxy_value(ingress_pod_ips(pods))
    patch = json.dumps({"data": {"STOA_TRUSTED_PROXIES": value}})
    subprocess.run(
        [
            kubectl_bin(),
            "-n",
            NS,
            "patch",
            "configmap",
            "stoa-gateway",
            "--type",
            "merge",
            "-p",
            patch,
        ],
        check=True,
    )
    live = trusted_proxy_value()
    assert_host_only(live)
    print(f"STOA_TRUSTED_PROXIES={live}")
    return live


def restart_gateway() -> None:
    """Reload the ConfigMap. envFrom is read at process start."""
    subprocess.run(
        [kubectl_bin(), "-n", NS, "rollout", "restart", "deployment/stoa-gateway"],
        check=True,
    )
    subprocess.run(
        [
            kubectl_bin(),
            "-n",
            NS,
            "rollout",
            "status",
            "deployment/stoa-gateway",
            "--timeout=180s",
        ],
        check=True,
    )


def backup_volumes(host: str) -> None:
    """Snapshot PVCs on the node before Service/gateway is retargeted.

    `systemctl start` waits for the oneshot. A non-zero status refuses the
    switch. This does not print the archive; the operator checks the journal.
    """
    _ssh(host, "sudo systemctl start stoa-pvc-backup.service")
    print(f"volume backup finished on {host} (stoa-pvc-backup.service)")


def preflight() -> None:
    """Image revision on worker-3, volume backup, then ingress-nginx pod IPs.

    Does not retarget Service/gateway or Ingress stoa-api. switch.sh calls
    this before `switch.py stoa`. A node /24 is never written. The backup
    runs before the ConfigMap patch and the rollout restart.
    """
    host = os.environ.get("STOA_NODE_SSH", "worker-3").strip() or "worker-3"
    revision = expected_revision()
    confirm_image(host, revision)
    backup_volumes(host)
    install_ingress_pod_ips()
    restart_gateway()
    print("preflight ok")


def self_test() -> None:
    paths = stoa_paths()
    assert len(paths) == 1
    assert paths[0]["path"] == "/apis"
    assert paths[0]["pathType"] == "Prefix"
    assert paths[0]["backend"]["service"]["name"] == "gateway"
    assert paths[0]["backend"]["service"]["port"]["number"] == 9080
    blob = json.dumps(paths)
    assert "/admin" not in blob
    assert '"path": "/"' not in blob
    catch_all = apisix_catch_all_paths()
    assert catch_all[0]["path"] == "/"
    assert catch_all[0]["backend"]["service"]["port"]["number"] == 9080
    assert ingress_matches(catch_all[0], LEGACY_ANON_PATH)
    assert not any(ingress_matches(rule, LEGACY_ANON_PATH) for rule in paths)
    assert legacy_anonymous_status(catch_all[0], LEGACY_ANON_PATH) == 401
    assert (
        legacy_anonymous_status(paths[0], LEGACY_ANON_PATH) == 404
    ), "the stoa /apis rule must not answer the old APISIX URL"
    assert INGRESS == "stoa-api"
    assert STOA_SELECTOR == {"app": "stoa-gateway"}
    assert STOA_TARGET_PORT == 8080
    assert APISIX_SELECTOR == {"app": "apisix"}
    assert APISIX_TARGET_PORT == 9080
    forbidden = ("/admin", "/metrics", "/mcp", "/oauth/register", "/v1/messages")
    for path in forbidden:
        assert path not in blob
    ips = ingress_pod_ips(
        {
            "items": [
                {"status": {"phase": "Running", "podIP": "10.42.0.15"}},
                {"status": {"phase": "Pending", "podIP": "10.42.0.16"}},
                {"status": {"phase": "Running", "podIP": "10.42.0.15"}},
            ]
        }
    )
    assert ips == ["10.42.0.15"]
    assert proxy_value(ips) == "10.42.0.15"
    assert_host_only("10.42.0.15")
    assert_host_only("10.42.0.15/32")
    for bad in (
        SENTINEL,
        "10.42.0.0/24",
        "10.42.0.0/16",
        "",
        f"10.42.0.15,{SENTINEL}",
    ):
        try:
            assert_host_only(bad)
        except PreflightError:
            pass
        else:
            raise AssertionError(bad)
    try:
        ingress_pod_ips({"items": []})
    except PreflightError:
        pass
    else:
        raise AssertionError("empty pod list")
    label = "29955d56cdee022caf3d57442027902d3ae39fad"
    doc = {
        "config": {
            "Labels": {REVISION_LABEL: label},
        }
    }
    assert find_revision(doc) == label
    assert find_revision({"info": json.dumps(doc)}) == label
    assert (
        manifest_digest({"Target": {"digest": "sha256:" + "ab" * 32}})
        == "sha256:" + "ab" * 32
    )
    assert (
        config_digest({"config": {"digest": "sha256:" + "cd" * 32}})
        == "sha256:" + "cd" * 32
    )
    print("switch.py self-test ok")
    previous = {key: os.environ.get(key) for key in ("K", "KUBECTL")}
    os.environ["K"] = "~/stoa-deploy-bin/kubectl-stoa"
    os.environ.pop("KUBECTL", None)
    try:
        assert kubectl_bin() == os.path.expanduser("~/stoa-deploy-bin/kubectl-stoa")
        os.environ["KUBECTL"] = "/usr/bin/kubectl"
        assert kubectl_bin() == "/usr/bin/kubectl"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print("kubectl binary selection ok")


def main(argv: list[str]) -> None:
    if len(argv) != 2 or argv[1] not in {"stoa", "apisix", "preflight", "--self-test"}:
        sys.exit(
            "usage: switch.py preflight | stoa | apisix | --self-test\n"
            "  preflight  require the imported image revision on worker-3,\n"
            "             snapshot PVCs (stoa-pvc-backup.service) before any\n"
            "             change, set STOA_TRUSTED_PROXIES to the ingress-nginx\n"
            "             pod IPs (never a node /24), restart the deployment\n"
            "  stoa       Service/gateway -> app=stoa-gateway, targetPort 8080,\n"
            "             Ingress host api.gostoa.dev paths replaced with /apis\n"
            "  apisix     restore the selector, targetPort, and paths saved on\n"
            "             the first stoa run"
        )
    try:
        if argv[1] == "--self-test":
            self_test()
        elif argv[1] == "preflight":
            preflight()
        elif argv[1] == "stoa":
            switch_to_stoa()
        else:
            switch_to_apisix()
    except PreflightError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main(sys.argv)
