#!/usr/bin/env python3
# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
"""Inventaire déclaratif local. Aucun réseau ni exécution de gestionnaire de paquets."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import tarfile
import tomllib
from email.parser import Parser

MARK = '[[À CONFIRMER]]'
SKIP = {'.git', '.claude', '.codex', '.aws', '.ssh', '.venv', 'venv',
        '__pycache__', 'target', 'node_modules', 'vendor', 'dist', 'build'}
NAMES = {'package.json', 'Cargo.toml', 'Cargo.lock', 'go.mod', 'go.sum',
         'pyproject.toml', 'Pipfile', 'setup.py', 'setup.cfg', 'Chart.yaml',
         'Chart.lock', 'LICENSE', 'NOTICE', '.goreleaser.yaml'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or any(x in SKIP - {'vendor', 'node_modules'} for x in p.parts):
        raise ValueError('chemin de preuve interdit')
    if p.name.startswith('.env') or 'credentials' in p.name.lower() or p.suffix in {'.pem', '.key', '.tfvars'}:
        raise ValueError('chemin de preuve interdit')
    path = root / p
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
        raise ValueError('lien symbolique interdit')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('preuve hors dépôt')
    return path


def source_files(root):
    """Élaguer les répertoires exclus avant parcours; ne pas suivre les liens."""
    found = []
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            p = Path(folder) / name
            if name.startswith('.env') or 'credentials' in name.lower():
                continue
            if (name in NAMES or name.startswith(('Dockerfile', 'requirements'))
                    or name.endswith(('.lock', '-lock.json', '-lock.yaml', '.tgz', '.whl', '.yaml', '.yml'))):
                relative = p.relative_to(root).as_posix()
                safe_path(root, relative)  # Selected symlinks fail closed, never read their target.
                found.append(relative)
    return sorted(found)


def redact(value):
    value = str(value)
    value = re.sub(r'(?<=//)[^/\s@]+@', '[IDENTIFIANTS MASQUÉS]@', value)
    value = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[ADRESSE MASQUÉE]', value)
    value = re.sub(r'\b[\w.-]+\.(?:internal|local|svc|cluster)(?::\d+)?', '[HÔTE MASQUÉ]', value)
    return value


def collect(root):
    root = root.resolve()
    files = source_files(root)
    rows = []
    sources = {f: digest(root / f) for f in files}

    def add(eco, name, version, source, license='', evidence='', notes='', locator=''):
        rows.append(dict(ecosystem=eco, name=redact(name), version=redact(version or MARK),
                         source=source, license=redact(license) if isinstance(license, str) and license else MARK,
                         license_evidence=evidence, notes=notes, locator=redact(locator)))

    def gap(eco, f, reason):
        add(eco, '[graphe incomplet]', '', f, notes=reason)

    def requirement(req, f):
        m = re.match(r'^([A-Za-z0-9][\w.-]*)(?:\[[^]]+\])?(.*)', req.strip())
        if not m:
            add('pypi', '[exigence non interprétée]', '', f, notes='syntaxe/options/include non résolus')
            return
        pinned = re.fullmatch(r'\s*==\s*([^,;\s*]+)\s*(?:;.*)?', m[2])
        add('pypi', re.sub(r'[-_.]+', '-', m[1]).lower(), pinned[1] if pinned else '', f,
            notes='contrainte/extras/marqueurs non résolus; ' + redact(req))

    def inspect_images(content, source, prefix=''):
        found = False
        for i, line in enumerate(content.splitlines(), 1):
            m = re.match(r'^\s*(?:-\s*)?(image|repository):\s*(.+?)\s*$', line)
            if not m: continue
            value = m[2].split(' #', 1)[0].strip("\"'")
            if value.startswith('#') or (m[1] == 'repository' and re.match(r'(?:https?|file|oci)://', value)):
                continue
            found = True
            add('oci', value, value if m[1] == 'image' else '', source, locator=prefix + str(i),
                notes='référence YAML lexicale; repository/tag/templates à confirmer')
        return found

    def inspect_chart_dependencies(content, source):
        block = re.search(r'^dependencies:\s*\n((?:[ \t]+[^\n]*\n?|-\s+[^\n]*\n?|\n)*)', content, re.M)
        if not block: return
        for item in re.split(r'(?m)^\s*-\s+name:\s*', block[1])[1:]:
            name = item.splitlines()[0].strip(" \"'")
            version = re.search(r'^\s+version:\s*(.+)', item, re.M)
            add('helm', name, version[1].strip(" \"'") if version else '', source,
                notes='dépendance chart déclarée; contrainte/condition non résolues')

    for f in files:
        p = root / f
        name = p.name
        if name in {'LICENSE', 'NOTICE'}:
            continue
        if name == 'package-lock.json':
            data = json.loads(p.read_text())
            if data.get('lockfileVersion') not in (2, 3) or not data.get('packages'):
                gap('npm', f, 'format de lock non pris en charge'); continue
            for loc, meta in data['packages'].items():
                if not loc: continue
                add('npm', meta.get('name') or loc.rsplit('node_modules/', 1)[-1], meta.get('version'), f,
                    meta.get('license', ''), f + ' champ license' if meta.get('license') else '',
                    'déclaration du lock; lien à résoudre' if meta.get('link') else 'déclaration du lock', loc)
                rows[-1]['integrity'] = meta.get('integrity', '')
            manifest = p.with_name('package.json')
            if manifest.exists():
                safe_path(root, manifest.relative_to(root).as_posix())
                direct = json.loads(manifest.read_text())
                for section in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'):
                    if direct.get(section, {}) != data['packages'].get('', {}).get(section, {}):
                        gap('npm', f, 'manifeste et racine du lock divergents: ' + section)
                    for dep in direct.get(section, {}):
                        if 'node_modules/' + dep not in data['packages']:
                            add('npm', dep, '', f, notes='déclaration absente du lock')
        elif name == 'package.json':
            data = json.loads(p.read_text())
            if not p.with_name('package-lock.json').exists():
                for section in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'):
                    for dep in data.get(section, {}): add('npm', dep, '', f, notes='absence de lock')
                gap('npm', f, 'graphe sans lock npm')
        elif name == 'Cargo.lock':
            for package in tomllib.loads(p.read_text()).get('package', []):
                add('cargo', package['name'], package['version'], f,
                    notes='licence absente de Cargo.lock; paquets locaux inclus', locator=package.get('source', 'local'))
        elif name == 'Cargo.toml':
            data = tomllib.loads(p.read_text())
            package = data.get('package', {})
            if package:
                add('cargo-project', package.get('name', '[nom hérité]'), package.get('version', '')
                    if isinstance(package.get('version', ''), str) else '', f, package.get('license', ''),
                    f + ' package.license', 'licence du projet seulement')
            sections = [(k, data.get(k, {})) for k in ('dependencies', 'dev-dependencies', 'build-dependencies')]
            for target in data.get('target', {}).values():
                sections.extend((k, target.get(k, {})) for k in ('dependencies', 'dev-dependencies', 'build-dependencies'))
            sections.append(('workspace', data.get('workspace', {}).get('dependencies', {})))
            for section, deps in sections:
                for dep, value in deps.items():
                    add('cargo-declaration', value.get('package', dep) if isinstance(value, dict) else dep,
                        '', f, notes='déclaration ' + section + '; résolution/features à confirmer')
            # Without Cargo metadata we cannot prove workspace/target/patch resolution.
            gap('cargo', f, 'résolution manifeste/lock/workspace/features non exécutée')
        elif name == 'go.mod':
            block = ''
            for line in p.read_text().splitlines():
                line = line.split('//', 1)[0].strip()
                if line == ')': block = ''; continue
                m = re.match(r'^(require|replace|exclude|tool)\s*\($', line)
                if m: block = m[1]; continue
                if line.startswith(('replace ', 'exclude ')) or block in {'replace', 'exclude'}:
                    if line: gap('go', f, 'replace/exclude: résolution effective à confirmer')
                m = re.match(r'^(?:require\s+)?([^\s]+)\s+(v\S+)', line)
                if m and (block == 'require' or line.startswith('require ')):
                    add('go', m[1], m[2], f, notes='module déclaré, licence non fournie par go.mod')
            gap('go', f, 'graphe sélectionné, replacements et dépendances système non prouvés')
        elif name == 'go.sum':
            seen = set()
            for line in p.read_text().splitlines():
                parts = line.split()
                if len(parts) != 3: raise ValueError('go.sum incorrect')
                key = (parts[0], parts[1].removesuffix('/go.mod'))
                if key not in seen:
                    add('go-sum', *key, f, notes='somme disponible, ne prouve pas un module embarqué'); seen.add(key)
        elif name == 'pyproject.toml':
            data = tomllib.loads(p.read_text())
            project = data.get('project', {})
            deps = list(project.get('dependencies', [])) + list(data.get('build-system', {}).get('requires', []))
            for group in project.get('optional-dependencies', {}).values(): deps.extend(group)
            for group in data.get('dependency-groups', {}).values():
                deps.extend(x for x in group if isinstance(x, str))
                if any(not isinstance(x, str) for x in group): gap('pypi', f, 'groupes inclus non résolus')
            poetry = data.get('tool', {}).get('poetry', {})
            groups = [poetry.get('dependencies', {}), poetry.get('dev-dependencies', {})]
            groups.extend(g.get('dependencies', {}) for g in poetry.get('group', {}).values())
            for group in groups:
                for dep in group:
                    if dep != 'python': add('pypi', dep, '', f, notes='contrainte Poetry non résolue')
            for req in deps: requirement(req, f)
            gap('pypi', f, 'transitifs, versions et dépendances dynamiques non résolus')
        elif name.startswith('requirements'):
            for line in p.read_text().splitlines():
                req = line.split(' #', 1)[0].strip()
                if req and not req.startswith('#'): requirement(req, f)
            gap('pypi', f, 'graphe transitif/include/hashes non reconstruit')
        elif name.startswith('Dockerfile'):
            stages = set()
            logical = []
            pending = ''
            start = 1
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if not pending: start = i
                pending += line.strip().removesuffix('\\') + ' '
                if line.rstrip().endswith('\\'): continue
                logical.append((start, pending.strip())); pending = ''
            if pending: gap('oci', f, 'instruction Dockerfile incomplète')
            for i, line in logical:
                if re.match(r'^FROM\s', line, re.I):
                    parts = shlex.split(line, comments=True)[1:]
                    parts = [x for x in parts if not x.startswith('--')]
                    image = parts[0]
                    if image.lower() not in stages and image != 'scratch':
                        add('oci', image, image, f, notes='image de base; tag/digest sans preuve de licence', locator=str(i))
                    if len(parts) >= 3 and parts[1].lower() == 'as': stages.add(parts[2].lower())
                if not re.match(r'^RUN\s', line, re.I): continue
                for command in re.finditer(r'(?:apt-get\s+install|apk\s+add)\s+([^;&|]+)', line):
                    for token in shlex.split(command[1]):
                        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+:-]*(?:=[A-Za-z0-9_.+~:-]+)?', token): continue
                        dep, _, version = token.partition('=')
                        add('os-package', dep, version, f, locator=str(i),
                            notes='installation explicite; transitifs/version effective/licence à confirmer')
                for command in re.finditer(r'pip(?:3)?\s+install\s+([^;&|]+)', line):
                    skip_next = False
                    for token in shlex.split(command[1]):
                        if skip_next: skip_next = False; continue
                        if token in {'-r', '--requirement', '-c', '--constraint', '--index-url', '--extra-index-url', '--target', '--prefix'}:
                            skip_next = True; continue
                        if token.startswith('-') or token in {'.', './'}: continue
                        requirement(token, f)
                        rows[-1]['locator'] = str(i)
                for command in re.finditer(r'cargo\s+install\s+([^;&|]+)', line):
                    skip_next = False
                    for token in shlex.split(command[1]):
                        if skip_next: skip_next = False; continue
                        if token in {'--version', '--root', '--path', '--git', '--rev', '--branch', '--tag', '--features', '--target'}:
                            skip_next = True; continue
                        if token.startswith('-') or not re.fullmatch(r'[\w-]+', token): continue
                        add('cargo-tool', token, '', f, locator=str(i),
                            notes='outil de build; version, graphe et licence non résolus')
            gap('oci', f, 'couches, outils de build et paquets système non inventoriés exhaustivement')
        elif name.endswith(('.yaml', '.yml')) or name == 'Chart.lock':
            content = p.read_text()
            if inspect_images(content, f): gap('oci', f, 'YAML non rendu; images et tags effectifs non résolus')
            if name in {'Chart.yaml', 'Chart.lock'}:
                inspect_chart_dependencies(content, f)
                gap('helm', f, 'dépendances chart et licences à confirmer')
        elif name.endswith('.tgz'):
            with tarfile.open(p, 'r:gz') as archive:
                members = archive.getmembers()
                texts = [m for m in members if m.isfile() and Path(m.name).name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE'))]
                for member in members:
                    if not member.isfile(): continue
                    if member.name.endswith('/Chart.yaml'):
                        if member.size > 1024 * 1024: raise ValueError('Chart.yaml trop volumineux')
                        content = archive.extractfile(member).read().decode('utf8')
                        chart_name = re.search(r'^name:\s*[\"\']?([^\s\"\']+)', content, re.M)
                        version = re.search(r'^version:\s*[\"\']?([^\s\"\']+)', content, re.M)
                        local_texts = [t for t in texts if Path(t.name).parent == Path(member.name).parent]
                        expressions = set()
                        incomplete_text = False
                        for text in local_texts:
                            if text.size > 2 * 1024 * 1024: raise ValueError('licence trop volumineuse')
                            if Path(text.name).name.upper().startswith('NOTICE'): continue
                            body = archive.extractfile(text).read().decode('utf8')
                            identifiers = re.findall(r'SPDX-License-Identifier:\s*([^\r\n]+)', body)
                            if not identifiers: incomplete_text = True
                            expressions.update(identifiers)
                        license = next(iter(expressions)).strip() if len(expressions) == 1 and not incomplete_text else ''
                        add('helm', chart_name[1] if chart_name else '[chart]', version[1] if version else '', f,
                            license=license, evidence='; '.join(f + '!' + t.name for t in local_texts),
                            notes='textes locaux lus, identifiant SPDX requis' if local_texts else 'aucun texte de licence local',
                            locator=member.name)
                    if member.name.endswith(('.yaml', '.yml')):
                        if member.size > 2 * 1024 * 1024: raise ValueError('YAML archivé trop volumineux')
                        content = archive.extractfile(member).read().decode('utf8')
                        inspect_images(content, f, prefix=member.name + ':')
            gap('helm', f, 'archives de charts; images imbriquées non rendues')
        elif name in {'Pipfile', 'setup.py', 'setup.cfg'} or name.endswith(('.lock', '.whl')):
            gap('unresolved', f, 'format non interprété; compléter les preuves locales')

    # A local workspace crate is distinct from a registry crate of the same name.
    projects = {}
    for row in rows:
        if row['ecosystem'] == 'cargo-project' and row['license'] != MARK:
            projects.setdefault((row['name'], row['version']), []).append(row)
    for row in rows:
        matches = projects.get((row['name'], row['version']), [])
        if row['ecosystem'] == 'cargo' and row['locator'] == 'local' and len(matches) == 1:
            row['license'] = matches[0]['license']
            row['license_evidence'] = matches[0]['source'] + ' package.license (crate locale exacte)'

    # Same npm artifact only; no inference by name or version alone.
    declarations = {}
    for row in rows:
        if row['ecosystem'] == 'npm' and row.get('integrity') and row['license'] != MARK:
            key = (row['name'], row['version'], row['integrity'])
            declarations.setdefault(key, set()).add(row['license'])
    for row in rows:
        key = (row['name'], row['version'], row.get('integrity'))
        if row['ecosystem'] == 'npm' and row['license'] == MARK and len(declarations.get(key, set())) == 1:
            row['license'] = next(iter(declarations[key])); row['license_evidence'] = 'lock: même nom/version/integrity'

    # Reviewed exact bindings to local metadata/texts; never read host caches.
    ledger_name = 'audit/licences/local-evidence.json'
    ledger = root / ledger_name
    if ledger.exists() or ledger.is_symlink():
        safe_path(root, ledger_name)
        data = json.loads(ledger.read_text())
        if data.get('schema') != 1 or not isinstance(data.get('entries'), list): raise ValueError('preuves invalides')
        sources[ledger_name] = digest(ledger)
        bound = set()
        applied = set()
        for entry in data['entries']:
            identity = tuple(entry[k] for k in ('ecosystem', 'name', 'version', 'source'))
            binding = (*identity, entry.get('locator'))
            if binding in bound: raise ValueError('preuve dupliquée')
            bound.add(binding)
            if not entry.get('reason') or entry['source_sha256'] != sources.get(entry['source']):
                raise ValueError('preuve périmée ou non justifiée')
            path = safe_path(root, entry['path'])
            if digest(path) != entry['sha256']: raise ValueError('texte de licence modifié')
            sources[entry['path']] = digest(path)
            content = path.read_text(encoding='utf8')
            kind = entry['kind']
            if kind == 'cargo':
                if identity[0] != 'cargo': raise ValueError('écosystème de preuve différent')
                package = tomllib.loads(content)['package']
                if (package['name'], package['version']) != identity[1:3]: raise ValueError('identité crate différente')
                license = package.get('license', '')
            elif kind == 'python':
                if identity[0] != 'pypi': raise ValueError('écosystème de preuve différent')
                meta = Parser().parsestr(content)
                normalized = re.sub(r'[-_.]+', '-', meta['Name'] or '').lower()
                if (normalized, meta['Version']) != identity[1:3]: raise ValueError('identité Python différente')
                license = meta.get('License-Expression') or meta.get('License') or ''
            elif kind == 'spdx-text':
                if identity[0] == 'oci' and not re.search(r'@sha256:[0-9a-f]{64}$', identity[1]):
                    raise ValueError('preuve image sans digest immuable')
                matches = re.findall(r'SPDX-License-Identifier:\s*([^\r\n]+)', content)
                license = matches[0].strip() if len(set(matches)) == 1 else ''
            else: raise ValueError('format de preuve inconnu')
            matches = [r for r in rows if tuple(r[k] for k in ('ecosystem', 'name', 'version', 'source')) == identity]
            if 'locator' in entry:
                matches = [r for r in matches if r.get('locator', '') == entry['locator']]
            elif len({r.get('locator', '') for r in matches}) > 1:
                raise ValueError('preuve ambiguë: locator obligatoire')
            if not matches: raise ValueError('preuve sans référence correspondante')
            for row in matches:
                key = (*identity, row.get('locator', ''))
                if key in applied: raise ValueError('preuves chevauchantes')
                applied.add(key)
                previous = row['license']
                row['license'] = redact(license) if isinstance(license, str) and license else MARK
                if previous != MARK and row['license'] != previous:
                    row['declared_license'] = previous
                    row['local_license'] = row['license']
                    row['license'] = MARK
                    row['notes'] += '; déclarations de licence divergentes'
                row['license_evidence'] = entry['path']
    return rows, sources
