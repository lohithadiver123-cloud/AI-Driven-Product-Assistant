"""Modular Email Service supporting SMTP and Development Mode."""
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
import aiosmtplib

from app.config import get_settings

logger = logging.getLogger("ai_product_assistant.email")

# In-memory development outbox for local developer convenience
dev_email_outbox: List[Dict[str, str]] = []


class EmailService:
    """Service to send transactional emails (verification, password reset)."""

    def __init__(self):
        self.settings = get_settings()

    async def send_verification_email(self, to_email: str, user_name: str, token: str) -> bool:
        """Send an account email verification message."""
        verification_link = f"{self.settings.FRONTEND_URL}/verify-email?token={token}"
        subject = f"Verify your {self.settings.APP_NAME} account"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; color: #f9fafb; margin: 0; padding: 20px; }}
            .card {{ max-width: 540px; margin: 0 auto; background: #111827; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 32px; }}
            .btn {{ display: inline-block; background: #6366f1; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; margin: 20px 0; }}
            .footer {{ font-size: 12px; color: #6b7280; margin-top: 24px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 16px; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h2>Welcome to {self.settings.APP_NAME}, {user_name}!</h2>
            <p>Thank you for creating your product workspace. Please verify your email address to confirm your account.</p>
            <p style="text-align: center;">
              <a href="{verification_link}" class="btn">Verify Email Address</a>
            </p>
            <p style="font-size: 13px; color: #9ca3af;">Or copy and paste this link in your browser:<br><code>{verification_link}</code></p>
            <div class="footer">
              <p>This verification link will expire in {self.settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours. If you did not create this account, please ignore this email.</p>
            </div>
          </div>
        </body>
        </html>
        """

        text_content = f"""
        Welcome to {self.settings.APP_NAME}, {user_name}!
        
        Please verify your email address by opening the following link:
        {verification_link}
        
        This link will expire in {self.settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.
        """

        return await self._dispatch_email(to_email, subject, html_content, text_content, link_type="VERIFICATION", link=verification_link)

    async def send_password_reset_email(self, to_email: str, user_name: str, token: str) -> bool:
        """Send a single-use password reset link."""
        reset_link = f"{self.settings.FRONTEND_URL}/reset-password?token={token}"
        subject = f"Reset your {self.settings.APP_NAME} password"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; color: #f9fafb; margin: 0; padding: 20px; }}
            .card {{ max-width: 540px; margin: 0 auto; background: #111827; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 32px; }}
            .btn {{ display: inline-block; background: #ef4444; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; margin: 20px 0; }}
            .footer {{ font-size: 12px; color: #6b7280; margin-top: 24px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 16px; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h2>Password Reset Request</h2>
            <p>Hello {user_name},</p>
            <p>We received a request to reset your password for {self.settings.APP_NAME}. Click the button below to choose a new password:</p>
            <p style="text-align: center;">
              <a href="{reset_link}" class="btn">Reset Password</a>
            </p>
            <p style="font-size: 13px; color: #9ca3af;">Or copy and paste this link in your browser:<br><code>{reset_link}</code></p>
            <div class="footer">
              <p>This single-use link will expire in {self.settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. If you did not request a password reset, you can safely ignore this email.</p>
            </div>
          </div>
        </body>
        </html>
        """

        text_content = f"""
        Hello {user_name},
        
        We received a request to reset your password for {self.settings.APP_NAME}.
        Open this link to choose a new password:
        {reset_link}
        
        This link will expire in {self.settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.
        If you did not request this, please ignore this email.
        """

        return await self._dispatch_email(to_email, subject, html_content, text_content, link_type="PASSWORD_RESET", link=reset_link)

    async def _dispatch_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
        link_type: str = "NOTIFICATION",
        link: Optional[str] = None,
    ) -> bool:
        """Dispatch email via real SMTP if configured, else log to development outbox."""
        settings = get_settings()

        # Development Mode: No SMTP configured
        if not settings.SMTP_HOST or not settings.SMTP_HOST.strip():
            logger.info("[DEV EMAIL DISPATCHER] To: %s | Subject: '%s' | Action: %s", to_email, subject, link_type)
            if link:
                logger.info("[DEV EMAIL LINK]: %s", link)
            dev_email_outbox.append({
                "to": to_email,
                "subject": subject,
                "type": link_type,
                "link": link or "",
            })
            return True

        # Real SMTP Delivery
        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            message["To"] = to_email

            part1 = MIMEText(text_content, "plain")
            part2 = MIMEText(html_content, "html")
            message.attach(part1)
            message.attach(part2)

            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME,
                password=settings.SMTP_PASSWORD,
                use_tls=False,
                start_tls=settings.SMTP_USE_TLS,
                timeout=10,
            )
            logger.info("Successfully sent email to %s via SMTP %s", to_email, settings.SMTP_HOST)
            return True
        except Exception as exc:
            logger.error("Failed to deliver email via SMTP: %s", exc)
            return False


email_service = EmailService()
