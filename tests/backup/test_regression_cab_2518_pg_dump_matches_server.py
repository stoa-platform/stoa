#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 STOA Platform
"""Regression for CAB-2518: pg_dump 18 against PostgreSQL 16.

pg_dump 17+ writes ``SET transaction_timeout`` into the dump preamble.
PostgreSQL 16 rejects that parameter, so restore aborts after DROP DATABASE.
The script must select a client of the server's major version and must refuse
an incompatible preamble before it drops anything. The dump is not rewritten.
"""

from __future__ import annotations

import gzip
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup" / "backup-postgres.sh"

PSQL = """#!/bin/bash
{
  printf 'ARGS: %s\\n' "$*"
  printf 'STDIN:\\n'
  cat
  printf '\\nEND\\n'
} >> "$PSQL_LOG"
if [[ "$*" == *server_version_num* ]]; then
  printf '%s\\n' 160005
fi
exit 0
"""

PG_DUMP_18 = """#!/bin/bash
if [[ "${1:-}" == "--version" ]]; then
  printf '%s\\n' "pg_dump (PostgreSQL) 18.6 (Ubuntu 18.6-1.pgdg26.04+2)"
  exit 0
fi
printf 'dump18 %s\\n' "$*" >> "$DUMP_LOG"
cat <<'SQL'
--
-- PostgreSQL database dump
--
SET statement_timeout = 0;
SET transaction_timeout = 0;
--
-- PostgreSQL database dump complete
--
SQL
"""

PG_DUMP_16 = """#!/bin/bash
if [[ "${1:-}" == "--version" ]]; then
  printf '%s\\n' "pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+2)"
  exit 0
fi
printf 'dump16 %s\\n' "$*" >> "$DUMP_LOG"
cat <<'SQL'
--
-- PostgreSQL database dump
--
SET statement_timeout = 0;
SET lock_timeout = 0;
-- USED_CLIENT=16
--
-- PostgreSQL database dump complete
--
SQL
"""

