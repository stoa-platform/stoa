#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CAB-2343: changed source/config/docs files must have no image-pinning debt.

Only changed allowlisted files are scanned; untouched debt remains for migration.
docs/platform-catalog.yaml is exempt: inventory only, not a deployment input (CAB-2359).
Consumers need literal digests; split Helm image.digest is trusted lexically.
SBOM actions may consume a pinned, earlier same-job build action's digest.
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


def dockerfile_path(path):
    name = PurePosixPath(path).name.lower()
    return (name.startswith("dockerfile") or name.endswith(".dockerfile") or
            re.search(r"\.dockerfile\.(?:j2|tpl|template)$", name) is not None)


def markdown_image(value):
    registry = re.match(r"(?:localhost|registry|[\w-]+(?:\.[\w-]+)+)(?::\d+)?/", value)
    citation = re.fullmatch(r"(?:.+\.[\w-]+|(?:.*/)?Dockerfile):\d+(?:[-:]\d+)?", value, re.I)
    if citation and not registry:
        return False
    return bool(registry or re.match(r"[a-z0-9_.-]+(?:/[a-z0-9_.-]+)*:(?:latest|[\w.-]+-latest|\d[\w.-]*|alpine)$", value))


def allowed(path):
    p = PurePosixPath(path)
    return (not set(p.parts) & {"private", "prive"} and p.name != "ACCES.md" and
            (p.suffix in {".yml", ".yaml", ".json", ".toml", ".sh", ".go", ".py", ".md", ".mdx", ".tpl", ".j2"}
             or dockerfile_path(path)))


def clean(value):
    return value.split(" #", 1)[0].strip().strip("\"'`").rstrip("\\").strip()


def built_sbom_images(path, lines):
    """Trust only direct SBOM inputs from immutable same-job build outputs.

    Recognize the conventional workflow block layout only; unsupported YAML
    layouts retain the normal literal-digest requirement (fail closed).
    """
    if PurePosixPath(path).parent.as_posix() != ".github/workflows" or not path.endswith((".yml", ".yaml")):
        return set()
    trusted = set()

    def end(start, indent):
        return next((i for i in range(start + 1, len(lines))
                     if lines[i].strip() and not lines[i].lstrip().startswith("#")
                     and len(lines[i]) - len(lines[i].lstrip()) <= indent), len(lines))

    def fields(start, stop, indent, sequence=False):
        result = {}
        for i in range(start, stop):
            match = KEY.match(lines[i])
            if match and (len(match[1]) == indent or (sequence and i == start)):
                if match[2] in result:
                    return {}
                result[match[2]] = (i, clean(match[3]))
        return result

    for root, line in enumerate(lines):
        if line.strip() != "jobs:" or line != line.lstrip():
            continue
        root_end = end(root, 0)
        for job in range(root + 1, root_end):
            if not re.fullmatch(r"  [\w-]+:\s*(?:#.*)?", lines[job]):
                continue
            job_end = min(end(job, 2), root_end)
            for step_list in range(job + 1, job_end):
                if lines[step_list].rstrip() != "    steps:":
                    continue
                stop = min(end(step_list, 4), job_end)
                starts = [i for i in range(step_list + 1, stop) if re.match(r"      - [\w-]+:", lines[i])]
                steps = []
                for start, finish in zip(starts, starts[1:] + [stop]):
                    attrs = fields(start, finish, 8, sequence=True)
                    with_index, with_value = attrs.get("with", (-1, ""))
                    inputs = fields(with_index + 1, min(end(with_index, 8), finish), 10) if with_index >= 0 and not with_value else {}
                    steps.append((attrs, inputs))
                ids = [attrs["id"][1] for attrs, _ in steps if "id" in attrs]
                producers = set()
                for attrs, inputs in steps:
                    action = attrs.get("uses", (-1, ""))[1]
                    image_index, value = inputs.get("image", (-1, ""))
                    digest = re.fullmatch(r"[^@]+@\$\{\{\s*steps\.([A-Za-z_][\w-]*)\.outputs\.digest\s*\}\}", value)
                    if ("run" not in attrs and re.fullmatch(r"anchore/sbom-action@[0-9a-f]{40}", action)
                            and digest and digest[1] in producers):
                        trusted.add(image_index)
                    identity = attrs.get("id", (-1, ""))[1]
                    if ("run" not in attrs and re.fullmatch(r"docker/build-push-action@[0-9a-f]{40}", action)
                            and re.fullmatch(r"[A-Za-z_][\w-]*", identity) and ids.count(identity) == 1
                            and inputs.get("push", (-1, ""))[1] == "true"):
                        producers.add(identity)
    return trusted


def findings(path, source):
    lines, found, stages, stack = source.splitlines(), [], set(), []
    trusted_images = built_sbom_images(path, lines)
    markdown, fence = path.endswith((".md", ".mdx")), None

    def add(index, kind):
        found.append((index + 1, kind))

    def image(index, value):
        value = clean(value)
        if value and not DIGEST.fullmatch(value) and index not in trusted_images:
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
        if markdown and (marker := re.match(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)", line)):
            token, language = marker.groups()
            if fence is None:
                fence = (token[0], len(token), language.lower())
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
            stages.clear()
        docker_context = dockerfile_path(path) or bool(fence and fence[2] in {"dockerfile", "docker"})
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
        match = re.match(r"\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\w+))?", line, re.I) if docker_context else None
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
                    if markdown_image(value):
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
            if path == "docs/platform-catalog.yaml" or not allowed(path):
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
