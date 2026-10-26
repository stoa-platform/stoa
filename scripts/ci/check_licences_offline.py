#!/usr/bin/env python3
# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
"""Contrôle local des licences: avertissement par défaut, blocage en deux temps (deny puis enforce). Python >= 3.11."""
import argparse
import csv
from collections import Counter
from datetime import date
import hashlib
import os
import json
from pathlib import Path
import re
import sys
import tarfile

MODES = ('warn', 'deny', 'enforce')
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
    return rows, sources


def validate_policy(policy):
    if 'enabled' in policy and type(policy['enabled']) is not bool:
        raise ValueError('enabled incorrect')
    if policy.get('mode', 'warn') not in MODES:
        raise ValueError('mode incorrect')
    for key in ('allowed', 'denied_prefixes', 'phase1_denied_prefixes', 'allowed_exceptions'):
        if not isinstance(policy[key], list) or not all(isinstance(x, str) and x for x in policy[key]):
            raise ValueError('configuration incorrecte')
    if policy['allowed_exceptions']:
        raise ValueError('exceptions SPDX globales interdites: utiliser une dérogation ciblée et justifiée')
    entries = policy.get('exceptions', [])
    if not isinstance(entries, list):
        raise ValueError('liste de dérogations incorrecte')
    keys = ('ecosystem', 'name', 'version', 'source', 'license')
    seen = set()
    for entry in entries:
        required = (*keys, 'source_sha256', 'reason', 'approved_by', 'decision', 'expires')
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in required):
            raise ValueError('dérogation incomplète')
        identity = (*tuple(entry[k] for k in keys), entry.get('locator'))
        if 'locator' in entry and (not isinstance(entry['locator'], str) or not entry['locator']):
            raise ValueError('locator incorrect')
        if identity in seen or any('*' in entry[k] for k in keys) or entry['name'].startswith('['):
            raise ValueError('dérogation globale, dupliquée ou visant un graphe incomplet')
        seen.add(identity)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', entry['expires']) or date.fromisoformat(entry['expires']) < date.today():
            raise ValueError('dérogation expirée')
        if not re.fullmatch(r'[0-9a-f]{64}', entry['source_sha256']):
            raise ValueError('empreinte de dérogation incorrecte')


def evaluate(rows, sources, policy):
    keys = ('ecosystem', 'name', 'version', 'source', 'license')
    phase1 = dict(policy, denied_prefixes=policy['phase1_denied_prefixes'])
    for row in rows:
        row['original_status'] = classify(row['license'], policy)
        row['status'] = row['original_status']
        # Premier temps du blocage: seules les licences de la liste phase 1.
        row['phase1_denied'] = classify(row['license'], phase1) == 'incompatible'
    for entry in policy.get('exceptions', []):
        identity = tuple(entry[k] for k in keys)
        matches = [r for r in rows if tuple(r[k] for k in keys) == identity]
        if 'locator' in entry:
            matches = [r for r in matches if r.get('locator', '') == entry['locator']]
        elif len({r.get('locator', '') for r in matches}) > 1:
            raise ValueError('dérogation ambiguë: locator obligatoire')
        if not matches:
            raise ValueError('dérogation sans référence correspondante')
        # Legacy CSV sources can carry an archive member and/or line number.
        relative = entry['source'].split('!', 1)[0].split(':', 1)[0]
        if entry['source_sha256'] != sources.get(relative):
            raise ValueError('dérogation périmée')
        for row in matches:
            if row['status'] in {'conforme', 'dérogation'}:
                raise ValueError('dérogation superflue ou chevauchante')
            row['status'] = 'dérogation'
            row['exception'] = {k: entry[k] for k in ('reason', 'approved_by', 'decision', 'expires')}
    return dict(Counter(row['status'] for row in rows))


def summary(line):
    target = os.environ.get('GITHUB_STEP_SUMMARY')
    if target:
        try:
            with open(target, 'a', encoding='utf8') as stream:
                stream.write(line + '\n')
        except OSError:
            pass


