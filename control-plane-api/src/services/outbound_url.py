"""Guard for server-side requests to user-supplied URLs (SSRF).

The control plane runs next to internal services (Vault, Keycloak, the
Kubernetes API, cloud metadata endpoints). A URL taken from a request body
must only reach public http(s) addresses, on every hop, redirects included.

Residual risk: DNS can change between this check and the connection (DNS
rebinding). Every hop is checked again, which narrows but does not close
that window.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_PORTS = {"http": 80, "https": 443}


class UnsafeOutboundURLError(ValueError):
    """The URL must not be fetched by the server."""


def _is_public_ip(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split("%", 1)[0])  # drop an IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # is_global excludes private, loopback, link-local, shared (100.64/10),
    # reserved and unspecified ranges.
    return ip.is_global and not ip.is_multicast


async def _resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def ensure_public_http_url(url: str) -> None:
    """Raise UnsafeOutboundURLError unless every address of the URL host is public."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeOutboundURLError("only http and https URLs are allowed")
    host = parts.hostname
    if not host:
        raise UnsafeOutboundURLError("URL has no host")
    if parts.username or parts.password:
        raise UnsafeOutboundURLError("URL must not carry credentials")
    try:
        port = parts.port or _DEFAULT_PORTS[scheme]
    except ValueError as exc:
        raise UnsafeOutboundURLError("invalid port") from exc

    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = await _resolve(host, port)
        except OSError as exc:
            raise UnsafeOutboundURLError("host does not resolve") from exc

    if not addresses or not all(_is_public_ip(address) for address in addresses):
        raise UnsafeOutboundURLError("URL targets a non-public address")


async def guard_outbound_request(request: httpx.Request) -> None:
    """httpx request hook: checks the first request and every redirect hop."""
    await ensure_public_http_url(str(request.url))
