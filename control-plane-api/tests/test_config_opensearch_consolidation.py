"""CAB-2199 / INFRA-1a S3 — regression guards for the OpenSearch consolidation.

Replaces the standalone ``OpenSearchSettings`` (formerly in
``opensearch/opensearch_integration.py``) with ``Settings.opensearch_audit``
(an ``OpenSearchAuditConfig`` sub-model hydrated from flat env vars by the
``_hydrate_opensearch_audit`` model_validator). Mirrors the
``GitProviderConfig`` pattern.

Tests cover:
- Flat env hydration into the sub-model.
- ``Settings.OPENSEARCH_URL`` (docs/embedding endpoint) stays distinct from
  ``opensearch_audit.host`` (audit endpoint).
- ``SecretStr`` round-trip — consumer code unwraps with ``.get_secret_value()``;
  ``repr(Settings(...))`` cannot leak the password.
- Explicit ``Settings(opensearch_audit=...)`` sub-model wins over flat env
  fields (Council Stage 2 #8 nuance).
- ``model_dump()`` excludes the flat env-ingress fields (``exclude=True``)
  and dumps the sub-model only.
"""

from __future__ import annotations

import pytest

from src.config import OpenSearchAuditConfig, Settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Run each test in a tmp cwd with no .env file present + cleared env."""
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
        "OPENSEARCH_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_opensearch_audit_hydrated_from_flat_env(monkeypatch):
    """Flat env vars (``OPENSEARCH_HOST``, ``AUDIT_BUFFER_SIZE``, etc.)
    flow into ``settings.opensearch_audit``."""
    monkeypatch.setenv("OPENSEARCH_HOST", "https://opensearch.example.io")
    monkeypatch.setenv("AUDIT_BUFFER_SIZE", "200")
    monkeypatch.setenv("OPENSEARCH_TIMEOUT", "60")

    s = Settings()

    assert s.opensearch_audit.host == "https://opensearch.example.io"
    assert s.opensearch_audit.audit_buffer_size == 200
    assert s.opensearch_audit.timeout == 60


def test_opensearch_audit_distinct_from_docs_search_url():
    """``OPENSEARCH_URL`` (docs/embedding endpoint) and ``opensearch_audit.host``
    (audit endpoint) MUST stay distinct — they can target different OpenSearch
    clusters in prod. See CLAUDE.md note #2 for the namespace explanation."""
    s = Settings(
        OPENSEARCH_URL="http://docs.local:9200",
        OPENSEARCH_HOST="https://audit.local",
    )

    assert s.OPENSEARCH_URL == "http://docs.local:9200"
    assert s.opensearch_audit.host == "https://audit.local"
    # The two values are semantically distinct
    assert s.OPENSEARCH_URL != s.opensearch_audit.host


def test_opensearch_password_secret_unwrapped_for_client():
    """``SecretStr`` round-trip — consumer code must unwrap with
    ``.get_secret_value()`` to pass the raw value to the OpenSearch client."""
    s = Settings(OPENSEARCH_PASSWORD="leaky-test-value")  # noqa: S106
    assert s.opensearch_audit.password.get_secret_value() == "leaky-test-value"
    # repr() must not leak — both on the sub-model and on the full Settings
    assert "leaky-test-value" not in repr(s)
    assert "leaky-test-value" not in repr(s.opensearch_audit)


def test_explicit_opensearch_audit_submodel_wins_over_flat_env(monkeypatch):
    """Council Stage 2 #8 nuance: an explicit
    ``Settings(opensearch_audit=OpenSearchAuditConfig(...))`` instance wins
    over the flat env fields. Phase 3-C detection uses ``model_fields_set``
    so any explicit kwarg short-circuits the flat-env hydration regardless
    of whether the value matches the default-factory shape."""
    monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.io")
    explicit = OpenSearchAuditConfig(host="https://explicit.io")

    s = Settings(opensearch_audit=explicit)

    # Explicit sub-model wins
    assert s.opensearch_audit.host == "https://explicit.io"
    # Flat env did NOT bleed in
    assert s.opensearch_audit.host != "https://from-env.io"


