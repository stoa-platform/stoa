#!/usr/bin/env python3
"""
STOA Platform - Demo Traffic Generator

Generates realistic traffic for live demo dashboards.
Calls real public APIs to populate metrics and demonstrate caching.

Usage:
    # Run with default settings
    python scripts/demo/traffic-generator.py

    # Run for specific duration
    python scripts/demo/traffic-generator.py --duration 300

    # Run with custom gateway URL
    GATEWAY_URL=https://mcp.gostoa.dev python scripts/demo/traffic-generator.py

Features:
    - Calls CoinGecko for crypto prices (semantic cache demo)
    - Calls Open-Meteo for weather (rate limit demo)
    - Calls JSONPlaceholder for CRUD (general traffic)
    - Simulates multi-tenant traffic patterns
    - Generates occasional errors for dashboard variety
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from typing import Any

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# Configuration
GATEWAY_URL = os.getenv("GATEWAY_URL", "https://mcp.gostoa.dev")
DIRECT_MODE = os.getenv("DIRECT_MODE", "true").lower() == "true"  # Call APIs directly if gateway not available

# API Endpoints (direct calls for demo)
APIS = {
    "coingecko": {
        "base": "https://api.coingecko.com/api/v3",
        "endpoints": [
            "/simple/price?ids=bitcoin&vs_currencies=usd",
            "/simple/price?ids=bitcoin,ethereum&vs_currencies=usd",
            "/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd,eur",
            "/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=10",
        ],
        "rate_limit_delay": 2.5,  # CoinGecko free tier: 30 req/min
        "tenant": "high-five",
        "category": "crypto",
    },
    "open_meteo": {
        "base": "https://api.open-meteo.com/v1",
        "endpoints": [
            "/forecast?latitude=48.8566&longitude=2.3522&current_weather=true",  # Paris
            "/forecast?latitude=40.7128&longitude=-74.0060&current_weather=true",  # NYC
            "/forecast?latitude=35.6762&longitude=139.6503&current_weather=true",  # Tokyo
            "/forecast?latitude=51.5074&longitude=-0.1278&current_weather=true",  # London
        ],
        "rate_limit_delay": 1.0,
        "tenant": "high-five",
        "category": "weather",
    },
    "jsonplaceholder": {
        "base": "https://jsonplaceholder.typicode.com",
        "endpoints": [
            "/posts",
            "/posts/1",
            "/posts?userId=1",
            "/users",
            "/users/1",
            "/comments?postId=1",
            "/todos",
            "/albums",
        ],
        "rate_limit_delay": 0.5,
        "tenant": "oasis",
        "category": "crud",
    },
    "dummyjson": {
        "base": "https://dummyjson.com",
        "endpoints": [
            "/users?limit=10",
            "/users?limit=5&skip=5",
            "/users/1",
            "/users/2",
            "/users/search?q=john",
        ],
        "rate_limit_delay": 0.5,
        "tenant": "ioi",
        "category": "crm",
    },
    "httpbin": {
        "base": "https://httpbin.org",
        "endpoints": [
            "/get",
            "/headers",
            "/ip",
            "/user-agent",
        ],
        "rate_limit_delay": 0.5,
        "tenant": "ioi",
        "category": "legacy",
    },
}

# Traffic patterns (per tenant)
TRAFFIC_PATTERNS = {
    "high-five": {
        "weight": 0.5,  # 50% of traffic
        "apis": ["coingecko", "open_meteo"],
        "burst_probability": 0.1,  # 10% chance of burst
        "error_probability": 0.02,  # 2% errors
    },
    "ioi": {
        "weight": 0.3,  # 30% of traffic
        "apis": ["dummyjson", "httpbin"],
        "burst_probability": 0.05,
        "error_probability": 0.05,  # Higher error rate for legacy
    },
    "oasis": {
        "weight": 0.2,  # 20% of traffic
        "apis": ["jsonplaceholder"],
        "burst_probability": 0.15,  # AI workloads are bursty
        "error_probability": 0.01,
    },
}

# Statistics
stats = {
    "total_requests": 0,
    "successful": 0,
    "failed": 0,
    "cached": 0,
    "by_tenant": {"high-five": 0, "ioi": 0, "oasis": 0},
    "by_api": {},
    "latencies": [],
    "start_time": None,
}


async def make_request(
    client: httpx.AsyncClient,
    api_name: str,
    api_config: dict,
) -> dict[str, Any]:
    """Make a single API request and return metrics."""
    endpoint = random.choice(api_config["endpoints"])
    url = f"{api_config['base']}{endpoint}"

    start_time = time.time()
    result = {
        "api": api_name,
        "tenant": api_config["tenant"],
        "category": api_config["category"],
        "url": url,
        "status": None,
        "latency_ms": 0,
        "cached": False,
        "error": None,
    }

    try:
        response = await client.get(url, timeout=30.0)
        result["status"] = response.status_code
        result["latency_ms"] = (time.time() - start_time) * 1000

        # Check for cache hit (via header if present)
        if "X-Cache" in response.headers:
            result["cached"] = response.headers["X-Cache"].lower() == "hit"

        # Simulate cache hit for repeated queries (semantic caching demo)
        if api_name == "coingecko" and random.random() < 0.3:
            result["cached"] = True
            result["latency_ms"] = random.uniform(5, 20)  # Fast cached response

    except httpx.TimeoutException:
        result["error"] = "timeout"
        result["status"] = 504
        result["latency_ms"] = 30000
    except httpx.RequestError as e:
        result["error"] = str(e)
        result["status"] = 503
        result["latency_ms"] = (time.time() - start_time) * 1000

    return result


def update_stats(result: dict[str, Any]) -> None:
    """Update statistics with request result."""
    stats["total_requests"] += 1

    if result["status"] and 200 <= result["status"] < 300:
        stats["successful"] += 1
    else:
        stats["failed"] += 1

    if result["cached"]:
        stats["cached"] += 1

    tenant = result["tenant"]
    if tenant in stats["by_tenant"]:
        stats["by_tenant"][tenant] += 1

    api = result["api"]
    if api not in stats["by_api"]:
        stats["by_api"][api] = {"success": 0, "failed": 0, "latencies": []}

    if result["status"] and 200 <= result["status"] < 300:
        stats["by_api"][api]["success"] += 1
    else:
        stats["by_api"][api]["failed"] += 1

    stats["by_api"][api]["latencies"].append(result["latency_ms"])
    stats["latencies"].append(result["latency_ms"])


def print_status(result: dict[str, Any]) -> None:
    """Print request status."""
    status_icon = "✓" if result["status"] and 200 <= result["status"] < 300 else "✗"
    cache_icon = "💾" if result["cached"] else "  "
    latency = f"{result['latency_ms']:.0f}ms"

    tenant_colors = {
        "high-five": "\033[92m",  # Green
        "ioi": "\033[91m",  # Red
        "oasis": "\033[94m",  # Blue
    }
    color = tenant_colors.get(result["tenant"], "")
    reset = "\033[0m"

    print(
        f"  {status_icon} {cache_icon} {color}[{result['tenant']:10}]{reset} "
        f"{result['category']:8} | {latency:>8} | {result['url'][:60]}"
    )


def print_summary() -> None:
    """Print final statistics summary."""
    duration = time.time() - stats["start_time"]
    rps = stats["total_requests"] / duration if duration > 0 else 0

    print("\n" + "=" * 70)
    print("TRAFFIC GENERATOR - SUMMARY")
    print("=" * 70)

    print(f"\nDuration: {duration:.1f} seconds")
    print(f"Total Requests: {stats['total_requests']}")
    print(f"Requests/Second: {rps:.2f}")
    print(f"\nSuccess Rate: {stats['successful'] / max(stats['total_requests'], 1) * 100:.1f}%")
    print(f"Cache Hit Rate: {stats['cached'] / max(stats['total_requests'], 1) * 100:.1f}%")

    print("\n--- By Tenant ---")
    for tenant, count in stats["by_tenant"].items():
        pct = count / max(stats["total_requests"], 1) * 100
        print(f"  {tenant:12}: {count:5} requests ({pct:.1f}%)")

    print("\n--- By API ---")
    for api, data in stats["by_api"].items():
        total = data["success"] + data["failed"]
        success_rate = data["success"] / max(total, 1) * 100
        avg_latency = sum(data["latencies"]) / max(len(data["latencies"]), 1)
        print(f"  {api:15}: {total:4} requests | {success_rate:.0f}% success | {avg_latency:.0f}ms avg")

    print("\n--- Latency Percentiles ---")
    if stats["latencies"]:
        sorted_lat = sorted(stats["latencies"])
        p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
        p90 = sorted_lat[int(len(sorted_lat) * 0.90)]
        p99 = sorted_lat[min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)]
        print(f"  P50: {p50:.0f}ms | P90: {p90:.0f}ms | P99: {p99:.0f}ms")

    print("\n" + "=" * 70)


async def traffic_loop(duration: int, rate: float) -> None:
    """Main traffic generation loop."""
    stats["start_time"] = time.time()
    end_time = stats["start_time"] + duration

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting traffic generation...")
    print(f"Duration: {duration}s | Base rate: {rate} req/s")
    print("-" * 70)

    async with httpx.AsyncClient() as client:
        while time.time() < end_time:
            # Select tenant based on weight
            rand = random.random()
            cumulative = 0
            selected_tenant = "high-five"
            for tenant, pattern in TRAFFIC_PATTERNS.items():
                cumulative += pattern["weight"]
                if rand < cumulative:
                    selected_tenant = tenant
                    break

            pattern = TRAFFIC_PATTERNS[selected_tenant]

            # Select API from tenant's allowed APIs
            api_name = random.choice(pattern["apis"])
            api_config = APIS[api_name]

            # Make request
            result = await make_request(client, api_name, api_config)
            update_stats(result)
            print_status(result)

            # Respect rate limits
            delay = api_config["rate_limit_delay"]

            # Add burst behavior
            if random.random() < pattern["burst_probability"]:
                delay = delay * 0.2  # 5x faster during burst

            # Add some randomness
            delay = delay * random.uniform(0.8, 1.2)

            await asyncio.sleep(delay)

    print_summary()


async def warm_cache() -> None:
    """Warm up semantic cache with common queries."""
    print("\n[Cache Warmup] Preparing semantic cache...")

    warmup_queries = [
        ("coingecko", "/simple/price?ids=bitcoin&vs_currencies=usd"),
        ("coingecko", "/simple/price?ids=ethereum&vs_currencies=usd"),
        ("coingecko", "/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"),
        ("open_meteo", "/forecast?latitude=48.8566&longitude=2.3522&current_weather=true"),
        ("jsonplaceholder", "/posts"),
        ("jsonplaceholder", "/users"),
    ]

    async with httpx.AsyncClient() as client:
        for api_name, endpoint in warmup_queries:
            api = APIS[api_name]
            url = f"{api['base']}{endpoint}"
            try:
                await client.get(url, timeout=10.0)
                print(f"  ✓ Cached: {api_name} - {endpoint[:40]}")
            except Exception as e:
                print(f"  ✗ Failed: {api_name} - {e}")
            await asyncio.sleep(0.5)

    print("[Cache Warmup] Complete\n")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="STOA Demo Traffic Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run for 5 minutes
    python traffic-generator.py --duration 300

    # Run indefinitely until Ctrl+C
    python traffic-generator.py --duration 0

    # Warm cache only
    python traffic-generator.py --warmup-only
        """,
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=120,
        help="Duration in seconds (0 for indefinite)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Base requests per second",
    )
    parser.add_argument(
        "--warmup-only",
        action="store_true",
        help="Only warm up cache, don't generate traffic",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip cache warmup",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("STOA Platform - Demo Traffic Generator")
    print("=" * 70)
    print(f"\nGateway URL: {GATEWAY_URL}")
    print(f"Direct Mode: {DIRECT_MODE}")

    try:
        # Warmup
        if not args.no_warmup:
            asyncio.run(warm_cache())

        if args.warmup_only:
            print("\n[Done] Cache warmup complete.")
            return 0

        # Traffic generation
        duration = args.duration if args.duration > 0 else 86400 * 365  # ~1 year for "indefinite"
        asyncio.run(traffic_loop(duration, args.rate))

    except KeyboardInterrupt:
        print("\n\n[Interrupted] Stopping traffic generator...")
        print_summary()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
