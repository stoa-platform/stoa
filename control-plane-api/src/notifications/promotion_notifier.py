"""Slack notifier for promotion lifecycle events (CAB-1706).

Reuses the same Slack transport as deployment_notifier (Bot API or webhook).
Sends notifications when promotions need approval, are approved, or rolled back.
"""

import logging
from typing import Any

from ..config import settings
from .deployment_notifier import _post_bot, _post_webhook
from .templates import format_message

logger = logging.getLogger(__name__)


async def notify_promotion_event(event_type: str, payload: dict[str, Any]) -> None:
    """Format and dispatch a Slack notification for a promotion event.

    Non-blocking: errors are logged as warnings, never raised.
    """
    text = format_message(event_type, payload)
    if text is None:
        return

    try:
        if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
            await _post_bot(text)
        elif settings.SLACK_WEBHOOK_URL:
            await _post_webhook(text)
        else:
            logger.debug("Slack not configured — promotion event not notified: %s", event_type)
    except Exception as exc:
        logger.warning("Failed to send promotion Slack notification: %s", exc)
