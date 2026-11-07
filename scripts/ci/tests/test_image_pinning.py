# SPDX-License-Identifier: Apache-2.0
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

script = Path(__file__).with_name("check_image_pinning.py")
if not script.exists():
    script = Path(__file__).parents[1] / "check_image_pinning.py"
spec = importlib.util.spec_from_file_location("guard", script)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
D = "sha256:" + "a" * 64


class PinningTests(unittest.TestCase):
    def test_consumers(self):
        for prefix in ("image: ", "FROM ", "docker" + " run --rm -p example:80 ", "kubectl run app --" + "image="):
            for value in ("nginx", "nginx:latest", "nginx:alpine", "nginx:8.13.4", "ghcr.io/team/app:" + "dev-latest", "${IMAGE}", "${IMAGE:-nginx:latest}", "nginx@sha256:${DIGEST}"):
                with self.subTest(prefix=prefix, value=value):
                    self.assertTrue(guard.findings("Dockerfile" if prefix == "FROM " else "guide.md", prefix + value))
            self.assertFalse(guard.findings("Dockerfile" if prefix == "FROM " else "guide.md", prefix + "nginx@" + D))
        self.assertFalse(guard.findings("Dockerfile", "from nginx@" + D + " as builder\nFROM builder AS final"))
        self.assertTrue(guard.findings("config.json", '{' + '"image": "nginx:1.2.3"}'))
        self.assertTrue(guard.findings("config.json", '{\n  ' + '"image": "nginx:latest"\n}'))
        self.assertTrue(guard.findings("config.yml", '{name: app, ' + 'image: nginx:latest, imagePull' + 'Policy: Always}'))
        self.assertFalse(guard.findings("config.yml", "spec: {restartPolicy: Always}"))
        self.assertFalse(guard.findings("config.yml", "image: ghcr.io/team/app:" + "latest@" + D))

    def test_helm_policy_docs(self):
        self.assertTrue(guard.findings("values.yaml", "image:\n  repository: nginx\n  tag: '1.2.3'"))
        self.assertFalse(guard.findings("values.yaml", "image:\n  repository: nginx\n  tag: '1.2.3'\n  digest: " + D + " # pinned"))
        self.assertTrue(guard.findings("values.yaml", "image:\n  repository: nginx"))
        self.assertTrue(guard.findings("test.yaml", "pullPolicy: 'Always'"))
        self.assertFalse(guard.findings("test.yaml", "imagePullPolicy: IfNotPresent"))
        self.assertTrue(guard.findings("docs/guide.md", "Use `ghcr.io/team/app:1.2.3`."))
        self.assertFalse(guard.findings("docs/guide.md", "Use `http:`, `CAB-2343:42`, `path:line`."))
        self.assertTrue(guard.findings("docs/guide.md", "```yaml\nimage: nginx:1.2.3\n```"))

    def test_metadata(self):
        base = "- uses: docker/metadata-action@" + "a" * 40 + "\n  with:\n    tags: |\n      "
        for tag in ("type=semver,pattern={{version}}", "type=match,pattern=v(.*)"):
            self.assertTrue(guard.findings("build.yml", base + tag))
            self.assertFalse(guard.findings("build.yml", base + tag + "\n    flavor: |\n      latest=false"))
            self.assertTrue(guard.findings("build.yml", base + tag + "\n- uses: other/action@x\n  with:\n    flavor: latest=false"))
            self.assertTrue(guard.findings("build.yml", base + tag + "\n    flavor: |\n      latest=false\n      latest=auto"))
        for tag in ("type=raw,value=${{ inputs.environment }}-latest", "type=raw,enable=true,value=latest"):
            self.assertTrue(guard.findings("build.yml", base + tag))
        self.assertFalse(guard.findings("build.yml", base + "type=raw,value=${{ inputs.environment }}-${{ github.sha }}"))

    def test_direct_interpolated_publications(self):
        for image in ("ghcr.io/team/app", "${{ env.IMAGE }}"):
            source = "tags: |\n  " + image + ":${{ inputs.environment }}-latest"
            self.assertEqual(guard.findings("build.yml", source), [(2, "publication-floating")])
            self.assertFalse(guard.findings("build.yml", source + "@" + D))
        source = "- uses: 'docker/metadata-action@" + "a" * 40 + "'\n  with:\n    tags: |\n      type=semver,pattern={{version}}"
        self.assertEqual(guard.findings("build.yml", source), [(4, "metadata-implicit-latest")])

    def test_file_citations_and_sql(self):
        for value in ("module.py:123", "src/module.rs:42-50", "path/file.ext:123", "Dockerfile:12"):
            self.assertFalse(guard.findings("docs/guide.md", "See `" + value + "`."))
        for value in ("nginx:1", "alpine:3.20", "nginx:alpine", "ghcr.io/team/app.py:1", "registry/app.py:1"):
            self.assertTrue(guard.findings("docs/guide.md", "Use `" + value + "`."))
        for path in ("module.py", "module.go", "docs/guide.md"):
            self.assertFalse(guard.findings(path, 'query = """SELECT name\nFROM entries\nWHERE active = true"""'))
        self.assertFalse(guard.findings("docs/guide.md", "```sql\nSELECT name\nFROM entries\n```"))

    def test_explicit_dockerfile_contexts(self):
        for path in ("Dockerfile", "service/Dockerfile.dev", "templates/Dockerfile.j2", "service/build.Dockerfile", "templates/build.Dockerfile.tpl"):
            self.assertTrue(guard.allowed(path))
            for image in ("nginx", "nginx:1", "alpine:3.20", "${IMAGE}"):
                self.assertTrue(guard.findings(path, "FROM " + image))
            self.assertFalse(guard.findings(path, "FROM nginx@" + D + " AS base\nFROM base"))
        for fence in ("```dockerfile", "~~~Dockerfile", "```docker"):
            close = fence[:3]
            self.assertTrue(guard.findings("docs/guide.md", fence + "\nFROM nginx:1\n" + close))
            self.assertFalse(guard.findings("docs/guide.md", fence + "\nFROM nginx@" + D + "\n" + close))
        source = "```dockerfile\nFROM nginx@" + D + " AS builder\n```\n```dockerfile\nFROM builder\n```"
        self.assertEqual(guard.findings("docs/guide.md", source), [(5, "image-unpinned")])

    def test_paths(self):
        for path in ("private/x.yml", "a/prive/x", "codex-9.log", "a/codex.log", "claude.log", "ACCES.md", "candidate.env", "notes.txt"):
            self.assertFalse(guard.allowed(path))
        for path in ("tests/image_fixture.yaml", "docs/guide.md", "Dockerfile", "service/Dockerfile.dev"):
            self.assertTrue(guard.allowed(path))

    def test_git_boundary_and_touched_debt(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*args):
                return subprocess.check_output(["git", "-C", root, *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            guide = Path(root) / "guide.md"
            guide.write_text("image" + ": nginx:1.2.3\n")
            def commit():
                git("add", ".")
                git("-c", "user.name=Guard", "-c", "user.email=guard@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
                return git("rev-parse", "HEAD")
            base = commit()
            guide.write_text(guide.read_text() + "# changed\n")
            head = commit()
            def run(start):
                return subprocess.run(["python3", "-B", str(script.resolve()), "--base", start, "--head", head], cwd=root, capture_output=True, text=True)
            result = run(base)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "guide.md:1:image-unpinned\n", ""))
            result = run("0" * 40)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (1, guard.GUARD + ":1:scan-failed\n", ""))


if __name__ == "__main__":
    unittest.main()
