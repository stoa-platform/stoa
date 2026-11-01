#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CAB-2343: changed source/config/docs files must have no image-pinning debt.

Only changed allowlisted files are scanned; untouched debt remains for migration.
Consumers need literal digests; split Helm image.digest is trusted lexically.
Metadata semver/match require latest=false; raw latest aliases fail.
This does not render templates, query registries, or change branch protection.
"""
import argparse
import re
import shlex
import subprocess
from pathlib import PurePosixPath

DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
KEY = re.compile(r"^(\s*)(?:-\s*)?([\w-]+):\s*(.*?)\s*$")
GUARD = "scripts/ci/check_image_pinning.py"


def allowed(path):
    p = PurePosixPath(path)
    return (not set(p.parts) & {"private", "prive"} and p.name != "ACCES.md" and
            (p.suffix in {".yml", ".yaml", ".json", ".toml", ".sh", ".go", ".py", ".md", ".mdx", ".tpl", ".j2"}
             or p.name.lower().startswith("dockerfile")))


def clean(value):
    return value.split(" #", 1)[0].strip().strip("\"'`").rstrip("\\").strip()


def findings(path, source):
    lines, found, stages, stack = source.splitlines(), [], set(), []

    def add(index, kind):
        found.append((index + 1, kind))

    def image(index, value):
        value = clean(value)
        if value and not DIGEST.fullmatch(value):
            add(index, "image-interpolation" if "$" in value or "{{" in value else "image-unpinned")

    def block(index, indent, equal=True):
        result = []
        for offset in range(index + 1, len(lines)):
            text = lines[offset]
            width = len(text) - len(text.lstrip())
            if text.strip() and not text.lstrip().startswith("#"):
                if width < indent or (width == indent and (equal or text.lstrip().startswith("- "))):
                    break
            result.append((offset, text))
        return result

    def helm_fields(index, indent):
        return [(m[2], clean(m[3])) for _, text in block(index, indent) if (m := KEY.match(text))]

    for index, line in enumerate(lines):
        match = KEY.match(line)
        if match:
            indent, key, value = match.groups()
            while stack and stack[-1][0] >= len(indent):
                stack.pop()
            if key in {"imagePullPolicy", "pullPolicy"} and clean(value) == "Always":
                add(index, "pull-policy-always")
            if key in {"image", "container"} and value:
                image(index, value)
            if key == "image" and not value:
                fields = dict(helm_fields(index, len(indent)))
                if fields.get("repository") and "tag" not in fields and not re.fullmatch(r"sha256:[0-9a-f]{64}", fields.get("digest", "")):
                    add(index, "helm-unpinned")
            if key == "tag" and any(entry[1] == "image" for entry in stack):
                parent = next(entry for entry in reversed(stack) if entry[1] == "image")
                fields = dict(helm_fields(parent[2], parent[0]))
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", fields.get("digest", "")):
                    add(index, "helm-tag-unpinned")
            if not value:
                stack.append((len(indent), key, index))
        for key, value in re.findall(r'''(?:^|[{,])\s*("[\w-]+"|'[\w-]+'|[\w-]+)\s*:\s*("[^"]*"|'[^']*'|[^,}\s]+)''', line):
            key = clean(key)
            if key in {"image", "container"}:
                image(index, value)
            elif key in {"imagePullPolicy", "pullPolicy"} and clean(value) == "Always":
                add(index, "pull-policy-always")
        flags = re.I if "dockerfile" in PurePosixPath(path).name.lower() else 0
        match = re.match(r"\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\w+))?", line, flags)
        if match:
            if match[1] != "scratch" and match[1].lower() not in stages:
                image(index, match[1])
            if match[2]:
                stages.add(match[2].lower())
        for value in re.findall(r"--image(?:=|\s+)([^\s]+)", line):
            image(index, value)
        match = re.search(r"\b(?:docker|podman)\s+(?:container\s+)?(?:run|create)\s+(.+)", line)
        if match:
            try:
                tokens = iter(shlex.split(match[1]))
                for token in tokens:
                    if token in {"-e", "-p", "-v", "-w", "-u", "--name", "--network", "--platform", "--entrypoint", "--env-file", "--mount", "--restart"}:
                        next(tokens, None)
                    elif not token.startswith("-"):
                        image(index, token)
                        break
            except ValueError:
                add(index, "image-unresolved")
        if path.endswith((".md", ".mdx")):
            for value in re.findall(r"`([^`\s]+)`", line):
                if "://" not in value and re.fullmatch(r"[\w./:@${}-]+", value):
                    registry = re.match(r"[\w.-]+\.[\w.-]+/", value)
                    if registry or re.match(r"[a-z0-9_.-]+(?:/[a-z0-9_.-]+)*:(?:latest|[\w.-]+-latest|\d[\w.-]*|alpine)$", value):
                        image(index, value)
        publication = line + " " + re.sub(r"\$\{\{[^}\n]*\}\}|\$\{[^}\n]*\}", "IMAGE_VAR", line)
        if re.search(r"(?:[\w.-]+(?:/[\w${}./-]+)+|IMAGE_VAR):(?:latest|[\w${}.-]+-latest)(?![\w.@-])", publication):
            add(index, "publication-floating")
        if re.match(r'''\s*(?:-\s*)?uses:\s*['"]?docker/metadata-action@''', line):
            action = block(index, len(line) - len(line.lstrip()), equal=False)
            inputs = next((block(off, len(m[1])) for off, text in action
                           if (m := KEY.match(text)) and m[2] == "with"), [])
            flavor, tags = [], []
            for off, text in inputs:
                entry = KEY.match(text)
                if entry and entry[2] in {"flavor", "tags"}:
                    values = [(off, clean(entry[3])), *block(off, len(entry[1]))]
                    if entry[2] == "flavor":
                        flavor = [clean(s) for _, s in values]
                    else:
                        tags = values
            latest_disabled = [v for v in flavor if v.startswith("latest=")][-1:] == ["latest=false"]
            for offset, text in tags:
                attrs = dict(part.strip().split("=", 1) for part in text.strip().split(",") if "=" in part)
                if attrs.get("type") in {"semver", "match"} and not latest_disabled:
                    add(offset, "metadata-implicit-latest")
                if attrs.get("type") == "raw" and re.search(r"(?:^|-)latest$", clean(attrs.get("value", ""))):
                    add(offset, "metadata-explicit-latest")
    return sorted(set(found))


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (args.base, args.head)):
            raise ValueError
        for sha in (args.base, args.head):
            git("cat-file", "-e", f"{sha}^{{commit}}")
        paths = git("diff", "--name-only", "-z", "--diff-filter=ACMRT", args.base, args.head).decode().split("\0")
        errors = []
        for path in filter(None, paths):
            if not allowed(path):
                continue
            if re.search(r"[\x00-\x1f:]", path):
                raise ValueError
            source = git("show", f"{args.head}:{path}")
            if b"\0" not in source:
                errors.extend(f"{path}:{line}:{kind}" for line, kind in findings(path, source.decode("utf-8")))
        print("\n".join(sorted(set(errors))), end="\n" if errors else "")
        return bool(errors)
    except (subprocess.CalledProcessError, UnicodeError, ValueError, OSError):
        print(f"{GUARD}:1:scan-failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