def requested_mode(args):
    """Mode demandé, lisible même si la politique est invalide (repli: warn)."""
    if args.enforce:
        return 'enforce'
    if args.mode:
        return args.mode
    try:
        policy = json.loads(args.config.read_text(encoding='utf8'))
        if 'enabled' in policy:
            if type(policy['enabled']) is not bool:
                return 'enforce'
            return 'enforce' if policy['enabled'] else 'warn'
        mode = policy.get('mode', 'warn')
        return mode if mode in MODES else 'enforce'
    except Exception:
        return 'enforce'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('licences-policy.json'))
    parser.add_argument('--inventory', type=Path, help='CSV historique; exige --snapshot')
    parser.add_argument('--snapshot', type=Path, help='snapshot associé au CSV historique')
    parser.add_argument('--mode', choices=list(MODES))
    parser.add_argument('--enforce', action='store_true', help='équivalent de --mode enforce')
    parser.add_argument('--report', type=Path, help='rapport JSON incluant toutes les références et preuves')
    args = parser.parse_args()
    try:
        policy = json.loads(args.config.read_text(encoding='utf8'))
        validate_policy(policy)
        mode = 'enforce' if args.enforce else (args.mode or ('enforce' if policy.get('enabled') else policy.get('mode', 'warn')))
        if bool(args.inventory) != bool(args.snapshot):
            raise ValueError('CSV et snapshot obligatoires ensemble')
        if args.inventory:
            rows, sources = check(args.root, args.inventory, args.snapshot, policy)
        else:
            from collect_licences_local import collect
            rows, sources = collect(args.root)
        if not rows:
            raise ValueError('aucune référence collectée')
        counts = evaluate(rows, sources, policy)
        findings = counts.get('à confirmer', 0) + counts.get('incompatible', 0)
        phase1 = sum(1 for row in rows if row['phase1_denied'] and row['status'] != 'dérogation')
        report = dict(schema=2, mode=mode, counts=counts, phase1_denied=phase1, rows=rows, sources=sources,
                      policy_sha256=sha256(args.config),
                      result='findings' if findings else ('accepted-with-exceptions' if counts.get('dérogation') else 'pass'))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print(f"Mode {mode}: {len(rows)} références; {findings} interdites par politique ou À CONFIRMER; "
              f"{counts.get('dérogation', 0)} dérogation(s).")
        if findings:
            print('AVERTISSEMENT: confirmations requises; voir le rapport détaillé.')
            print(f'::warning title=Licences::{findings} référence(s) à confirmer ou interdite(s), '
                  f'dont {phase1} interdite(s) dès le premier temps; voir license-report.json.')
        summary(f"Licences (mode {mode}): {len(rows)} références, {findings} à confirmer ou interdites, "
                f"{phase1} interdites (premier temps), {counts.get('dérogation', 0)} dérogation(s).")
        if mode == 'enforce' and findings:
            return 1
        if mode == 'deny' and phase1:
            return 1
        return 0
    except (OSError, ValueError, KeyError, TypeError, csv.Error, IndexError, AttributeError, tarfile.TarError, UnicodeError):
        # Never echo untrusted input, URLs, manifest contents or exception text.
        if args.report:
            try:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(dict(schema=2, result='invalid-input')) + '\n')
            except OSError:
                pass
        print('Entrées invalides ou périmées: contrôle fermé, régénération requise.', file=sys.stderr)
        if requested_mode(args) == 'warn':
            # Mode avertissement: ne jamais faire échouer la CI, mais rester visible.
            print('::warning title=Licences::entrées invalides ou périmées, contrôle non concluant.')
            summary('Licences (mode warn): contrôle non concluant, entrées invalides ou périmées.')
            return 0
        return 2


if __name__ == '__main__':
    sys.exit(main())
