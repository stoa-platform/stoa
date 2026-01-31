#!/usr/bin/env python3
"""mTLS Demo Traffic Generator (CAB-1025).

Generates realistic API traffic from seeded demo clients.
Simulates F5 mTLS termination by sending X-SSL-Client-Cert-SHA256 header.

Usage:
    cd <project-root>
    python scripts/demo-mtls/generate_traffic.py --tps 10 --duration 60

Features:
- Async httpx for high throughput
- Configurable TPS and duration
- Traffic mix: 80% valid, 10% header mismatch, 10% JWT mismatch
- Live stats output (ANSI refresh)
- Graceful shutdown on Ctrl+C
"""

import argparse
import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add project paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_ROOT / "control-plane-api"))
sys.path.insert(0, str(_SCRIPT_DIR))

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mock_jwt import (  # noqa: E402
    generate_demo_token,
    generate_mismatched_token,
    generate_no_cnf_token,
)

# --- Config ---
DEFAULT_GATEWAY_URL = "http://localhost:8080"
DEFAULT_ENDPOINT = "/health"  # Safe default; use /mcp/v1/tools/echo/invoke with gateway
DEFAULT_TPS = 10
DEFAULT_DURATION = 60
DEFAULT_DB_URL = "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa"
CERT_HEADER = "X-SSL-Client-Cert-SHA256"
TENANT_ID = "acme"

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K\r"


@dataclass
class TrafficStats:
    """Real-time traffic statistics."""

    total: int = 0
    success: int = 0
    auth_failed: int = 0
    cert_mismatch: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)
    start_time: float = 0.0

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        recent = self.latencies[-100:]
        return sum(recent) / len(recent) if recent else 0.0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time if self.start_time else 0.0

    @property
    def actual_tps(self) -> float:
        return self.total / self.elapsed if self.elapsed > 1 else 0.0


