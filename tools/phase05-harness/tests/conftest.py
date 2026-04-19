"""Pytest config for phase05-harness tests.

Registers the `live` marker so `--strict-markers` stays happy without a
pytest.ini in this subtree.
"""

from __future__ import annotations


def pytest_configure(config):  # type: ignore[no-untyped-def]
    config.addinivalue_line(
        "markers",
        "live: requires ANTHROPIC_API_KEY and STOA_LIVE_SMOKE=1 (hits the real API)",
    )
