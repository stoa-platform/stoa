"""Offline traversal, inventory and audit orchestration."""

from __future__ import annotations

import ast

from keycloak_audit_lib.common import (
    Finding,
    category,
    credential_path,
    environment,
    files,
    line_for,
    relevant,
)
from keycloak_audit_lib.declarations import inspect_representations
from keycloak_audit_lib.lexical import lexical_checks
from keycloak_audit_lib.parsing import parse_representations
from keycloak_audit_lib.representation import RepresentationRules


class Audit(RepresentationRules):
    def __init__(self, mode="auto"):
        self.mode = mode
        self.findings: list[Finding] = []
        self.inventory = []
        self.errors = False

    def add(self, path, text, rule, message, key="", start=1, severity="HIGH", dev_warning=False):
        env = environment(path, self.mode)
        if env == "dev" and dev_warning:
            severity = "WARN"
        self.findings.append(
            Finding(
                path, line_for(text, key, start) if key else start, rule, severity, env, message
            )
        )

    def audit_text(self, path, text):
        kind = category(path, text)
        self.inventory.append(
            {
                "file": path,
                "category": kind,
                "environment": environment(path, self.mode),
                "status": "read",
            }
        )
        if kind in {"documentation", "consumer", "checker"} and not path.endswith(".json"):
            return

        representations = parse_representations(self, path, text, kind)
        if representations is None:
            return
        inspect_representations(self, path, text, representations)
        lexical_checks(self, path, text)
        if kind in {"bootstrap", "runtime"} and path.endswith((".py", ".sh")):
            self.add(
                path,
                text,
                "KC_DYNAMIC_REVIEW",
                "Analyse statique partielle : conditions, substitutions et appels externes à revoir.",
                severity="REVIEW",
            )
        if path.endswith(".py"):
            self.python_literals(path, text)
        if path.endswith("templates/bootstrap-job.yaml"):
            self.add(
                path,
                text,
                "KC_EXISTING_STATE",
                "Vérifier la branche objets existants : un import initial ne réconcilie pas les paramètres.",
                severity="REVIEW",
            )
        if kind == "network":
            self.add(
                path,
                text,
                "KC_NETWORK_REVIEW",
                "Valider les labels, namespaces, ports Service/Pod et politiques cumulées hors de cette analyse.",
                severity="REVIEW",
            )

    def python_literals(self, path, text):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            self.errors = True
            self.add(
                path, text, "KC_PARSE", "Python non analysable ; détails masqués.", severity="ERROR"
            )
            return
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            obj = {}
            for k, v in zip(node.keys, node.values, strict=True):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    try:
                        obj[k.value] = ast.literal_eval(v)
                    except (ValueError, TypeError):
                        obj[k.value] = "${DYNAMIC}"
            if "clientId" in obj:
                # Normalize dynamic nested collections; still flag missing proof.
                for k in ("attributes",):
                    if k in obj and not isinstance(obj[k], dict):
                        obj[k] = {}
                for k in ("defaultClientScopes", "protocolMappers"):
                    if k in obj and not isinstance(obj[k], list):
                        obj[k] = []
                self.representation(path, text, obj, node.lineno)

    def scan(self, root):
        for p in files(root):
            rel = p.relative_to(root).as_posix()
            if credential_path(p):
                self.inventory.append(
                    {"file": rel, "category": "excluded", "status": "credential-path-not-read"}
                )
                continue
            try:
                raw = p.read_bytes()
            except OSError:
                self.errors = True
                self.inventory.append({"file": rel, "category": "error", "status": "unreadable"})
                continue
            if raw.startswith(b"\x00GITCRYPT"):
                self.inventory.append(
                    {"file": rel, "category": "opaque", "status": "encrypted-not-decrypted"}
                )
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if relevant(rel, text):
                self.audit_text(rel, text)
        unique = {}
        for finding in self.findings:
            unique.setdefault(
                (finding.file, finding.line, finding.rule, finding.severity, finding.environment),
                finding,
            )
        self.findings = sorted(unique.values())
        return self
