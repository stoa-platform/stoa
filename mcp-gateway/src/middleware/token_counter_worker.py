# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Token Counter Background Worker (CAB-881).

Consumes TokenPayload from the async queue and emits Prometheus metrics.
Runs as an asyncio background task — zero impact on request latency.

MVP: in-memory asyncio.Queue
Future (CAB-459): Redis Streams for multi-instance deployments.
"""

import asyncio

import structlog

from .token_counter import (
    TokenPayload,
    count_tokens,
    get_token_queue,
    TOKENS_TOTAL,
    TOKENS_BY_TENANT,
    _hash_for_log,
)

logger = structlog.get_logger(__name__)


class TokenCounterWorker:
    """Background worker that consumes queued payloads and counts tokens.

    Lifecycle managed via start()/stop() in the application lifespan.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("token_counter_worker_started")

    async def stop(self) -> None:
        """Stop the background consumer task gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("token_counter_worker_stopped")

    async def _consume_loop(self) -> None:
        """Main consumer loop — drains queue and records metrics."""
        queue = get_token_queue()

        while self._running:
            try:
                payload: TokenPayload = await asyncio.wait_for(
                    queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                self._process(payload)
            except Exception:
                logger.exception(
                    "token_counter_process_error",
                    tool_name=payload.tool_name,
                    direction=payload.direction,
                )

    def _process(self, payload: TokenPayload) -> None:
        """Count tokens and record Prometheus metrics."""
        token_count = count_tokens(payload.body)

        # Public metric
        TOKENS_TOTAL.labels(
            tool_name=payload.tool_name,
            direction=payload.direction,
        ).inc(token_count)

        # Internal metric (tenant-scoped)
        TOKENS_BY_TENANT.labels(
            tenant_id=payload.tenant_id,
            tool_name=payload.tool_name,
        ).inc(token_count)

        logger.debug(
            "token_counted",
            tool_name=payload.tool_name,
            direction=payload.direction,
            tokens=token_count,
            tenant_hash=_hash_for_log(payload.tenant_id),
        )


# Singleton instance
token_counter_worker = TokenCounterWorker()
