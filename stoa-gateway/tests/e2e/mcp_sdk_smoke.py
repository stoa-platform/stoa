#!/usr/bin/env python3
"""Reference-client smoke against a running STOA Gateway (CAB-2115).

Drives the *official* Python MCP SDK (`mcp>=1.0`), which uses the same
Pydantic-strict schema family that powers Anthropic's Toolbox — i.e. the
validator that rejected the connector in CAB-2112 with

    ValidationError: capabilities.experimental.transports
    Input should be a valid dictionary [type=dict_type]

If any of the past three regressions (CAB-2106 Accept / CAB-2109
public_methods / CAB-2112 initialize shape) had been re-introduced, this
script would have failed before we shipped them to prod.

## Exit codes

- ``0``  every stage green.
- ``1``  a stage failed — prints the underlying error, the full response
         body, and the stage index so CI logs remain diagnosable.

## Stages

1. Streamable-HTTP transport is used by ``claude.ai``'s Anthropic backend
   and by Claude Code with ``--transport http``.
2. Each discovery / metadata method in the MCP 2025-11-25 capability set
   is round-tripped against the server. Unexpected shape anywhere → SDK
   Pydantic error → test failure.
3. ``tools/list`` must return at least the built-in ``stoa_*`` tools; a
   zero-length list signals a tool registry or boot regression.

## Usage

    STOA_GATEWAY_URL=http://127.0.0.1:8080/mcp/sse  # pre-merge default
    STOA_GATEWAY_URL=https://mcp.gostoa.dev/mcp/sse # post-deploy probe
    python mcp_sdk_smoke.py

``STOA_GATEWAY_BEARER`` (optional) is attached as ``Authorization: Bearer``
on post-deploy runs that want to exercise authenticated paths such as
``tools/call``; omit it for the capability-negotiation-only gate.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


DEFAULT_URL = "http://127.0.0.1:8080/mcp/sse"


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str = ""
    data: Any = field(default=None, repr=False)


async def run_smoke(
    url: str, bearer: str | None, call_tool: bool
) -> list[StageResult]:
    """Execute every stage and return their results. Never raises."""
    results: list[StageResult] = []
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else None

    try:
        async with streamablehttp_client(url, headers=headers) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. initialize — locks CAB-2112 (experimental shape) + CAB-2106 (Accept).
                init = await session.initialize()
                results.append(
                    StageResult(
                        "initialize",
                        True,
                        f"protocol={init.protocolVersion} "
                        f"server={init.serverInfo.name}/{init.serverInfo.version}",
                        init,
                    )
                )

                # 2. Discovery surface — locks CAB-2109 (public_methods).
                tools = await session.list_tools()
                results.append(
                    StageResult(
                        "tools/list",
                        len(tools.tools) > 0,
                        f"{len(tools.tools)} tools",
                        tools,
                    )
                )

                resources = await session.list_resources()
                results.append(
                    StageResult(
                        "resources/list",
                        True,
                        f"{len(resources.resources)} resources",
                        resources,
                    )
                )

                templates = await session.list_resource_templates()
                results.append(
                    StageResult(
                        "resources/templates/list",
                        True,
                        f"{len(templates.resourceTemplates)} templates",
                        templates,
                    )
                )

                prompts = await session.list_prompts()
                results.append(
                    StageResult(
                        "prompts/list",
                        True,
                        f"{len(prompts.prompts)} prompts",
                        prompts,
                    )
                )

                ping = await session.send_ping()
                results.append(StageResult("ping", True, str(ping), ping))

                logging_result = await session.set_logging_level("info")
                results.append(
                    StageResult(
                        "logging/setLevel",
                        True,
                        "level=info accepted",
                        logging_result,
                    )
                )

                # 3. One concrete tool invocation (no external deps).
                #    `stoa_platform_info` is a self-describing health tool.
                #    Gated on `call_tool=True` because anonymous tools/call
                #    must 401 per the CAB-2109 contract; the pre-merge gate
                #    exercises discovery only and leaves tool invocation to
                #    the post-deploy probe (which attaches a Bearer token).
                if call_tool:
                    info = await session.call_tool(
                        "stoa_platform_info", arguments={}
                    )
                    results.append(
                        StageResult(
                            "tools/call:stoa_platform_info",
                            not info.isError,
                            "ok" if not info.isError else "tool returned isError",
                            info,
                        )
                    )

    except Exception as exc:  # noqa: BLE001
        results.append(
            StageResult(
                "transport-or-handshake",
                False,
                f"{type(exc).__name__}: {exc}",
                traceback.format_exc(),
            )
        )

    return results


def _format(results: list[StageResult]) -> tuple[bool, str]:
    lines = []
    ok = all(r.ok for r in results) and bool(results)
    for r in results:
        icon = "✓" if r.ok else "✗"
        lines.append(f"  {icon} {r.name}: {r.detail}")
    return ok, "\n".join(lines)


async def _amain() -> int:
    url = os.environ.get("STOA_GATEWAY_URL", DEFAULT_URL)
    bearer = os.environ.get("STOA_GATEWAY_BEARER") or None
    call_tool = os.environ.get("STOA_SMOKE_CALL_TOOL", "1") != "0"

    print(f"MCP SDK smoke → {url}  (bearer={'yes' if bearer else 'no'})")

    results = await run_smoke(url, bearer, call_tool=call_tool)

    ok, body = _format(results)
    print(body)
    if ok:
        print(f"MCP SDK smoke PASS ({len(results)} stages)")
        return 0

    # Verbose failure report — include the traceback we captured plus every
    # stage that returned ok=False so CI logs explain *why*.
    print("\nMCP SDK smoke FAIL")
    for r in results:
        if not r.ok:
            print(f"\n--- {r.name} ---")
            print(r.detail)
            if r.data and isinstance(r.data, str):
                print(r.data)
    return 1


def main() -> None:
    rc = asyncio.run(_amain())
    sys.exit(rc)


if __name__ == "__main__":
    main()
