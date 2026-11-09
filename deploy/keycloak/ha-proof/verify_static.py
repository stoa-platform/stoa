# SPDX-License-Identifier: Apache-2.0
"""Static HA check for the STOA identity service (Keycloak).

Reads charts and the in-repo compose files. Prints a report and exits 0 when
the report is produced. HA_STATIC=fail means this repository does not prove
failover for the retained sizing. No cluster, kubeconfig, or secret is used.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
CHART = REPO / "charts" / "stoa-platform"
COMPOSE = REPO / "deploy" / "docker-compose" / "docker-compose.yml"
QUICKSTART = REPO / "quickstart" / "docker-compose.yml"
GATEWAY_PDB = CHART / "templates" / "stoa-gateway-pdb.yaml"
SCAN_ROOTS = (CHART / "templates", REPO / "k8s", REPO / "deploy")
WORKLOAD_KINDS = {"Deployment", "StatefulSet"}
DISCOVERY = ("jdbc-ping", "dns_ping", "dns-ping", "kubernetes")


@dataclass(frozen=True)
class Gap:
    id: str
    detail: str


@dataclass(frozen=True)
class Report:
    prod_replicas: int | None
    staging_replicas: int | None
    dev_replicas: int | None
    base_replicas: int | None
    compose_replicas: int
    compose_cache: str | None
    compose_cache_stack: str | None
    compose_named: bool
    compose_healthcheck: bool
    quickstart_replicas: int
    quickstart_dev_mode: bool
    quickstart_cache: str | None
    workloads: tuple[str, ...]
    pdbs: tuple[str, ...]
    anti_affinity: bool
    k8s_probes: bool
    shared_cache: bool
    gaps: tuple[Gap, ...]

    @property
    def in_repo_replicas(self) -> int:
        return max(self.compose_replicas, self.quickstart_replicas)

    @property
    def ha_static(self) -> str:
        proven = (
            not self.gaps
            and self.in_repo_replicas >= 2
            and self.shared_cache
            and self.anti_affinity
            and self.k8s_probes
            and bool(self.pdbs)
        )
        return "pass" if proven else "fail"

    def shell(self) -> str:
        retained = self.prod_replicas if self.prod_replicas is not None else "missing"
        shared = "true" if self.shared_cache else "false"
        return (
            f"HA_STATIC={self.ha_static}\n"
            f"RETAINED_PROD_REPLICAS={retained}\n"
            f"IN_REPO_REPLICAS={self.in_repo_replicas}\n"
            f"SHARED_CACHE={shared}\n"
        )

    def text(self) -> str:
        lines = [
            "Identity service HA — static proof (Keycloak)",
            f"HA_STATIC={self.ha_static}",
            "",
            "Retained reference (not a rendered workload):",
            f"  charts/stoa-platform/values-prod.yaml keycloak.replicas={self.prod_replicas}",
            f"  charts/stoa-platform/values-staging.yaml keycloak.replicas={self.staging_replicas}",
            f"  charts/stoa-platform/values-dev.yaml keycloak.replicas={self.dev_replicas}",
            f"  charts/stoa-platform/values.yaml keycloak.replicas={self.base_replicas}",
            "  Comment in those files: counts are REFERENCE ONLY; the chart lives in",
            "  stoa-infra charts/keycloak/, with JGroups DNS_PING claimed when replicas > 1.",
            "",
            "In-repo runnable identity workloads:",
            f"  deploy/docker-compose: replicas={self.compose_replicas} "
            f"cache={self.compose_cache!s} stack={self.compose_cache_stack!s} "
            f"container_name={self.compose_named} healthcheck={self.compose_healthcheck}",
            f"  quickstart/docker-compose: replicas={self.quickstart_replicas} "
            f"start-dev={self.quickstart_dev_mode} cache={self.quickstart_cache!s}",
            f"  Kubernetes Deployment/StatefulSet for Keycloak: {list(self.workloads) or 'none'}",
            "",
            "Controls checked on identity workloads:",
            f"  pod anti-affinity: {self.anti_affinity}",
            f"  PodDisruptionBudget selecting keycloak: {list(self.pdbs) or 'none'}",
            f"  readiness and liveness probes: {self.k8s_probes}",
            f"  shared session cache: {self.shared_cache}",
            "  values-prod.yaml podDisruptionBudget feeds stoa-gateway, not Keycloak.",
            "",
            "Gaps (current sizing left unchanged):",
        ]
        lines.extend(f"  - {gap.id}: {gap.detail}" for gap in self.gaps)
        lines.extend(
            [
                "",
                "Proven statically: the reference counts, and that no in-repo manifest",
                "implements multi-replica Keycloak with anti-affinity, a Keycloak PDB,",
                "Kubernetes probes, and a shared session cache.",
                "Still to prove live, outside this repository: the stoa-infra chart",
                "(replicas, DNS_PING or jdbc-ping, PDB, spread, probes), then a bascule",
                "that keeps an existing session and a new token valid after one loss.",
                "This checker does not contact a cluster.",
                "",
            ]
        )
        return "\n".join(lines)


def tolerated_losses(replicas: int, shared_cache: bool) -> int:
    """Active-active identity tier: one loss is tolerable only with a shared cache."""
    if replicas >= 2 and shared_cache:
        return replicas - 1
    return 0


def _replicas(values: dict) -> int | None:
    keycloak = values.get("keycloak")
    if not isinstance(keycloak, dict) or "replicas" not in keycloak:
        return None
    return int(keycloak["replicas"])


def _env(service: dict) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    mapped: dict[str, str] = {}
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            mapped[key] = value
    return mapped


def _service_replicas(service: dict) -> int:
    deploy = service.get("deploy") if isinstance(service.get("deploy"), dict) else {}
    if "replicas" in deploy:
        return int(deploy["replicas"])
    return 1


def _discovery(*parts: str) -> bool:
    blob = " ".join(parts).lower()
    return any(token in blob for token in DISCOVERY)


def _shared(replicas: int, cache: str | None, stack: str | None, command: str) -> bool:
    return replicas >= 2 and cache == "ispn" and (bool(stack) or _discovery(command))


def _load(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} root is not a mapping")
    return loaded


def _service(path: Path, name: str) -> dict:
    service = (_load(path).get("services") or {}).get(name)
    if not isinstance(service, dict):
        raise ValueError(f"{path} has no {name} service")
    return service


def _command(service: dict) -> str:
    command = service.get("command")
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command or "")


def _iter_files():
    seen: set[Path] = set()
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".yaml", ".yml"} or not path.is_file():
                continue
            if path in seen or path.stat().st_size > 1_000_000:
                continue
            seen.add(path)
            yield path


def _docs(path: Path):
    text = path.read_text(encoding="utf-8")
    if "{{" in text:
        return text, []
    try:
        docs = [doc for doc in yaml.safe_load_all(text) if isinstance(doc, dict)]
    except yaml.YAMLError:
        return text, []
    return text, docs


def _labels(doc: dict) -> dict:
    return ((doc.get("metadata") or {}).get("labels") or {}) if isinstance(doc, dict) else {}


def _identity_doc(doc: dict) -> bool:
    if doc.get("kind") not in WORKLOAD_KINDS:
        return False
    meta = doc.get("metadata") or {}
    labels = _labels(doc)
    name = str(meta.get("name", ""))
    image_blob = yaml.safe_dump(doc.get("spec") or {})
    named = name == "keycloak" or labels.get("app.kubernetes.io/name") == "keycloak"
    named = named or labels.get("app") == "keycloak"
    return named or "keycloak/keycloak" in image_blob


def _identity_template(text: str) -> bool:
    if not re.search(r"(?m)^kind:\s*(Deployment|StatefulSet)\s*$", text):
        return False
    if re.search(r"(?i)keycloak/keycloak", text):
        return True
    return bool(re.search(r"(?m)^\s+name:\s+keycloak\s*$", text))


def _pdb_doc(doc: dict) -> bool:
    if doc.get("kind") != "PodDisruptionBudget":
        return False
    labels = ((doc.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
    return "keycloak" in " ".join(str(value).lower() for value in labels.values())


def _pdb_template(text: str) -> bool:
    if not re.search(r"(?m)^kind:\s*PodDisruptionBudget\s*$", text):
        return False
    return bool(
        re.search(
            r"(?m)^\s+(app|app\.kubernetes\.io/name|app\.kubernetes\.io/component):\s+keycloak\s*$",
            text,
        )
    )


def _anti_affinity(doc: dict) -> bool:
    affinity = ((doc.get("spec") or {}).get("template") or {}).get("spec") or {}
    return "podAntiAffinity" in (affinity.get("affinity") or {})


def _probes(doc: dict) -> bool:
    containers = (((doc.get("spec") or {}).get("template") or {}).get("spec") or {}).get(
        "containers"
    ) or []
    found = False
    for container in containers:
        if not isinstance(container, dict):
            continue
        if "readinessProbe" in container and "livenessProbe" in container:
            found = True
    return found


def _scan() -> dict:
    workloads: list[str] = []
    pdbs: list[str] = []
    anti = False
    probes = False
    for path in _iter_files():
        relative = path.relative_to(REPO).as_posix()
        text, docs = _docs(path)
        identity_docs = [doc for doc in docs if _identity_doc(doc)]
        if identity_docs or (not docs and _identity_template(text)):
            workloads.append(relative)
        if any(_pdb_doc(doc) for doc in docs) or (not docs and _pdb_template(text)):
            pdbs.append(relative)
        anti = anti or any(_anti_affinity(doc) for doc in identity_docs)
        if identity_docs:
            probes = probes or any(_probes(doc) for doc in identity_docs)
        elif not docs and _identity_template(text):
            probes = probes or (
                "readinessProbe:" in text and "livenessProbe:" in text
            )
            anti = anti or "podAntiAffinity:" in text
    return {
        "workloads": tuple(workloads),
        "pdbs": tuple(pdbs),
        "anti_affinity": anti,
        "k8s_probes": probes,
    }


def analyze() -> Report:
    """Build the static report from the repository that contains this file."""
    prod = _replicas(_load(CHART / "values-prod.yaml"))
    staging = _replicas(_load(CHART / "values-staging.yaml"))
    dev = _replicas(_load(CHART / "values-dev.yaml"))
    base = _replicas(_load(CHART / "values.yaml"))
    compose = _service(COMPOSE, "keycloak")
    quickstart = _service(QUICKSTART, "keycloak")
    compose_env = _env(compose)
    quick_env = _env(quickstart)
    compose_cache = compose_env.get("KC_CACHE")
    compose_stack = compose_env.get("KC_CACHE_STACK")
    quick_cache = quick_env.get("KC_CACHE")
    compose_replicas = _service_replicas(compose)
    quick_replicas = _service_replicas(quickstart)
    quick_command = _command(quickstart)
    scan = _scan()
    shared = _shared(compose_replicas, compose_cache, compose_stack, _command(compose)) or _shared(
        quick_replicas, quick_cache, quick_env.get("KC_CACHE_STACK"), quick_command
    )
    gateway_pdb = GATEWAY_PDB.read_text(encoding="utf-8")
    if "app.kubernetes.io/name: stoa-gateway" not in gateway_pdb or "keycloak" in gateway_pdb:
        raise ValueError("stoa-gateway PDB template no longer matches the expected selector")

    gaps: list[Gap] = []
    if base is None:
        gaps.append(
            Gap(
                "reference-only",
                f"prod={prod}, staging={staging}, dev={dev} are reference counts; "
                "values.yaml sets none, and this chart renders no Keycloak workload "
                "(stoa-infra charts/keycloak/ owns it and is not in this repo).",
            )
        )
    if not scan["workloads"]:
        gaps.append(
            Gap(
                "no-identity-workload",
                "no Deployment or StatefulSet named or imaged as Keycloak under charts/, k8s/, or deploy/.",
            )
        )
    if not scan["pdbs"]:
        gaps.append(
            Gap(
                "no-keycloak-pdb",
                "no PodDisruptionBudget selects Keycloak. values-prod.yaml podDisruptionBudget "
                "is consumed by templates/stoa-gateway-pdb.yaml (app.kubernetes.io/name: stoa-gateway).",
            )
        )
    if not scan["anti_affinity"]:
        gaps.append(
            Gap(
                "no-anti-affinity",
                "no podAntiAffinity on an in-repo Keycloak workload.",
            )
        )
    if not scan["k8s_probes"]:
        gaps.append(
            Gap(
                "no-k8s-probes",
                "no Keycloak workload defines both readinessProbe and livenessProbe. "
                "The compose healthcheck is process-local only.",
            )
        )
    if compose_replicas < 2 or compose.get("container_name"):
        gaps.append(
            Gap(
                "compose-single-replica",
                "deploy/docker-compose keycloak is a single service"
                + (" with container_name, which blocks `compose scale`." if compose.get("container_name") else "."),
            )
        )
    if not shared:
        gaps.append(
            Gap(
                "cache-not-shared",
                f"platform compose sets KC_CACHE={compose_cache!s} without KC_CACHE_STACK "
                f"and with {compose_replicas} replica; quickstart cache={quick_cache!s}. "
                "ispn on one process is not a shared session cache.",
            )
        )
    if quick_replicas < 2 or "start-dev" in quick_command:
        gaps.append(
            Gap(
                "quickstart-dev-mode",
                "quickstart/docker-compose.yml runs one Keycloak in start-dev with no KC_CACHE.",
            )
        )
    return Report(
        prod_replicas=prod,
        staging_replicas=staging,
        dev_replicas=dev,
        base_replicas=base,
        compose_replicas=compose_replicas,
        compose_cache=compose_cache,
        compose_cache_stack=compose_stack,
        compose_named=bool(compose.get("container_name")),
        compose_healthcheck="healthcheck" in compose,
        quickstart_replicas=quick_replicas,
        quickstart_dev_mode="start-dev" in quick_command,
        quickstart_cache=quick_cache,
        workloads=scan["workloads"],
        pdbs=scan["pdbs"],
        anti_affinity=scan["anti_affinity"],
        k8s_probes=scan["k8s_probes"],
        shared_cache=shared,
        gaps=tuple(gaps),
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    report = analyze()
    sys.stdout.write(report.shell() if "--shell" in args else report.text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
