"""CAB-1795: tooling secrets come from OpenBao through scripts/lib/stoa-secret.sh.

Infisical is retired (ADR-075). These tests drive the helper, the Council S3
key resolution and the Linear stop hooks against local doubles of curl and of
the macOS `security` tool. No network access.
"""

import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts/lib/stoa-secret.sh"
COUNCIL = ROOT / "scripts/council-review.sh"
HOOKS = ROOT / ".claude/hooks"
RENEW = "/v1/auth/token/renew-self"

# Logs argv and stdin, then answers like OpenBao (body, newline, HTTP code).
FAKE_CURL = """#!PYTHON
import json, os, sys
args = sys.argv[1:]
url = args[-1]
header = sys.stdin.read() if "@-" in args else ""
with open(os.environ["CURL_LOG"], "a") as log:
    log.write(json.dumps({"argv": args, "stdin": header}) + "\\n")
mode = os.environ.get("FAKE_MODE", "200")
if mode == "refused":
    sys.exit(7)
if url.endswith("/v1/auth/token/renew-self"):
    code, body = os.environ.get("FAKE_RENEW_CODE", "200"), "{}"
elif mode == "200":
    code, body = mode, json.dumps({"data": {"data": json.loads(os.environ["FAKE_DATA"])}})
else:
    code, body = mode, json.dumps({"errors": ["permission denied"]})
if "-o" not in args:
    sys.stdout.write(body)
sys.stdout.write("\\n" + code)
"""

FAKE_SECURITY = """#!PYTHON
import os, sys
service = os.environ.get("FAKE_KC_SERVICE", "stoa-openbao")
token = os.environ.get("FAKE_KC_TOKEN", "")
if token and sys.argv[1:] == ["find-generic-password", "-s", service, "-a", "tooling", "-w"]:
    print(token)
    sys.exit(0)
sys.exit(44)
"""


class OpenBaoDoubleTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        (self.home / ".config/stoa").mkdir(parents=True)
        (self.home / ".config/stoa/openbao-ca.pem").write_text("test CA\n")
        bindir = self.base / "bin"
        bindir.mkdir()
        for name, source in (("curl", FAKE_CURL), ("security", FAKE_SECURITY)):
            path = bindir / name
            path.write_text(source.replace("PYTHON", sys.executable, 1))
            path.chmod(0o700)
        jq = shutil.which("jq")
        self.assertIsNotNone(jq, "jq is required")
        self.log = self.base / "curl.log"
        self.token = secrets.token_urlsafe(24)
        self.value = secrets.token_urlsafe(24)
        self.env = {
            "PATH": f"{bindir}:{Path(jq).parent}:/usr/bin:/bin",
            "HOME": str(self.home),
            "CURL_LOG": str(self.log),
            "FAKE_DATA": json.dumps({"api_key": self.value}),
        }

    def run_cmd(self, argv, **extra):
        env = {**self.env, **extra}
        return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)

    def secret(self, *args, **extra):
        script = '. "$1"; shift; stoa_secret "$@"'
        return self.run_cmd(["/bin/bash", "-c", script, "bash", str(HELPER), *args], **extra)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def reads(self):
        return [c for c in self.calls() if not c["argv"][-1].endswith(RENEW)]

    def renewals(self):
        return [c for c in self.calls() if c["argv"][-1].endswith(RENEW)]

    def assert_token_hidden(self, run):
        self.assertNotIn(self.token, run.stdout + run.stderr)
        for call in self.calls():
            self.assertNotIn(self.token, " ".join(call["argv"]))
            if call["stdin"]:
                self.assertEqual(f"X-Vault-Token: {self.token}\n", call["stdin"])


