import resend
import structlog
from typing import List

from app.core.config import settings
from app.core.email import EmailMessage, EmailResult

logger = structlog.get_logger()


class ResendEmailSender:
    """Resend email sender implementation using official SDK."""

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.from_email = settings.RESEND_FROM_EMAIL
        self.from_name = settings.RESEND_FROM_NAME
        if self.api_key:
            resend.api_key = self.api_key

    def send(self, message: EmailMessage) -> EmailResult:
        if not self.api_key:
            logger.warning("RESEND_API_KEY_not_configured")
            return EmailResult(status="skipped", error="Resend API key not configured")

        try:
            params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [message.to],
                "subject": message.subject,
                "html": message.html,
            }
            if message.text:
                params["text"] = message.text
            if message.reply_to:
                params["reply_to"] = message.reply_to

            result = resend.Emails.send(params)
            logger.info("email_sent", to=message.to, message_id=result.get("id"))
            return EmailResult(
                status="sent",
                message_id=result.get("id"),
            )

        except Exception as e:
            logger.error("email_send_error", error=str(e), to=message.to)
            return EmailResult(status="failed", error=str(e))

    def send_bulk(self, messages: List[EmailMessage]) -> List[EmailResult]:
        if not self.api_key:
            logger.warning("RESEND_API_KEY_not_configured")
            return [
                EmailResult(status="skipped", error="Resend API key not configured")
                for _ in messages
            ]

        results = []
        for msg in messages:
            results.append(self.send(msg))
        return results
