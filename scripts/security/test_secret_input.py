"""Exercise secret transfer to child processes using local command doubles."""

import json
import os
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SecretInputTests(unittest.TestCase):
    def test_curl_receives_secrets_by_descriptor_and_preserves_stdin(self):
        token = secrets.token_urlsafe(32) + '\\"\n'
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fake = base / "curl"
            fake.write_text(
                "#!/usr/bin/python3\nimport json, os, sys\n"
                "from pathlib import Path\n"
                "config = Path(sys.argv[-1]).read_text()\n"
                "Path(os.environ['CAPTURE']).write_text(json.dumps([config, sys.stdin.read()]))\n"
                "print(json.dumps(sys.argv[1:]))\n"
            )
            fake.chmod(0o700)
            command = 'source "$HELPER"; curl -sf http://keycloak:8080 -H "$TOKEN" --data-urlencode "password=$TOKEN" --data-binary @-'
            run = subprocess.run(
                ["/bin/bash", "-euc", command],
                input="body",
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": str(base),
                    "HELPER": str(ROOT / "scripts/lib/secret-input.sh"),
                    "TOKEN": token,
                    "CAPTURE": str(base / "capture"),
                },
            )
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertNotIn(token, run.stdout + run.stderr)
            self.assertEqual(["-q", "--config", "/dev/fd/3"], json.loads(run.stdout))
            config, body = json.loads((base / "capture").read_text())
            header = next(
                line.partition(" = ")[2]
                for line in config.splitlines()
                if line.startswith("header")
            )
            self.assertEqual(token, json.loads(header))
            self.assertEqual("body", body)

    def test_unknown_options_fail_without_echo(self):
        token = secrets.token_urlsafe(32)
        run = subprocess.run(
            ["/bin/bash", "-euc", 'source "$HELPER"; curl --unknown "$TOKEN"'],
            env={"HELPER": str(ROOT / "scripts/lib/secret-input.sh"), "TOKEN": token},
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, run.returncode)
        self.assertNotIn(token, run.stdout + run.stderr)

    def test_hook_curl_config_escaping(self):
        token = secrets.token_urlsafe(32) + '\\"\n'
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fake = base / "curl"
            fake.write_text(
                "#!/usr/bin/python3\nimport os, sys\nfrom pathlib import Path\n"
                "Path(os.environ['CAPTURE']).write_text(sys.stdin.read())\n"
                "print('request completed')\n"
            )
            fake.chmod(0o700)
            run = subprocess.run(
                ["/bin/sh", "-ec", '. "$HELPER"; curl -sf http://keycloak:8080 -H "$TOKEN"'],
                env={
                    **os.environ,
                    "PATH": str(base) + ":/usr/bin",
                    "TOKEN": token,
                    "HELPER": str(ROOT / "charts/stoa-platform/files/curl-config.sh"),
                    "CAPTURE": str(base / "capture"),
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertNotIn(token, run.stdout + run.stderr)
            config = (base / "capture").read_text()
            value = next(
                line.partition(" = ")[2]
                for line in config.splitlines()
                if line.startswith("header")
            )
            self.assertEqual(token, json.loads(value))