def test_explicit_default_factory_submodel_wins_over_flat_env(monkeypatch):
    """Phase 3-C BH-INFRA1a-002 — passing a default-factory instance
    explicitly (``opensearch_audit=OpenSearchAuditConfig()``) is treated
    as "explicit" and short-circuits the flat-env hydration.

    Pre-Phase-3-C, the validator compared ``model_dump()`` outputs to a
    fresh default-factory instance — they matched, the explicit sub-model
    was misclassified as "default", and flat env vars (``OPENSEARCH_HOST``)
    silently overrode the caller's intent. ``model_fields_set`` lists
    every field name the caller supplied at construction, so the explicit
    kwarg is now correctly classified.
    """
    monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.example.io")
    monkeypatch.setenv("AUDIT_BUFFER_SIZE", "999")

    s = Settings(opensearch_audit=OpenSearchAuditConfig())

    # Default-factory values preserved (NOT overridden by env)
    assert s.opensearch_audit.host == "https://opensearch.gostoa.dev"
    assert s.opensearch_audit.audit_buffer_size == 100


def test_explicit_path_emits_debug_log(caplog):
    """Phase 3-C BH-INFRA1a-012 — operator debug breadcrumb. The validator
    logs a ``DEBUG`` line each path so operators can tell whether
    ``opensearch_audit.host`` came from an explicit sub-model or from
    flat env hydration."""
    with caplog.at_level("DEBUG", logger="src.config"):
        Settings(opensearch_audit=OpenSearchAuditConfig(host="https://x.io"))
    matching = [
        r for r in caplog.records
        if "opensearch_audit" in r.message and "explicit" in r.message
    ]
    assert matching, f"expected explicit-path debug log, got: {[r.message for r in caplog.records]}"


def test_flat_env_path_emits_debug_log(caplog):
    """Phase 3-C BH-INFRA1a-012 — counter-test of the debug breadcrumb."""
    with caplog.at_level("DEBUG", logger="src.config"):
        Settings()
    matching = [
        r for r in caplog.records
        if "opensearch_audit" in r.message and "hydrating from flat" in r.message
    ]
    assert matching, f"expected flat-env-path debug log, got: {[r.message for r in caplog.records]}"


def test_model_dump_excludes_flat_opensearch_fields():
    """The flat env-ingress fields are ``exclude=True`` to keep them out of
    ``model_dump()`` / JSON schema; the sub-model is the dumpable surface."""
    s = Settings(OPENSEARCH_PASSWORD="leaky-test-value")  # noqa: S106
    dumped = s.model_dump()

    # Flat ingress fields excluded
    assert "OPENSEARCH_HOST" not in dumped
    assert "OPENSEARCH_USER" not in dumped
    assert "OPENSEARCH_PASSWORD" not in dumped
    assert "AUDIT_ENABLED" not in dumped
    assert "AUDIT_BUFFER_SIZE" not in dumped

    # Sub-model is present
    assert "opensearch_audit" in dumped
    sub = dumped["opensearch_audit"]
    assert sub["host"] == "https://opensearch.gostoa.dev"
    # SecretStr still masked in dump (not the raw value)
    assert sub["password"].get_secret_value() == "leaky-test-value"


def test_get_settings_returns_consolidated_submodel(monkeypatch):
    """``opensearch.opensearch_integration.get_settings()`` is a back-compat
    accessor that returns the consolidated ``Settings.opensearch_audit``
    sub-model. Legacy importers
    ``from ...opensearch_integration import get_settings`` keep working
    without code change.

    Phase 3-D BH-INFRA1a-008 — the test now patches the module-level
    ``settings`` singleton with a fresh ``Settings()`` instantiated under
    the fixture's controlled env so the assertions actually exercise the
    Phase 2 consolidation contract under known config (rather than
    asserting only the type of the boot-time singleton).
    """
    import src.opensearch.opensearch_integration as opensearch_integration

    monkeypatch.setenv("OPENSEARCH_HOST", "https://controlled.example.io")
    monkeypatch.setenv("AUDIT_BUFFER_SIZE", "42")
    fresh = Settings()
    monkeypatch.setattr(opensearch_integration, "settings", fresh)

    s = opensearch_integration.get_settings()

    # Must be the OpenSearchAuditConfig type, not the legacy OpenSearchSettings.
    assert isinstance(s, OpenSearchAuditConfig)
    # Field shape preserved (consumer contract).
    assert hasattr(s, "host")
    assert hasattr(s, "user")
    assert hasattr(s, "password")
    assert hasattr(s, "audit_enabled")
    # Behaviour under controlled env: flat-env hydration reflected in the
    # sub-model returned by get_settings().
    assert s.host == "https://controlled.example.io"
    assert s.audit_buffer_size == 42
