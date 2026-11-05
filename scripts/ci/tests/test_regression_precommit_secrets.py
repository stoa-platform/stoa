"""Exercise the secret guard against real Git indexes, without network access."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "scripts/ci/precommit_secrets.py"


class SecretGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, timeout=10
        )

    def stage(self, content, name="sample.txt"):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git("add", "--", name)
        return path

    def record_head(self):
        # Build a baseline tree directly; no commit or hook bypass is needed.
        tree = self.git("write-tree").stdout.strip().decode()
        who = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
        commit = self.git(*who, "commit-tree", tree, "-m", "test baseline").stdout.strip()
        self.git("update-ref", "HEAD", commit.decode())

    def invoke(self, *args):
        return subprocess.run(args, cwd=self.repo, capture_output=True, text=True, timeout=10)

    def scan(self, message=None):
        args = ["python3", str(GUARD)]
        if message is not None:
            path = self.repo / "message"
            path.write_text(message)
            args.append(str(path))
        return self.invoke(*args)

    def assert_blocked(self, result, content):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Secret guard:", result.stderr)
        self.assertNotIn(content.strip(), result.stdout + result.stderr)

    def test_clean_index_and_message_pass(self):
        self.stage('title = "Public example"\n')
        self.assertEqual(self.scan().returncode, 0)
        self.assertEqual(self.scan("fix: improve input validation\n").returncode, 0)

    def test_empty_index_passes(self):
        self.assertEqual(self.scan().returncode, 0)

    def test_obvious_fake_tokens_block_in_index_and_message(self):
        tokens = [
            "AKIA" + "A" * 16,
            "ghp_" + "A" * 36,
            "github_pat_" + "A" * 82,
            "xoxb-" + "1234567890-" * 2 + "A" * 24,
            "-----BEGIN " + "RSA PRIVATE KEY-----",
            "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----",
            'api_key = "' + "FAKE" * 10 + '"',
            'client_secret: "' + "FAKE" * 6 + '"',
            'DB_PASSWORD: "' + "FAKE" * 6 + '"',
            "password: " + "Fake" * 2 + "123!",
            "API_KEY=" + "FAKE" * 4 + "/+=",
        ]
        for token in tokens:
            with self.subTest(kind=token[:4]):
                self.stage(token + "\n")
                self.assert_blocked(self.scan(), token)
                self.assert_blocked(self.scan("fix: example\n\n" + token), token)

    def test_safe_references_and_placeholders_pass(self):
        lines = [
            'api_key = "' + v + '"' for v in ["REPLACE_FROM_VAULT", "${API_KEY:-}", "<YOUR_KEY>"]
        ]
        lines += [
            'api_key = os.getenv("API_KEY")',
            "const apiKey = process.env.API_KEY;",
            "password = settings.db_password",
            "  password: formData.password,",
            "self.client_secret = self.client_secret  # attribute",
            "accessToken: dpopAccessToken!,",
            "login(username=username, password=password, api_key=API_KEY)",
            "client_secret: SecretStr",
        ]
        for line in lines:
            with self.subTest(line=line):
                self.stage(line + "\n")
                self.assertEqual(self.scan().returncode, 0)
                self.assertEqual(self.scan("fix: example\n\n" + line).returncode, 0)

    def test_worktree_cannot_hide_staged_secret(self):
        token = "ghp_" + "A" * 36
        path = self.stage(token)
        path.write_text("clean worktree\n")
        self.assert_blocked(self.scan(), token)

    def test_unstaged_secret_is_not_committed(self):
        path = self.stage("clean index\n")
        path.write_text("ghp_" + "A" * 36)
        self.assertEqual(self.scan().returncode, 0)

    def test_only_added_lines_are_scanned(self):
        self.stage("ghp_" + "A" * 36 + "\n")
        self.record_head()
        self.stage("clean replacement\n")
        self.assertEqual(self.scan().returncode, 0)

    def test_new_sensitive_paths_block_even_with_clean_content(self):
        names = [".env", ".env.local", ".env.development", "key.pem", "key.key", "vars.tfvars"]
        names += ["credentials.json", ".aws/credentials", ".git-credentials", "ci.credentials"]
        for name in names:
            with self.subTest(name=name):
                self.stage("clean\n", name)
                result = self.scan()
                self.assertEqual(result.returncode, 1)
                self.assertIn("sensitive filename", result.stderr)
                self.git("read-tree", "--empty")

    def test_rename_to_sensitive_path_blocks(self):
        self.stage("clean\n", "notes.txt")
        self.record_head()
        self.git("mv", "notes.txt", ".env")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("sensitive filename", result.stderr)

    def test_templates_and_credential_sources_can_be_added_and_modified(self):
        self.stage("tracked\n", "portal/.env.development")  # tracked env file, edits only
        self.record_head()
        names = ["portal/.env.development", "deploy/.env.example", ".env.sample"]
        names += ["src/credentials.rs", "docs/credentials.md", "ui/CredentialsViewer.tsx"]
        for content in ["clean\n", "clean edit\n"]:
            for name in names:
                self.stage(content, name)
            self.assertEqual(self.scan().returncode, 0, content)
            self.record_head()
        token = "ghp_" + "A" * 36
        self.stage(token + "\n", names[1])
        self.assert_blocked(self.scan(), token)

    def test_test_and_example_paths_are_not_exempt(self):
        token = "ghp_" + "A" * 36
        self.stage(token, "tests/fixture.example")
        self.assert_blocked(self.scan(), token)

    def test_added_line_starting_with_plus_is_scanned(self):
        token = "ghp_" + "A" * 36
        self.stage("++" + token)
        self.assert_blocked(self.scan(), token)

    def test_missing_message_fails_closed(self):
        result = self.invoke("python3", str(GUARD), str(self.repo / "missing"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Secret guard:", result.stderr)

    def test_real_hooks_refuse_secrets_before_running_other_tools(self):
        guard = self.repo / "scripts/ci/precommit_secrets.py"
        guard.parent.mkdir(parents=True)
        shutil.copyfile(GUARD, guard)
        token = "ghp_" + "A" * 36
        self.stage(token)
        message = self.repo / "message"
        message.write_text("fix: example\n\n" + token)
        for hook in ["pre-commit", "commit-msg"]:
            with self.subTest(hook=hook):
                result = self.invoke("/bin/sh", str(ROOT / ".husky" / hook), str(message))
                self.assert_blocked(result, token)

    def test_existing_hooks_invoke_guard_before_other_checks(self):
        for name in ["pre-commit", "commit-msg"]:
            lines = (ROOT / ".husky" / name).read_text().splitlines()
            self.assertIn("scripts/ci/precommit_secrets.py", lines[0])
            self.assertIn("|| exit", lines[0])