class StoaSecretTests(OpenBaoDoubleTestCase):
    def test_reads_field_with_token_on_stdin_only(self):
        run = self.secret("anthropic", "api_key", STOA_OPENBAO_TOKEN=self.token)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(self.value, run.stdout)
        self.assertEqual("", run.stderr)
        argv = self.reads()[0]["argv"]
        self.assertEqual("https://127.0.0.1:18200/v1/secret/data/stoa/tooling/anthropic", argv[-1])
        self.assertEqual("-q", argv[0])
        self.assertIn(str(self.home / ".config/stoa/openbao-ca.pem"), argv)
        self.assertIn("@-", argv)
        self.assert_token_hidden(run)

    def test_keychain_then_file_fallbacks(self):
        run = self.secret("anthropic", "api_key", FAKE_KC_TOKEN=self.token)
        self.assertEqual(self.value, run.stdout, run.stderr)
        run = self.secret(
            "anthropic", "api_key", FAKE_KC_TOKEN=self.token,
            FAKE_KC_SERVICE="stoa-openbao-test", STOA_OPENBAO_KEYCHAIN_SERVICE="stoa-openbao-test",
        )
        self.assertEqual(self.value, run.stdout, run.stderr)
        (self.home / ".config/stoa/openbao-tooling-token").write_text(self.token + "\n")
        run = self.secret("anthropic", "api_key")
        self.assertEqual(self.value, run.stdout, run.stderr)
        self.assertEqual(3, len(self.reads()))
        self.assert_token_hidden(run)

    def test_missing_token_fails_before_any_request(self):
        run = self.secret("anthropic", "api_key")
        self.assertEqual(1, run.returncode)
        self.assertEqual("", run.stdout)
        self.assertEqual(1, len(run.stderr.splitlines()))
        self.assertIn("no OpenBao token", run.stderr)
        self.assertEqual([], self.calls())

    def test_failures_print_one_line_and_no_value(self):
        cases = (("403", "HTTP 403"), ("404", "HTTP 404"), ("503", "HTTP 503"), ("refused", "unreachable"))
        for mode, expected in cases:
            with self.subTest(mode=mode):
                run = self.secret("anthropic", "api_key", STOA_OPENBAO_TOKEN=self.token, FAKE_MODE=mode)
                self.assertEqual(1, run.returncode)
                self.assertEqual("", run.stdout)
                self.assertEqual(1, len(run.stderr.splitlines()), run.stderr)
                self.assertIn(expected, run.stderr)
                self.assert_token_hidden(run)
        self.assertEqual([], self.renewals())

    def test_rejects_bad_arguments_without_request(self):
        run = self.secret("anthropic", "missing", STOA_OPENBAO_TOKEN=self.token)
        self.assertEqual(1, run.returncode)
        self.assertIn("field missing not found", run.stderr)
        self.assertEqual("", run.stdout)
        before = len(self.calls())
        for path in ("../platform", "/anthropic", "a//b", "a/", "a/./b", "a b", "a?b"):
            with self.subTest(path=path):
                run = self.secret(path, "api_key", STOA_OPENBAO_TOKEN=self.token)
                self.assertEqual(2, run.returncode)
                self.assertEqual("", run.stdout)
        run = self.secret("anthropic", STOA_OPENBAO_TOKEN=self.token)
        self.assertEqual(2, run.returncode)
        self.assertIn("usage", run.stderr)
        self.assertEqual(before, len(self.calls()))

    def test_renews_at_most_once_a_day_and_ignores_failures(self):
        env = {"STOA_OPENBAO_TOKEN": self.token, "FAKE_RENEW_CODE": "403"}
        for _ in range(2):
            run = self.secret("anthropic", "api_key", **env)
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual(self.value, run.stdout)
        self.assertEqual(1, len(self.renewals()))
        self.assertIn("-d", self.renewals()[0]["argv"])
        stamps = list((self.home / ".cache/stoa").iterdir())
        self.assertEqual(1, len(stamps))
        stamps[0].write_text(f"{int(time.time()) - 90000}\n")
        # A caller running with noclobber (set -C) must not block the stamp update.
        script = 'set -C; . "$1"; stoa_secret anthropic api_key'
        run = self.run_cmd(["/bin/bash", "-c", script, "bash", str(HELPER)], **env)
        self.assertEqual(self.value, run.stdout, run.stderr)
        self.assertEqual(2, len(self.renewals()))
        self.secret("anthropic", "api_key", **env)
        self.assertEqual(2, len(self.renewals()))
        self.secret("anthropic", "api_key", STOA_OPENBAO_ADDR="https://127.0.0.1:18210/", **env)
        self.assertEqual(3, len(self.renewals()))
        self.assertTrue(self.reads()[-1]["argv"][-1].startswith("https://127.0.0.1:18210/v1/"))
        self.assert_token_hidden(run)

    def test_caller_xtrace_and_command_mode(self):
        script = '. "$1"; v=$(stoa_secret anthropic api_key); echo "${#v}"'
        run = self.run_cmd(["/bin/bash", "-xc", script, "bash", str(HELPER)], STOA_OPENBAO_TOKEN=self.token)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(str(len(self.value)), run.stdout.strip())
        self.assert_token_hidden(run)
        run = self.run_cmd([str(HELPER), "anthropic", "api_key"], STOA_OPENBAO_TOKEN=self.token)
        self.assertEqual(self.value, run.stdout, run.stderr)