async def fetch_clients(database_url: str) -> list[dict]:
    """Fetch seeded clients from database."""
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT id, tenant_id, name, certificate_fingerprint, status
                FROM clients
                WHERE tenant_id = :tid AND status = 'active'
                ORDER BY name
            """),
            {"tid": TENANT_ID},
        )
        rows = result.all()

    await engine.dispose()

    return [
        {
            "id": str(row[0]),
            "tenant_id": row[1],
            "name": row[2],
            "certificate_fingerprint": row[3],
            "status": row[4],
        }
        for row in rows
    ]


async def send_request(
    http_client: httpx.AsyncClient,
    endpoint: str,
    token: str,
    cert_fingerprint: str,
    stats: TrafficStats,
) -> None:
    """Send a single request with mTLS simulation."""
    headers = {
        "Authorization": f"Bearer {token}",
        CERT_HEADER: cert_fingerprint,
        "Content-Type": "application/json",
    }

    start = time.monotonic()
    try:
        resp = await http_client.get(endpoint, headers=headers, timeout=5.0)
        latency_ms = (time.monotonic() - start) * 1000
        stats.latencies.append(latency_ms)
        stats.total += 1

        if 200 <= resp.status_code < 300:
            stats.success += 1
        elif resp.status_code == 401:
            stats.auth_failed += 1
            body = resp.text.lower()
            if "certificate binding" in body or "cert" in body:
                stats.cert_mismatch += 1
        else:
            stats.errors += 1
    except Exception:
        stats.total += 1
        stats.errors += 1


def print_stats(stats: TrafficStats, final: bool = False) -> None:
    """Print live stats with ANSI escape codes."""
    prefix = f"{BOLD}{'FINAL' if final else 'LIVE '}{RESET}"
    success_color = GREEN if stats.success_rate > 80 else YELLOW if stats.success_rate > 50 else RED

    lines = [
        f"\n{BOLD}{'=' * 50}{RESET}",
        f"  {prefix} mTLS Demo Traffic — {stats.elapsed:.0f}s elapsed",
        f"{'=' * 50}",
        f"  {CYAN}Total{RESET}        {stats.total:>8}   ({stats.actual_tps:.1f} req/s)",
        f"  {GREEN}Success{RESET}      {stats.success:>8}   ({success_color}{stats.success_rate:.1f}%{RESET})",
        f"  {YELLOW}Auth 401{RESET}     {stats.auth_failed:>8}",
        f"  {RED}Cert Mismatch{RESET} {stats.cert_mismatch:>7}",
        f"  {RED}Errors 5xx{RESET}   {stats.errors:>8}",
        f"  {CYAN}Avg Latency{RESET}  {stats.avg_latency_ms:>7.1f} ms",
        f"{'=' * 50}",
    ]

    if not final:
        # Move cursor up to overwrite previous stats
        sys.stdout.write(f"\033[{len(lines)}A")

    for line in lines:
        sys.stdout.write(f"{CLEAR_LINE}{line}\n")
    sys.stdout.flush()


async def traffic_loop(
    clients: list[dict],
    tps: int,
    duration: int,
    gateway_url: str,
    endpoint: str,
    stats: TrafficStats,
) -> None:
    """Main traffic generation loop."""
    interval = 1.0 / tps
    end_time = time.monotonic() + duration
    stats.start_time = time.monotonic()
    pending: set[asyncio.Task] = set()

    async with httpx.AsyncClient(base_url=gateway_url) as http_client:
        while time.monotonic() < end_time:
            client_data = random.choice(clients)
            roll = random.random()

            if roll < 0.80:
                # Valid request — matching JWT cnf + header
                token = generate_demo_token(
                    client_data["id"],
                    client_data["tenant_id"],
                    client_data["certificate_fingerprint"],
                )
                fingerprint = client_data["certificate_fingerprint"]
            elif roll < 0.90:
                # Header mismatch — correct JWT, wrong header
                token = generate_demo_token(
                    client_data["id"],
                    client_data["tenant_id"],
                    client_data["certificate_fingerprint"],
                )
                fingerprint = "00" * 32
            else:
                # JWT mismatch — wrong cnf in JWT, correct header
                token = generate_mismatched_token(
                    client_data["id"],
                    client_data["tenant_id"],
                )
                fingerprint = client_data["certificate_fingerprint"]

            task = asyncio.create_task(
                send_request(http_client, endpoint, token, fingerprint, stats)
            )
            pending.add(task)
            task.add_done_callback(pending.discard)

            await asyncio.sleep(interval)

        # Drain pending requests
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def main(
    tps: int,
    duration: int,
    gateway_url: str,
    endpoint: str,
    database_url: str,
) -> None:
    """Main entry point."""
    print(f"\n{BOLD}{GREEN}mTLS Demo Traffic Generator (CAB-1025){RESET}")
    print(f"  Gateway:  {gateway_url}")
    print(f"  Endpoint: {endpoint}")
    print(f"  TPS:      {tps}")
    print(f"  Duration: {duration}s\n")

    # Fetch clients
    print("Fetching clients from database...")
    try:
        clients = await fetch_clients(database_url)
    except Exception as e:
        print(f"{RED}DB error: {e}{RESET}")
        print(f"{YELLOW}Falling back to 10 mock clients...{RESET}")
        import secrets

        clients = [
            {
                "id": f"mock-client-{i:03d}",
                "tenant_id": TENANT_ID,
                "name": f"mock-{i:03d}",
                "certificate_fingerprint": secrets.token_hex(32),
                "status": "active",
            }
            for i in range(10)
        ]

    print(f"Loaded {GREEN}{len(clients)}{RESET} active clients\n")

    stats = TrafficStats()

    # Print initial empty stats block
    print_stats(stats)

    # Stats display task
    async def display_loop():
        while True:
            await asyncio.sleep(0.5)
            print_stats(stats)

    display_task = asyncio.create_task(display_loop())

    try:
        await traffic_loop(clients, tps, duration, gateway_url, endpoint, stats)
    except asyncio.CancelledError:
        pass
    finally:
        display_task.cancel()
        try:
            await display_task
        except asyncio.CancelledError:
            pass

    print_stats(stats, final=True)
    print(f"\n{GREEN}Demo complete!{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="mTLS Demo Traffic Generator (CAB-1025)")
    parser.add_argument("--tps", type=int, default=DEFAULT_TPS, help="Transactions per second")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help="Duration in seconds")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL, help="MCP Gateway URL")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Target endpoint")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="Database URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.tps, args.duration, args.gateway_url, args.endpoint, args.db_url))
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user{RESET}")
