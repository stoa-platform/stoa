"""Regression test for CAB-2199 Phase 3-C — opensearch_audit precedence detection.

Before the fix:
- ``Settings._hydrate_opensearch_audit`` detected an explicit caller-passed
  sub-model by comparing ``self.opensearch_audit.model_dump()`` to a fresh
  default-factory instance dump. When the caller passed a default-factory
  instance explicitly —
  ``Settings(opensearch_audit=OpenSearchAuditConfig())`` — the dumps matched
  and the validator misclassified the kwarg as "absent", letting the flat
  ``OPENSEARCH_HOST`` / ``AUDIT_*`` env vars override the explicit value.
- This violated the CLAUDE.md note #2 contract ("explicit sub-model wins").

After the fix:
- The validator now uses ``self.model_fields_set``. Pydantic v2 lists every
  field name the caller supplied at construction (regardless of whether the
  value matches the default-factory shape), so the explicit kwarg is
  correctly classified.

Audit trail: ``docs/infra/INFRA-1a-BUG-HUNT.md`` BH-INFRA1a-002 (Family B).
"""

# regression for CAB-2199
from __future__ import annotations

import pytest

from src.config import OpenSearchAuditConfig, Settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Tmp cwd with no .env + cleared opensearch_audit env vars."""
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENSEARCH_HOST",
        "OPENSEARCH_USER",
        "OPENSEARCH_PASSWORD",
        "OPENSEARCH_VERIFY_CERTS",
        "OPENSEARCH_CA_CERTS",
        "OPENSEARCH_TIMEOUT",
        "AUDIT_ENABLED",
        "AUDIT_BUFFER_SIZE",
        "AUDIT_FLUSH_INTERVAL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_regression_cab_2199_default_factory_submodel_explicit_wins(monkeypatch):
    """Default-factory ``OpenSearchAuditConfig()`` passed explicitly must
    short-circuit the flat-env hydration.

    Pre-Phase-3-C this test would have failed: with ``OPENSEARCH_HOST``
    set in env, the dump-equality detection misclassified the explicit
    default-factory instance as "absent" and the env value bled into
    ``settings.opensearch_audit.host``.
    """
    monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.example.io")
    monkeypatch.setenv("AUDIT_BUFFER_SIZE", "999")

    s = Settings(opensearch_audit=OpenSearchAuditConfig())

    # Default-factory values preserved (NOT overridden by env).
    assert s.opensearch_audit.host == "https://opensearch.gostoa.dev"
    assert s.opensearch_audit.audit_buffer_size == 100


def test_regression_cab_2199_non_default_explicit_submodel_still_wins(monkeypatch):
    """Counter-test: a non-default explicit sub-model also short-circuits
    the flat-env hydration. This case worked pre-Phase-3-C (the dump-equality
    detection caught it) — pinning ensures the new ``model_fields_set``
    detection didn't lose the existing contract.
    """
    monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.example.io")

    s = Settings(opensearch_audit=OpenSearchAuditConfig(host="https://explicit.io"))

    assert s.opensearch_audit.host == "https://explicit.io"
    assert s.opensearch_audit.host != "https://from-env.example.io"


def test_regression_cab_2199_no_explicit_kwarg_hydrates_from_env(monkeypatch):
    """Counter-test: when the caller does NOT pass ``opensearch_audit=``,
    flat-env hydration kicks in (the legitimate path).
    """
    monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.example.io")
    monkeypatch.setenv("AUDIT_BUFFER_SIZE", "777")

    s = Settings()

    assert s.opensearch_audit.host == "https://from-env.example.io"
    assert s.opensearch_audit.audit_buffer_size == 777
