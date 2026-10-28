"""Regression tests for the data minimisation of the audit actor's network
identifiers (source address and user agent).

Rules, applied once in ``AuditMiddleware.dispatch`` before either audit store
(OpenSearch document, PostgreSQL dual-write) is written:

- the source address is truncated to its network: IPv4 /24, IPv6 /48;
- the user agent is kept only when the outcome is not ``success``.

Events written before this change are not touched (append-only stores).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException

from src.opensearch.audit_middleware import (
    AuditMiddleware,
    minimise_actor,
    truncate_ip,
)

# --- truncate_ip -------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("203.0.113.77", "203.0.113.0"),  # IPv4 -> /24
        ("198.51.100.1", "198.51.100.0"),
        ("127.0.0.1", "127.0.0.0"),  # loopback is not special-cased
        ("2001:db8:abcd:1234:5678:9abc:def0:1", "2001:db8:abcd::"),  # IPv6 -> /48
        ("2001:db8::1", "2001:db8::"),
        ("::1", "::"),
        ("::ffff:203.0.113.77", "203.0.113.0"),  # IPv4-mapped IPv6 -> IPv4 /24
        ("fe80::1%eth0", "fe80::"),  # zone index dropped
        (None, None),
        ("", ""),
    ],
)
def test_truncate_ip(host, expected):
    assert truncate_ip(host) == expected


# --- refusal: a value that does not parse is never written --------------------


@pytest.mark.parametrize(
    "host",
    [
        "testclient",  # Starlette TestClient name
        "/run/uvicorn.sock",  # unix socket path
        " 203.0.113.77",  # leading space
        "203.0.113.77:443",  # host:port
        "[2001:db8::1]",  # bracketed literal
        "0x7f000001",  # hexadecimal integer
        "2130706433",  # decimal integer
        "203.0.113",  # short form
        "0300.0.113.77",  # octal octet (rejected by ipaddress)
        "2001:db8::1::2",  # double "::"
    ],
)
def test_truncate_ip_refuses_values_that_do_not_parse(host):
    assert truncate_ip(host) is None


@pytest.mark.parametrize("host", [3405803853, b"203.0.113.77", ["203.0.113.77"], 1.5, object()])
def test_truncate_ip_refuses_values_that_are_not_strings(host):
    # A non-string value must not raise inside the ``finally`` of ``dispatch``
    # (which would lose the audit event): it is refused like any other value.
    assert truncate_ip(host) is None


# --- IPv6 forms that embed an IPv4 address: minimised as that IPv4 (/24) ------
# Documentation addresses only (RFC 5737 192.0.2.0/24, 198.51.100.0/24,
# 203.0.113.0/24; RFC 3849 2001:db8::/32).


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        # IPv4-mapped ::ffff:0:0/96 (RFC 4291 s2.5.5.2), both notations
        ("::ffff:203.0.113.77", "203.0.113.0"),
        ("::ffff:cb00:714d", "203.0.113.0"),
        ("::FFFF:203.0.113.77", "203.0.113.0"),
        # IPv4-compatible ::/96 (RFC 4291 s2.5.5.1, deprecated), both notations
        ("::203.0.113.77", "203.0.113.0"),
        ("::cb00:714d", "203.0.113.0"),
        # NAT64 well-known prefix 64:ff9b::/96 (RFC 6052 s2.1)
        ("64:ff9b::203.0.113.77", "203.0.113.0"),
        ("64:ff9b::cb00:714d", "203.0.113.0"),
        # NAT64 local-use prefix 64:ff9b:1::/48 (RFC 8215), /96 layout
        ("64:ff9b:1::203.0.113.77", "203.0.113.0"),
        # Teredo 2001::/32 (RFC 4380): server 198.51.100.1, client 203.0.113.77
        # (client bits XORed with 0xffffffff: 203.0.113.77 -> 34ff:8eb2)
        ("2001:0:c633:6401:0:0:34ff:8eb2", "203.0.113.0"),
        ("2001:0:c633:6401:8000:ffff:34ff:8eb2", "203.0.113.0"),  # flags/port set
        # 6to4 2002::/16 (RFC 3056): 2002:cb00:714d::/48 embeds 203.0.113.77
        ("2002:cb00:714d::1", "203.0.113.0"),
        ("2002:cb00:714d:abcd:1234:5678:9abc:def0", "203.0.113.0"),
    ],
)
def test_truncate_ip_minimises_the_embedded_ipv4(host, expected):
    assert truncate_ip(host) == expected


def test_teredo_server_address_is_not_kept():
    # The Teredo server (198.51.100.1 here) is not the caller: nothing of it
    # survives, only the client's /24.
    out = truncate_ip("2001:0:c633:6401:0:0:34ff:8eb2")
    assert out == "203.0.113.0"
    assert "198.51.100" not in out
    assert "c633" not in out


@pytest.mark.parametrize(
    "host",
    [
        "::ffff:203.0.113.77",  # IPv4-mapped
        "::ffff:cb00:714d",
        "::203.0.113.77",  # IPv4-compatible
        "::cb00:714d",
        "64:ff9b::203.0.113.77",  # NAT64 well-known prefix
        "64:ff9b::cb00:714d",
    ],
)
def test_mapped_compatible_and_nat64_never_keep_the_full_ipv4(host):
    # Symmetric with the 6to4 and Teredo non-leak tests: the full embedded
    # address (203.0.113.77, cb00:714d) never survives, in any notation.
    out = truncate_ip(host)
    assert out == "203.0.113.0"
    assert "113.77" not in out
    assert "714d" not in out
    assert "ffff" not in out and "ff9b" not in out


def test_six_to_four_never_keeps_the_full_ipv4():
    # Without the 6to4 rule, the /48 truncation would keep the whole IPv4
    # address in the top 48 bits (2002:cb00:714d::).
    assert truncate_ip("2002:cb00:714d::1") != "2002:cb00:714d::"


def test_nat64_local_use_with_an_ambiguous_layout_keeps_no_ipv4_bits():
    # 64:ff9b:1::/48 with a non-/96 RFC 6052 layout: the IPv4 position depends
    # on the operator's prefix length, so the generic /48 rule applies and the
    # result carries no bit of the embedded address.
    assert truncate_ip("64:ff9b:1:cb00:714d::") == "64:ff9b:1::"
    assert truncate_ip("64:ff9b:1:cb00:0:714d::") == "64:ff9b:1::"


@pytest.mark.parametrize("host", ["::", "::1"])
def test_unspecified_and_loopback_are_not_ipv4_compatible(host):
    assert truncate_ip(host) == "::"


def test_embedded_ipv4_output_fits_the_pg_column():
    for host in ("2002:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "64:ff9b::ffff:ffff"):
        assert len(truncate_ip(host)) <= 45


def test_truncated_value_fits_the_pg_column():
    # audit_events.client_ip is String(45): the longest possible output is an
    # IPv6 network address, never longer than the input.
    longest = "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
    assert len(truncate_ip(longest)) <= 45


# --- minimise_actor ----------------------------------------------------------


def _actor(ua: str | None = "Mozilla/5.0 pytest") -> dict:
    return {"ip_address": "203.0.113.77", "user_agent": ua, "type": "user", "id": "u1"}


def test_minimise_actor_drops_user_agent_on_success():
    actor = minimise_actor(_actor(), "success")
    assert actor["ip_address"] == "203.0.113.0"
    assert actor["user_agent"] is None
    assert actor["id"] == "u1"  # other fields untouched


@pytest.mark.parametrize("outcome", ["failure", "denied", "error"])
def test_minimise_actor_keeps_user_agent_when_not_success(outcome):
    actor = minimise_actor(_actor(), outcome)
    assert actor["ip_address"] == "203.0.113.0"
    assert actor["user_agent"] == "Mozilla/5.0 pytest"


def test_minimise_actor_tolerates_missing_fields():
    actor = minimise_actor({"type": "anonymous"}, "failure")
    assert actor["ip_address"] is None
    assert "user_agent" not in actor


def test_minimise_actor_very_long_user_agent_is_kept_verbatim_on_failure():
    ua = "x" * 4096
    assert minimise_actor(_actor(ua), "failure")["user_agent"] == ua


# --- end to end through the middleware (both stores) -------------------------


def _build_app(monkeypatch) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    """App with the audit middleware, a fake OpenSearch logger and a spied PG write."""
    app = FastAPI()

    @app.get("/v1/things")
    async def list_things():
        return {"ok": True}

    @app.post("/v1/things")
    async def create_thing():
        return {"ok": True}

    @app.post("/v1/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="no")

    audit_logger = MagicMock()
    audit_logger.log = AsyncMock()
    pg_write = AsyncMock()
    app.add_middleware(AuditMiddleware, audit_logger=audit_logger)
    # Spy on the dual-write without a database
    monkeypatch.setattr(AuditMiddleware, "_write_pg_audit", pg_write)
    return app, audit_logger.log, pg_write


@pytest.mark.asyncio
async def test_successful_mutation_writes_truncated_ip_and_no_user_agent(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app, os_log, pg_write = _build_app(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v1/things", headers={"User-Agent": "pytest-ua"})
    assert resp.status_code == 200

    event = os_log.await_args.args[0]
    assert event.outcome == "success"
    assert event.actor["ip_address"] == "127.0.0.0"  # ASGITransport client is 127.0.0.1
    assert event.actor["user_agent"] is None

    kwargs = pg_write.await_args.kwargs
    assert kwargs["client_ip"] == "127.0.0.0"
    assert kwargs["user_agent"] is None


@pytest.mark.asyncio
async def test_failed_mutation_keeps_user_agent_in_both_stores(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app, os_log, pg_write = _build_app(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v1/forbidden", headers={"User-Agent": "pytest-ua"})
    assert resp.status_code == 403

    event = os_log.await_args.args[0]
    assert event.outcome == "failure"
    assert event.actor["ip_address"] == "127.0.0.0"
    assert event.actor["user_agent"] == "pytest-ua"

    kwargs = pg_write.await_args.kwargs
    assert kwargs["client_ip"] == "127.0.0.0"
    assert kwargs["user_agent"] == "pytest-ua"


@pytest.mark.asyncio
async def test_successful_read_is_minimised_in_opensearch_only(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app, os_log, pg_write = _build_app(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/v1/things", headers={"User-Agent": "pytest-ua"})
    assert resp.status_code == 200

    event = os_log.await_args.args[0]
    assert event.actor["ip_address"] == "127.0.0.0"
    assert event.actor["user_agent"] is None
    pg_write.assert_not_awaited()  # GET is never dual-written


@pytest.mark.asyncio
async def test_missing_user_agent_header_is_tolerated(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app, os_log, pg_write = _build_app(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        # httpx sets a default User-Agent; override it with an empty value
        resp = await client.post("/v1/forbidden", headers={"User-Agent": ""})
    assert resp.status_code == 403
    event = os_log.await_args.args[0]
    assert event.actor["user_agent"] in ("", None)
    assert pg_write.await_args.kwargs["user_agent"] in ("", None)


@pytest.mark.asyncio
async def test_extract_actor_itself_still_returns_the_raw_address():
    """Truncation happens in dispatch, not in _extract_actor (one place, both stores).

    Runs as a coroutine on the suite's event loop (asyncio_mode = "auto"): a nested
    ``asyncio.run`` would close the loop that pytest-asyncio < 1.0 shares with the
    async tests collected after this one.
    """
    middleware = AuditMiddleware.__new__(AuditMiddleware)
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.77"),
        headers={"User-Agent": "pytest"},
        state=SimpleNamespace(),
        url=SimpleNamespace(path="/v1/x"),
    )

    actor = await middleware._extract_actor(request)
    assert actor["ip_address"] == "203.0.113.77"