KUBECTL = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$KUBECTL_LOG"
case "$1" in
  cluster-info) exit 0 ;;
  config) printf '%s\\n' disposable-test; exit 0 ;;
  get) printf '%s\\n' Running; exit 0 ;;
  exec)
    shift
    while [[ $# -gt 0 && "$1" != "--" ]]; do shift; done
    shift
    exec "$@"
    ;;
esac
printf 'unexpected kubectl call: %s\\n' "$*" >&2
exit 1
"""


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _gzip_dump(path: Path, sql: str) -> None:
    with gzip.open(path, "wb") as handle:
        handle.write(sql.encode("utf-8"))


COMPLETE_V16 = """--
-- PostgreSQL database dump
--
SET statement_timeout = 0;
SET lock_timeout = 0;
--
-- PostgreSQL database dump complete
--
"""

COMPLETE_V18 = """--
-- PostgreSQL database dump
--
SET statement_timeout = 0;
SET transaction_timeout = 0;
SET lock_timeout = 0;
--
-- PostgreSQL database dump complete
--
"""


class BackupClientMatch(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.psql_log = self.root / "psql.log"
        self.dump_log = self.root / "dump.log"
        self.kubectl_log = self.root / "kubectl.log"
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir()
        self.bin = self.root / "bin"
        self.lib = self.root / "client-lib"
        _write_executable(self.bin / "psql", PSQL)
        self.psql_log.write_text("", encoding="utf-8")
        self.dump_log.write_text("", encoding="utf-8")
        self.kubectl_log.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _env(self, extra_path: Path | None = None) -> dict[str, str]:
        # Clean environment: the script notifies Slack when proxy variables are
        # present, and this test must not reach a real service.
        path = os.environ.get("PATH", "/usr/bin:/bin")
        parts = [str(self.bin)]
        if extra_path is not None:
            parts.insert(0, str(extra_path))
        return {
            "PATH": ":".join(parts + [path]),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": "C",
            "LC_ALL": "C",
            "LOG_LEVEL": "INFO",
            "PG_CONNECTION_MODE": "direct",
            "BACKUP_DESTINATION": "local",
            "BACKUP_LOCAL_DIR": str(self.backup_dir),
            "PG_DATABASE": "stoa_cab_2518",
            "PG_USER": "stoa",
            "PG_CLIENT_LIB_ROOT": str(self.lib),
            "PSQL_LOG": str(self.psql_log),
            "DUMP_LOG": str(self.dump_log),
            "KUBECTL_LOG": str(self.kubectl_log),
        }

    def _run(self, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(BACKUP_SCRIPT), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_regression_cab_2518_prefers_server_major_over_newer_pg_dump(self) -> None:
        # A binary that merely lives in the v16 directory but reports v18 must
        # be ignored. Trusting the path would write SET transaction_timeout.
        _write_executable(self.lib / "16" / "bin" / "pg_dump", PG_DUMP_18)
        _write_executable(self.bin / "pg_dump", PG_DUMP_18)
        _write_executable(self.bin / "pg_dump-16", PG_DUMP_16)

        result = self._run([], self._env())

        self.assertEqual(result.returncode, 0, result.stderr)
        location = result.stdout.strip()
        self.assertTrue(location.endswith(".sql.gz"), result.stdout)
        with gzip.open(location, "rt", encoding="utf-8") as handle:
            dump = handle.read()
        self.assertIn("USED_CLIENT=16", dump)
        self.assertNotIn("transaction_timeout", dump)
        dump_log = self.dump_log.read_text(encoding="utf-8")
        self.assertIn("dump16", dump_log)
        self.assertNotIn("dump18", dump_log)
        self.assertNotIn("DROP DATABASE", self.psql_log.read_text(encoding="utf-8"))

    def test_regression_cab_2518_refuses_newer_client_without_dropping(self) -> None:
        _write_executable(self.bin / "pg_dump", PG_DUMP_18)

        result = self._run([], self._env())

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to dump", result.stderr)
        self.assertIn("transaction_timeout", result.stderr)
        self.assertEqual(self.dump_log.read_text(encoding="utf-8"), "")
        self.assertNotIn("DROP DATABASE", self.psql_log.read_text(encoding="utf-8"))
        self.assertEqual(list(self.backup_dir.glob("**/*.sql.gz")), [])

    def test_regression_cab_2518_rejects_incompatible_preamble_before_drop(self) -> None:
        _write_executable(self.bin / "pg_dump", PG_DUMP_16)
        bad = self.root / "from-pg-dump-18.sql.gz"
        _gzip_dump(bad, COMPLETE_V18)

        result = self._run(["--restore", str(bad), "--force"], self._env())

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to restore", result.stderr)
        self.assertIn("was not modified", result.stderr)
        self.assertIn("transaction_timeout", result.stderr)
        self.assertNotIn("DROP DATABASE", self.psql_log.read_text(encoding="utf-8"))

    def test_regression_cab_2518_compatible_preamble_still_drops_before_replay(self) -> None:
        _write_executable(self.bin / "pg_dump", PG_DUMP_16)
        good = self.root / "from-pg-dump-16.sql.gz"
        _gzip_dump(good, COMPLETE_V16)

        result = self._run(["--restore", str(good), "--force"], self._env())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Refusing to restore", result.stderr)
        self.assertIn("DROP DATABASE", self.psql_log.read_text(encoding="utf-8"))

    def test_regression_cab_2518_kubectl_keeps_pod_binary_and_refuses_mismatch(self) -> None:
        # A matching client on the host must not be injected into kubectl exec:
        # that path does not exist inside the database pod.
        _write_executable(self.lib / "16" / "bin" / "pg_dump", PG_DUMP_16)
        _write_executable(self.bin / "pg_dump-16", PG_DUMP_16)
        _write_executable(self.bin / "pg_dump", PG_DUMP_18)
        shim = self.root / "shim"
        _write_executable(shim / "kubectl", KUBECTL)
        env = self._env(extra_path=shim)
        env["PG_CONNECTION_MODE"] = "kubectl"
        env["PG_NAMESPACE"] = "stoa-system"
        env["PG_POD_NAME"] = "control-plane-db-0"

        result = self._run([], env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to dump", result.stderr)
        kubectl_log = self.kubectl_log.read_text(encoding="utf-8")
        self.assertIn(
            "exec -i -n stoa-system control-plane-db-0 -- pg_dump --version",
            kubectl_log,
        )
        self.assertNotIn("pg_dump-16", kubectl_log)
        self.assertNotIn(str(self.lib), kubectl_log)
        self.assertEqual(self.dump_log.read_text(encoding="utf-8"), "")
        self.assertNotIn("DROP DATABASE", self.psql_log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
