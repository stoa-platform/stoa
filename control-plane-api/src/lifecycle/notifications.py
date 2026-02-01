"""
Tenant Lifecycle Notification Service
CAB-409: Email notifications for demo trial lifecycle

5 notification types:
  - warning_3d:  "Your trial expires in 3 days" (J+11)
  - urgent_1d:   "Last chance - expires tomorrow" (J+13)
  - expired:     "Trial expired - read-only mode" (J+14)
  - grace:       "Data will be deleted in 7 days" (J+15)
  - final:       "Deletion scheduled tomorrow" (J+21)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import NotificationType, TenantLifecycleNotification
from .metrics import lifecycle_metrics

logger = logging.getLogger("stoa.lifecycle.notifications")


# ─── Email Templates ──────────────────────────────────────────────────────────

TEMPLATES: dict[NotificationType, dict] = {
    NotificationType.WARNING_3D: {
        "subject": "Your STOA trial expires in {days_left} days",
        "body": """Hi there,

Your STOA Platform trial for **{tenant_name}** expires on **{expires_at}**.

You have **{days_left} days** remaining to explore the platform.

**What you can do:**
- **Extend your trial** for 7 more days (one-time): {portal_url}/settings/billing
- **Upgrade to Pro/Enterprise**: {portal_url}/upgrade
- **Export your data**: {portal_url}/settings/export

Questions? Reply to this email or reach us at support@gostoa.dev.

-- The STOA Team
""",
    },
    NotificationType.URGENT_1D: {
        "subject": "Last day! Your STOA trial expires tomorrow",
        "body": """Hi there,

This is your **last chance** -- your STOA trial for **{tenant_name}** expires **tomorrow**.

After expiration, your tenant will switch to **read-only mode**.

**Act now:**
- [Extend for 7 days]({portal_url}/settings/billing) (free, one-time)
- [Upgrade to keep full access]({portal_url}/upgrade)

Don't lose your configuration and API subscriptions!

-- The STOA Team
""",
    },
    NotificationType.EXPIRED: {
        "subject": "Your STOA trial has expired",
        "body": """Hi there,

Your STOA trial for **{tenant_name}** has **expired**.

**What this means:**
- Your tenant is now in **read-only mode**
- API calls will return `403 Forbidden`
- You can still view your dashboards and configuration
- Your data is preserved for **7 more days**

**To restore full access:**
- [Upgrade to a paid plan]({portal_url}/upgrade)
- Contact sales@gostoa.dev for Enterprise pricing

-- The STOA Team
""",
    },
    NotificationType.GRACE: {
        "subject": "Your STOA data will be deleted in 7 days",
        "body": """Hi there,

Your STOA trial for **{tenant_name}** expired yesterday.

**Your data will be permanently deleted in 7 days**, including:
- API configurations
- Subscriptions and API keys
- Usage metrics and logs
- Kubernetes namespace

**To preserve your data:**
- [Upgrade now]({portal_url}/upgrade) -- your data will be migrated seamlessly
- [Export your data]({portal_url}/settings/export) before it's gone

Need more time? Contact us at support@gostoa.dev.

-- The STOA Team
""",
    },
    NotificationType.FINAL: {
        "subject": "Final notice: STOA data deletion tomorrow",
        "body": """Hi there,

This is your **final notice**. All data for **{tenant_name}** will be **permanently deleted tomorrow**.

This action is **irreversible**. After deletion:
- All API configurations will be removed
- Kubernetes namespace will be destroyed
- API keys will be revoked
- Audit logs will be archived (30-day retention)

**Last chance to save your work:**
- [Upgrade now]({portal_url}/upgrade)
- Email support@gostoa.dev for emergency extension

-- The STOA Team
""",
    },
}


# ─── Notification Service ─────────────────────────────────────────────────────

class NotificationService:
    """Sends lifecycle notifications, ensuring each type is sent only once per tenant."""

    PORTAL_URL = "https://demo.gostoa.dev"

    def __init__(self, db: AsyncSession, email_sender=None):
        self.db = db
        self.email_sender = email_sender

    async def send_if_not_sent(
        self,
        tenant_id: str,
        notification_type: NotificationType,
        recipient_email: str,
        context: dict,
    ) -> bool:
        """Send a notification if not already sent. Returns True if sent."""
        already_sent = await self._was_sent(tenant_id, notification_type)
        if already_sent:
            return False

        template = TEMPLATES[notification_type]
        render_context = {**context, "portal_url": self.PORTAL_URL}
        subject = template["subject"].format(**render_context)
        body = template["body"].format(**render_context)

        success = True
        error_message = None
        try:
            await self._send_email(
                to=recipient_email,
                subject=subject,
                body=body,
                notification_type=notification_type.value,
                tenant_id=tenant_id,
            )
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Failed to send {notification_type.value} to {recipient_email}: {e}")

        await self._record_notification(
            tenant_id=tenant_id,
            notification_type=notification_type,
            recipient_email=recipient_email,
            success=success,
            error_message=error_message,
        )

        if success:
            lifecycle_metrics.notifications_sent_total.labels(
                type=notification_type.value,
                channel="email",
            ).inc()
            logger.info(f"Sent {notification_type.value} to {recipient_email} for tenant {tenant_id}")

        return success

    async def _was_sent(self, tenant_id: str, notification_type: NotificationType) -> bool:
        """Check if notification was already sent (send-once via ORM)."""
        stmt = select(TenantLifecycleNotification).where(
            and_(
                TenantLifecycleNotification.tenant_id == tenant_id,
                TenantLifecycleNotification.notification_type == notification_type.value,
                TenantLifecycleNotification.success == True,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _record_notification(
        self,
        tenant_id: str,
        notification_type: NotificationType,
        recipient_email: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record notification in database."""
        record = TenantLifecycleNotification(
            tenant_id=tenant_id,
            notification_type=notification_type.value,
            recipient_email=recipient_email,
            success=success,
            error_message=error_message,
        )
        self.db.add(record)

    async def _send_email(self, to: str, subject: str, body: str, notification_type: str, tenant_id: str) -> None:
        """
        MVP: Log-only. Production: plug SES/SMTP/Resend here.
        Interface contract: (to, subject, body) -> bool
        """
        if self.email_sender:
            await self.email_sender.send(to=to, subject=subject, body=body)
        else:
            # COUNCIL #5: Log-only for MVP, do NOT log body (may contain PII)
            logger.info(
                "NOTIFICATION_SENT",
                extra={
                    "notification_type": notification_type,
                    "tenant_id": tenant_id,
                    "to": to,
                    "subject": subject,
                },
            )
