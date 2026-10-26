#!/usr/bin/env python3
# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
"""Copier sans altération LICENSE/NOTICE dans un contexte ou vérifier une archive locale."""
import argparse
from pathlib import Path
import tarfile
import zipfile


def legal_files(root):
    docs = {}
    for name in ('LICENSE', 'NOTICE'):
        p = root / name
        if p.is_symlink() or not p.is_file(): raise ValueError('document absent ou lien')
        docs[name] = p.read_bytes()
        if not docs[name]: raise ValueError('document vide')
    return docs


def stage(root, destination):
    dest = Path(destination)
    if dest.is_absolute() or '..' in dest.parts: raise ValueError('destination hors dépôt')
    target = root / dest
    if not target.resolve().is_relative_to(root.resolve()): raise ValueError('destination hors dépôt')
    if any(p.is_symlink() for p in [target, *target.parents]): raise ValueError('destination liée')
    docs = legal_files(root)
    for name, content in docs.items():
        p = target / name
        if p.is_symlink() or (p.exists() and p.read_bytes() != content):
            raise ValueError('document existant différent')
    target.mkdir(parents=True, exist_ok=True)
    for name, content in docs.items(): (target / name).write_bytes(content)


def check_archive(root, path):
    docs = legal_files(root)
    found = set()
    prefixes = set()

    def verify(name, size, read):
        # Only top-level package docs, never those of nested dependencies.
        parts = Path(name).parts
        if Path(name).is_absolute() or '..' in parts:
            raise ValueError('chemin archivé invalide')
        if len(parts) not in (1, 2) or parts[-1] not in docs: return
        key = parts[-1]
        if key in found or size != len(docs[key]) or read() != docs[key]:
            raise ValueError('document archivé différent ou dupliqué')
        found.add(key)
        prefixes.add(parts[:-1])

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('lien archivé interdit')
                verify(member.filename, member.file_size, lambda m=member: archive.read(m))
    else:
        with tarfile.open(path, 'r:*') as archive:
            for member in archive:
                if Path(member.name).name in docs and not member.isfile():
                    raise ValueError('document archivé non régulier')
                if member.isfile():
                    verify(member.name, member.size, lambda m=member: archive.extractfile(m).read())
    if found != set(docs) or len(prefixes) != 1: raise ValueError('LICENSE ou NOTICE absent du même paquet')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dest')
    group.add_argument('--archive', type=Path)
    args = parser.parse_args()
    try:
        if args.dest is not None: stage(args.root.resolve(), args.dest)
        else: check_archive(args.root.resolve(), args.archive)
        print('LICENSE et NOTICE vérifiés sans modification.')
        return 0
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile):
        print('Échec: documents légaux absents, différents ou chemin invalide.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
