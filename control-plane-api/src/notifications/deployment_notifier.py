"""Slack notifier for deployment lifecycle events (CAB-1413).

Sends formatted Slack messages via incoming webhook or Bot API.
Infrastructure (bot token + webhook URL) is already in K8s Secret from CAB-1398.

Priority:
  1. SLACK_BOT_TOKEN + SLACK_CHANNEL_ID  (Bot API, supports threading)
  2. SLACK_WEBHOOK_URL                   (incoming webhook, simpler)
  3. No credentials configured           (log warning, no-op)
"""

import logging
from typing import Any

import httpx

from ..config import settings
from .templates import format_message

logger = logging.getLogger(__name__)

_SLACK_API_POST = "https://slack.com/api/chat.postMessage"


async def notify_deployment_event(event_type: str, payload: dict[str, Any]) -> None:
    """Format and dispatch a Slack notification for a deployment event.

    Non-blocking: errors are logged as warnings, never raised.
    """
    text = format_message(event_type, payload)
    if text is None:
        return  # unrecognised event type — skip silently

    try:
        if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
            await _post_bot(text)
        elif settings.SLACK_WEBHOOK_URL:
            await _post_webhook(text)
        else:
            logger.debug("Slack not configured — deployment event not notified: %s", event_type)
    except Exception as exc:
        logger.warning("Failed to send deployment Slack notification: %s", exc)


async def _post_webhook(text: str) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(settings.SLACK_WEBHOOK_URL, json={"text": text})
        resp.raise_for_status()


async def _post_bot(text: str) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(
            _SLACK_API_POST,
            headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"},
            json={"channel": settings.SLACK_CHANNEL_ID, "text": text},
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Slack Bot API error: %s", data.get("error", "unknown"))
