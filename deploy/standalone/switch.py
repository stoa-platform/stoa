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

import json
import subprocess
import sys

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
    out = subprocess.check_output(["kubectl", *args, "-o", "json"], text=True)
    return json.loads(out)


def kubectl_replace(obj: dict) -> None:
    subprocess.run(
        ["kubectl", "replace", "-f", "-"],
        input=json.dumps(obj),
        text=True,
        check=True,
    )


def backup_exists() -> bool:
    result = subprocess.run(
        ["kubectl", "-n", NS, "get", "configmap", BACKUP],
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
        ["kubectl", "create", "-f", "-"],
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
    assert INGRESS == "stoa-api"
    assert STOA_SELECTOR == {"app": "stoa-gateway"}
    assert STOA_TARGET_PORT == 8080
    assert APISIX_SELECTOR == {"app": "apisix"}
    assert APISIX_TARGET_PORT == 9080
    forbidden = ("/admin", "/metrics", "/mcp", "/oauth/register", "/v1/messages")
    for path in forbidden:
        assert path not in blob
    print("switch.py self-test ok")


def main(argv: list[str]) -> None:
    if len(argv) != 2 or argv[1] not in {"stoa", "apisix", "--self-test"}:
        sys.exit(
            "usage: switch.py stoa | apisix | --self-test\n"
            "  stoa    Service/gateway -> app=stoa-gateway, targetPort 8080,\n"
            "          Ingress host api.gostoa.dev paths replaced with /apis\n"
            "  apisix  restore the selector, targetPort, and paths saved on\n"
            "          the first stoa run"
        )
    if argv[1] == "--self-test":
        self_test()
    elif argv[1] == "stoa":
        switch_to_stoa()
    else:
        switch_to_apisix()


if __name__ == "__main__":
    main(sys.argv)
