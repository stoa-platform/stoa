"""Regression: app boots cleanly without a Kafka broker (CAB-2085).

Before the fix, `consumers.deployment_consumer`, `consumers.promotion_deploy_consumer`,
`workers.git_sync_worker`, `workers.sync_engine`, and the metering consumers
instantiated `kafka.KafkaConsumer` at lifespan start. On CI runners (no broker
reachable) this produced noisy `NoBrokersAvailable` logs plus secondary
`ValueError: I/O operation on closed file` from threads logging after pytest
closed stdout.

After the fix, the master `STOA_ENABLE_KAFKA_CONSUMERS` flag gates every
Kafka-dependent consumer. Tests set it to `false` in `conftest.py`, so the
lifespan must complete without touching the broker.
"""

from __future__ import annotations

import logging
import os

import pytest
from fastapi.testclient import TestClient

FORBIDDEN_LOG_FRAGMENTS = (
    "NoBrokersAvailable",
    "I/O operation on closed file",
    "DNS lookup failed for redpanda",
)


def test_master_gate_defaults_disabled_in_test_env() -> None:
    """conftest.py must set the master gate to false before src.main is imported."""
    assert os.environ.get("STOA_ENABLE_KAFKA_CONSUMERS") == "false", (
        "conftest.py should set STOA_ENABLE_KAFKA_CONSUMERS=false before importing "
        "src.main so Kafka consumers never start during tests."
    )


def test_per_consumer_flags_respect_master_gate() -> None:
    """When the master gate is off, every Kafka-backed consumer flag must be False."""
    from src import main

    assert main.KAFKA_CONSUMERS_ENABLED is False

    kafka_backed_flags = (
        "ENABLE_DEPLOYMENT_NOTIFIER",
        "ENABLE_SNAPSHOT_CONSUMER",
        "ENABLE_SYNC_ENGINE",
        "ENABLE_CHAT_METERING_CONSUMER",
        "ENABLE_BILLING_METERING_CONSUMER",
        "ENABLE_AUDIT_TRAIL_CONSUMER",
        "ENABLE_GIT_SYNC_WORKER",
    )
    for flag in kafka_backed_flags:
        assert (
            getattr(main, flag) is False
        ), f"{flag} must AND with KAFKA_CONSUMERS_ENABLED so the master gate turns it off."


def test_audit_trail_consumer_safe_by_default() -> None:
    """Regression: src/main.py must default ENABLE_AUDIT_TRAIL_CONSUMER to "false"
    so the audit Kafka -> PG consumer is opt-in per environment.

    Static check on the source: importlib.reload(main) caused CI hangs because
    conftest.py mocks several services in src.main via patch.object(...).start(),
    and reloading drops those patches; subsequent lifespan tests then attempted
    real Kafka connections. This static check covers the same intent without
    touching module state.
    """
    import re
    from pathlib import Path

    main_py = (Path(__file__).resolve().parent.parent / "src" / "main.py").read_text()
    pattern = re.compile(
        r"ENABLE_AUDIT_TRAIL_CONSUMER\s*=\s*\(\s*"
        r"KAFKA_CONSUMERS_ENABLED\s+and\s+"
        r'os\.getenv\(\s*"ENABLE_AUDIT_TRAIL_CONSUMER"\s*,\s*"(?P<default>[^"]+)"\s*\)'
        r"\s*\.\s*lower\(\)\s*==\s*\"true\"\s*\)",
    )
    match = pattern.search(main_py)
    assert match is not None, (
        "ENABLE_AUDIT_TRAIL_CONSUMER expression in src/main.py does not match the expected shape. "
        "Update this regression if the formula changed, but keep the safe default invariant."
    )
    assert match.group("default") == "false", (
        f'src/main.py defaults ENABLE_AUDIT_TRAIL_CONSUMER to "{match.group("default")}". '
        'It must default to "false" — environments opt in explicitly via stoa-infra Helm values. '
        "See docs/plans/2026-05-08-audit-consumer-ingestion-contract.md."
    )


def test_app_lifespan_emits_no_kafka_errors(caplog: pytest.LogCaptureFixture) -> None:
    """Running the full lifespan must not surface any Kafka broker lookup."""
    from src.main import app

    caplog.set_level(logging.WARNING)

    with TestClient(app):
        pass

    leaked = [
        record.getMessage()
        for record in caplog.records
        if any(token in record.getMessage() for token in FORBIDDEN_LOG_FRAGMENTS)
    ]
    assert not leaked, (
        "Kafka consumer leaked past the STOA_ENABLE_KAFKA_CONSUMERS gate; " f"offending log lines: {leaked}"
    )