class ConsumerTests(OpenBaoDoubleTestCase):
    def setUp(self):
        super().setUp()
        self.env["FAKE_DATA"] = json.dumps({"ANTHROPIC_API_KEY": self.value, "LINEAR_API_KEY": self.value})

    def resolve(self, **extra):
        script = '. "$1"; resolve_api_key; printf "%s" "${ANTHROPIC_API_KEY:-}"'
        return self.run_cmd(["/bin/bash", "-c", script, "bash", str(COUNCIL)], **extra)

    def test_council_prefers_env_and_honours_kill_switches(self):
        preset = secrets.token_urlsafe(16)
        self.assertEqual(preset, self.resolve(ANTHROPIC_API_KEY=preset).stdout)
        for switch in ("COUNCIL_NO_SECRET_BACKEND", "COUNCIL_NO_INFISICAL", "MOCK_API"):
            with self.subTest(switch=switch):
                run = self.resolve(STOA_OPENBAO_TOKEN=self.token, **{switch: "1"})
                self.assertEqual(0, run.returncode, run.stderr)
                self.assertEqual("", run.stdout)
        self.assertEqual([], self.calls())

    def test_council_falls_back_to_openbao(self):
        run = self.resolve(STOA_OPENBAO_TOKEN=self.token)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(self.value, run.stdout)
        self.assertIn("resolved via OpenBao", run.stderr)
        self.assertNotIn(self.value, run.stderr)
        self.assertTrue(self.reads()[0]["argv"][-1].endswith("/stoa/tooling/anthropic"))
        run = self.resolve(STOA_OPENBAO_TOKEN=self.token, FAKE_MODE="403")
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual("", run.stdout)
        self.assertIn("HTTP 403", run.stderr)
        self.assert_token_hidden(run)

    def test_linear_hooks_fall_back_to_openbao_root(self):
        project = self.base / "project"
        project.mkdir()
        for hook in ("stop-linear-close.sh", "stop-sync-claims.sh"):
            with self.subTest(hook=hook):
                self.log.unlink(missing_ok=True)
                argv = ["/bin/bash", str(HOOKS / hook)]
                run = self.run_cmd(argv, CLAUDE_PROJECT_DIR=str(project), LINEAR_API_KEY=self.value)
                self.assertEqual(0, run.returncode, run.stderr)
                self.assertEqual([], self.calls())
                run = self.run_cmd(argv, CLAUDE_PROJECT_DIR=str(project), STOA_OPENBAO_TOKEN=self.token)
                self.assertEqual(0, run.returncode, run.stderr)
                self.assertTrue(self.reads()[0]["argv"][-1].endswith("/stoa/tooling/root"))
                self.assert_token_hidden(run)


if __name__ == "__main__":
    unittest.main()
