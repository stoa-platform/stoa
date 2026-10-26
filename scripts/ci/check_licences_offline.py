#!/usr/bin/env python3
# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
"""Contrôle sans réseau, désactivé par défaut. Python >= 3.11, bibliothèque standard."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

SKIP = {'.git', '.claude', '.codex', '.aws', '.ssh', 'node_modules', 'vendor',
        '.venv', 'venv', '__pycache__', 'target'}
MANIFESTS = {'Cargo.toml', 'package.json', 'pyproject.toml', 'go.mod', 'go.sum',
             'Chart.yaml', 'Chart.lock', 'Pipfile', 'setup.py', 'setup.cfg',
             'LICENSE', 'NOTICE', '.goreleaser.yaml'}


def audit_input(path):
    """Périmètre conservateur; inclut les nouvelles sources non encore inventoriées."""
    p = Path(path)
    return (not SKIP.intersection(p.parts) and not p.name.startswith('.env') and
            'credentials' not in p.name.lower() and
            (p.name in MANIFESTS or p.name.startswith(('Dockerfile', 'requirements'))
             or p.name.endswith(('.lock', '-lock.json', '-lock.yaml', '.tgz', '.whl'))
             or (p.suffix in {'.yaml', '.yml'} and
                 (p.parts[0] in {'charts', 'deploy', 'k8s', 'quickstart', 'tests'}
                  or 'k8s' in p.parts or 'compose' in p.name))))


def source_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                  if audit_input(p.relative_to(root)) and p.is_file())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(expression, policy):
    """SPDX AND/OR/WITH: AND prioritaire; aucune ponctuation ignorée."""
    tokens = re.findall(r'\(|\)|[^\s()]+', expression or '')
    pos = 0
    allowed = {x.upper() for x in policy['allowed']}
    exceptions = {x.upper() for x in policy['allowed_exceptions']}
    denied = tuple(x.upper() for x in policy['denied_prefixes'])

    def atom():
        nonlocal pos
        token = tokens[pos]
        pos += 1
        if token == '(':
            value = expr('OR')
            if tokens[pos] != ')':
                raise ValueError('parenthèse')
            pos += 1
            return value
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-+:]*', token) or token.upper() in {'AND', 'OR', 'WITH'}:
            raise ValueError('identifiant')
        if pos < len(tokens) and tokens[pos].upper() == 'WITH':
            pos += 1
            exception = tokens[pos]
            pos += 1
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-+]*', exception):
                raise ValueError('exception')
            return 0 if f'{token} WITH {exception}'.upper() in exceptions else 1
        uid = token.upper()
        return 2 if uid.startswith(denied) else (0 if uid in allowed else 1)

    def expr(operator):
        nonlocal pos
        parse = atom if operator == 'AND' else lambda: expr('AND')
        value = parse()
        while pos < len(tokens) and tokens[pos].upper() == operator:
            pos += 1
            other = parse()
            value = max(value, other) if operator == 'AND' else min(value, other)
        return value

    try:
        value = expr('OR')
        if pos != len(tokens):
            raise ValueError('reste')
        return ['conforme', 'à confirmer', 'incompatible'][value]
    except (ValueError, IndexError, RecursionError):
        return 'à confirmer'


def check(root, inventory, snapshot, policy):
    ledger = json.loads(snapshot.read_text(encoding='utf8'))
    if ledger['schema'] != 1 or sha256(inventory) != ledger['inventory_sha256']:
        raise ValueError('inventaire absent, altéré ou schéma incorrect')
    sources = ledger['sources']
    if not sources or set(source_files(root)) != set(sources):
        raise ValueError('périmètre modifié: régénérer inventaire et empreintes')
    for relative, digest in sources.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError('source modifiée ou chemin hors dépôt')
    with inventory.open(encoding='utf8', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'ecosystem', 'name', 'version', 'license', 'source'} <= set(reader.fieldnames or []):
            raise ValueError('colonnes CSV manquantes')
        rows = list(reader)
    if not rows or any(not row.get('name') or not row.get('source') for row in rows):
        raise ValueError('inventaire vide ou ligne incomplète')
    rejected = 0
    for row in rows:
        verdict = classify(row['license'], policy)
        if verdict != 'conforme':
            rejected += 1
    print(f'{len(rows)} références; {rejected} interdites ou à confirmer')
    return 1 if rejected else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('licences-policy.json'))
    parser.add_argument('--inventory', type=Path, default=Path('audit/licences/inventaire-licences.csv'))
    parser.add_argument('--snapshot', type=Path, default=Path('audit/licences/sources.json'))
    parser.add_argument('--enforce', action='store_true', help='activer explicitement ce brouillon')
    args = parser.parse_args()
    try:
        policy = json.loads(args.config.read_text(encoding='utf8'))
        if type(policy['enabled']) is not bool or any(
            not isinstance(policy[k], list) or not all(isinstance(x, str) and x for x in policy[k])
            for k in ('allowed', 'denied_prefixes', 'allowed_exceptions')):
            raise ValueError('configuration incorrecte')
        if not args.enforce and not policy['enabled']:
            print('Contrôle licences désactivé (brouillon).')
            return 0
        return check(args.root, args.inventory, args.snapshot, policy)
    except (OSError, ValueError, KeyError, TypeError, csv.Error):
        print('Entrées invalides ou périmées: contrôle fermé, régénération requise.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
