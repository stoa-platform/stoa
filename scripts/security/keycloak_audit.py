#!/usr/bin/env python3
"""Contrôle statique hors ligne. N'exécute ni shell, ni Helm, ni code du dépôt.

Python >= 3.11, PyYAML pour les YAML (aucun téléchargement automatique).
Sortie sans extraits de sources, identités, URI ou valeurs de secrets.
Codes: 0 = aucune violation, 1 = violations, 2 = erreur/couverture incomplète.
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from keycloak_audit_lib.audit import Audit as Audit
from keycloak_audit_lib.common import (
    API_CLIENTS as API_CLIENTS,
    ATTR_BOUNDS as ATTR_BOUNDS,
    BOUNDS as BOUNDS,
    DEV_FILES as DEV_FILES,
    DEV_PREFIXES as DEV_PREFIXES,
    REQUIRED_TIMES as REQUIRED_TIMES,
    SKIP_DIRS as SKIP_DIRS,
    SUFFIXES as SUFFIXES,
    Finding as Finding,
    bounded as bounded,
    category as category,
    credential_path as credential_path,
    environment as environment,
    files as files,
    is_true as is_true,
    json_objects as json_objects,
    line_for as line_for,
    relevant as relevant,
    walk as walk,
)
from keycloak_audit_lib.parsing import yaml as yaml


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--environment", choices=("auto", "dev", "prod"), default="auto")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    if not args.root.is_dir() or args.root.is_symlink():
        print("Racine invalide.", file=sys.stderr)
        return 2
    audit = Audit(args.environment).scan(args.root)
    result = {
        "environment_mode": args.environment,
        "rules": "proposition de sécurité, à valider ; absence explicite = écart",
        "counts": dict(Counter(f.severity for f in audit.findings)),
        "inventory": audit.inventory,
        "findings": [asdict(f) for f in audit.findings],
    }
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for f in audit.findings:
            print(f"{f.file}:{f.line} {f.severity} {f.rule} [{f.environment}] {f.message}")
    if audit.errors:
        return 2
    return 1 if any(f.severity not in {"REVIEW"} for f in audit.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
