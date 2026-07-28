import httpx
import structlog
from typing import List, Optional

from app.core.config import settings
from app.core.email import EmailMessage, EmailResult

logger = structlog.get_logger()

RESEND_API_URL = "https://api.resend.com"


class ResendEmailSender:
    """Resend email sender implementation."""

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.from_email = settings.RESEND_FROM_EMAIL
        self.from_name = settings.RESEND_FROM_NAME

    @staticmethod
    def _text_to_html(text: str) -> str:
        """Convert plain text to HTML preserving paragraphs and line breaks."""
        import html
        escaped = html.escape(text)
        paragraphs = escaped.split("\n\n")
        html_parts = []
        for p in paragraphs:
            lines = p.strip().split("\n")
            html_parts.append("<p>" + "<br>".join(lines) + "</p>")
        return "\n".join(html_parts)

    @staticmethod
    def _build_email_html(body: str, logo_url: Optional[str] = None) -> str:
        """Wrap body in a branded HTML email template with optional logo."""
        import html as html_mod
        safe_body = body if "<p>" in body or "<br" in body else ResendEmailSender._text_to_html(body)

        logo_section = ""
        if logo_url:
            logo_section = f"""
            <div style="text-align:center; padding:24px 0 8px 0; border-top:1px solid #e5e7eb; margin-top:32px;">
              <img src="{html_mod.escape(logo_url)}" alt="Logo" style="max-width:180px; height:auto; display:inline-block;" />
            </div>"""

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 24px;background:#ffffff;">
    <div style="font-size:15px;line-height:1.6;color:#1f2937;">
      {safe_body}
    </div>
    {logo_section}
    <div style="text-align:center;font-size:11px;color:#9ca3af;padding-top:16px;">
      Precosquin - Festival Provincial de Folklore · Puerto Pirámides, Chubut
    </div>
  </div>
</body>
</html>"""

    def send(self, message: EmailMessage) -> EmailResult:
        if not self.api_key:
            logger.warning("RESEND_API_KEY_not_configured")
            return EmailResult(status="skipped", error="Resend API key not configured")

        try:
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [message.to],
                "subject": message.subject,
                "html": self._build_email_html(message.html, message.logo_url),
            }
            if message.text:
                payload["text"] = message.text
            if message.reply_to:
                payload["reply_to"] = message.reply_to

            response = httpx.post(
                f"{RESEND_API_URL}/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )

            if response.status_code in (200, 201):
                data = response.json()
                logger.info("email_sent", to=message.to, message_id=data.get("id"))
                return EmailResult(
                    status="sent",
                    status_code=response.status_code,
                    message_id=data.get("id"),
                )
            else:
                error_detail = response.text
                logger.error("email_send_failed", status=response.status_code, error=error_detail, to=message.to)
                return EmailResult(status="failed", status_code=response.status_code, error=error_detail)

        except httpx.TimeoutException:
            logger.error("email_send_timeout", to=message.to)
            return EmailResult(status="failed", error="Timeout connecting to Resend")
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
