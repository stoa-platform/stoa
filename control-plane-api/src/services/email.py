"""Email notification service for STOA Platform"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications"""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "noreply@stoa.cab-i.com")
        self.smtp_tls = os.getenv("SMTP_TLS", "true").lower() == "true"
        self.enabled = os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() == "true"
        self.portal_url = os.getenv("PORTAL_URL", "https://portal.stoa.cab-i.com")

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        """
        Send an email notification.

        Returns True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.info(f"Email notifications disabled. Would send to {to_email}: {subject}")
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = to_email

            # Plain text fallback
            if text_body:
                msg.attach(MIMEText(text_body, "plain"))

            # HTML body
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, to_email, msg.as_string())

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    async def send_key_rotation_notification(
        self,
        to_email: str,
        subscription_id: str,
        api_name: str,
        application_name: str,
        new_api_key: str,
        old_key_expires_at: datetime,
        grace_period_hours: int
    ) -> bool:
        """
        Send API key rotation notification email.

        Includes the new API key (shown only once!) and grace period information.
        """
        subject = f"[STOA] API Key Rotated - {api_name}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1a73e8; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
        .key-box {{ background: #fff; border: 2px solid #1a73e8; border-radius: 4px; padding: 15px; margin: 20px 0; font-family: monospace; word-break: break-all; }}
        .warning {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 15px; margin: 20px 0; }}
        .info {{ background: #d1ecf1; border: 1px solid #17a2b8; border-radius: 4px; padding: 15px; margin: 20px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
        code {{ background: #e9ecef; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">🔐 API Key Rotated</h1>
        </div>
        <div class="content">
            <p>Hello,</p>
            <p>Your API key for <strong>{api_name}</strong> has been successfully rotated.</p>

            <h3>📋 Details</h3>
            <ul>
                <li><strong>API:</strong> {api_name}</li>
                <li><strong>Application:</strong> {application_name}</li>
                <li><strong>Subscription ID:</strong> <code>{subscription_id}</code></li>
            </ul>

            <h3>🔑 Your New API Key</h3>
            <div class="key-box">
                {new_api_key}
            </div>

            <div class="warning">
                <strong>⚠️ Important:</strong> This is the only time you will see this key.
                Please save it securely now!
            </div>

            <div class="info">
                <strong>⏰ Grace Period:</strong><br>
                Your old API key will remain valid for <strong>{grace_period_hours} hours</strong>
                until <strong>{old_key_expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC</strong>.<br><br>
                Please update your applications with the new key before the grace period expires.
            </div>

            <h3>📝 Next Steps</h3>
            <ol>
                <li>Copy and securely store your new API key</li>
                <li>Update your application configuration with the new key</li>
                <li>Test your integration to ensure it works correctly</li>
                <li>The old key will automatically stop working after the grace period</li>
            </ol>

            <p>
                <a href="{self.portal_url}/subscriptions/{subscription_id}"
                   style="display: inline-block; background: #1a73e8; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                    View Subscription
                </a>
            </p>
        </div>
        <div class="footer">
            <p>This is an automated message from the STOA Platform.</p>
            <p>If you did not request this key rotation, please contact support immediately.</p>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
API Key Rotated - {api_name}

Your API key for {api_name} has been successfully rotated.

Details:
- API: {api_name}
- Application: {application_name}
- Subscription ID: {subscription_id}

YOUR NEW API KEY:
{new_api_key}

IMPORTANT: This is the only time you will see this key. Please save it securely now!

GRACE PERIOD:
Your old API key will remain valid for {grace_period_hours} hours until {old_key_expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC.
Please update your applications with the new key before the grace period expires.

Next Steps:
1. Copy and securely store your new API key
2. Update your application configuration with the new key
3. Test your integration to ensure it works correctly
4. The old key will automatically stop working after the grace period

View your subscription: {self.portal_url}/subscriptions/{subscription_id}

---
This is an automated message from the STOA Platform.
If you did not request this key rotation, please contact support immediately.
"""

        return await self.send_email(to_email, subject, html_body, text_body)


# Singleton instance
email_service = EmailService()
