"""Unit tests for the demo reset CLI entry point (CAB-2149 c/3).

Boundaries tested without a real database: argument parsing + the
missing-``DATABASE_URL`` guard. End-to-end DB validation is performed
when the CLI is wired into the Phase 2 demo harness.
"""

from __future__ import annotations

import asyncio

import pytest
from scripts.demo.reset import _main, parse_args


class TestParseArgs:
    def test_defaults_are_full_cycle(self) -> None:
        args = parse_args([])
        assert args.check is False
        assert args.reset_only is False

    def test_check_flag(self) -> None:
        args = parse_args(["--check"])
        assert args.check is True

    def test_reset_only_flag(self) -> None:
        args = parse_args(["--reset-only"])
        assert args.reset_only is True


class TestMissingDatabaseUrl:
    def test_regression_cab_2149_cli_exits_1_without_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        exit_code = asyncio.run(_main(parse_args([])))
        assert exit_code == 1
