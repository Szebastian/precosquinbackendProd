import base64 as b64
import requests
import structlog
from typing import List

from app.core.config import settings
from app.core.email import EmailMessage, EmailResult

logger = structlog.get_logger()

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailSender:
    """Resend email sender using direct API calls for full CID attachment control."""

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.from_email = settings.RESEND_FROM_EMAIL
        self.from_name = settings.RESEND_FROM_NAME

    def send(self, message: EmailMessage) -> EmailResult:
        if not self.api_key:
            logger.warning("RESEND_API_KEY_not_configured")
            return EmailResult(status="skipped", error="Resend API key not configured")

        try:
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [message.to],
                "subject": message.subject,
                "html": message.html,
            }
            if message.text:
                payload["text"] = message.text
            if message.reply_to:
                payload["reply_to"] = message.reply_to

            if message.attachments:
                payload["attachments"] = []
                for att in message.attachments:
                    payload["attachments"].append({
                        "content": b64.b64encode(att.content).decode("utf-8"),
                        "filename": att.filename,
                        "content_type": att.content_type,
                        "content_id": att.content_id,
                    })

            resp = requests.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                logger.info("email_sent", to=message.to, message_id=data.get("id"))
                return EmailResult(status="sent", message_id=data.get("id"))
            else:
                error_detail = resp.text
                logger.error("email_send_failed", status=resp.status_code, response=error_detail, to=message.to)
                return EmailResult(status="failed", error=f"HTTP {resp.status_code}: {error_detail}")

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
