"""Backend Seeder — multi-persona mock API for traffic seed (CAB-1976).

Simulates 5 different API backends with varied behaviors:
  /petstore/*    — fast (5-20ms), occasional 404
  /payments/*    — medium (50-200ms), occasional 500
  /analytics/*   — slow (200-800ms), large payloads
  /auth/*        — fast but 30% 401/403
  /legacy/*      — unreliable (20% timeout, 10% 500)
  /health        — always 200
"""

import asyncio
import json
import random
import time

from aiohttp import web


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "backend-seeder"})


async def petstore(request: web.Request) -> web.Response:
    await asyncio.sleep(random.uniform(0.005, 0.020))
    path = request.match_info.get("path", "")
    if random.random() < 0.1:
        return web.json_response({"error": "Pet not found"}, status=404)
    pets = [
        {"id": i, "name": f"Pet-{i}", "species": random.choice(["dog", "cat", "bird"])}
        for i in range(random.randint(1, 5))
    ]
    return web.json_response({"pets": pets, "path": path})


async def payments(request: web.Request) -> web.Response:
    await asyncio.sleep(random.uniform(0.050, 0.200))
    if random.random() < 0.15:
        return web.json_response(
            {"error": "Payment processing failed", "code": "INSUFFICIENT_FUNDS"},
            status=500,
        )
    return web.json_response(
        {
            "transaction_id": f"txn-{int(time.time()*1000)}",
            "amount": round(random.uniform(10, 500), 2),
            "currency": "EUR",
            "status": "completed",
        }
    )


async def analytics(request: web.Request) -> web.Response:
    await asyncio.sleep(random.uniform(0.200, 0.800))
    rows = [
        {"date": f"2026-04-0{d}", "views": random.randint(100, 10000), "conversions": random.randint(1, 100)}
        for d in range(1, 8)
    ]
    return web.json_response({"report": rows, "generated_at": time.time()})


async def auth_endpoint(request: web.Request) -> web.Response:
    await asyncio.sleep(random.uniform(0.005, 0.015))
    r = random.random()
    if r < 0.15:
        return web.json_response({"error": "Invalid token"}, status=401)
    if r < 0.30:
        return web.json_response({"error": "Forbidden"}, status=403)
    return web.json_response({"user_id": "user-42", "roles": ["read", "write"]})


async def legacy(request: web.Request) -> web.Response:
    r = random.random()
    if r < 0.20:
        await asyncio.sleep(5.0)  # timeout
        return web.json_response({"error": "Timeout"}, status=504)
    if r < 0.30:
        return web.json_response({"error": "Internal error"}, status=500)
    await asyncio.sleep(random.uniform(0.050, 0.300))
    return web.json_response({"data": "legacy_response", "ts": time.time()})


app = web.Application()
app.router.add_get("/health", health)
app.router.add_route("*", "/petstore/{path:.*}", petstore)
app.router.add_route("*", "/payments/{path:.*}", payments)
app.router.add_route("*", "/analytics/{path:.*}", analytics)
app.router.add_route("*", "/auth/{path:.*}", auth_endpoint)
app.router.add_route("*", "/legacy/{path:.*}", legacy)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=9999)
