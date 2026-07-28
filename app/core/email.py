from typing import Protocol, List, Optional
from pydantic import BaseModel


class EmailResult(BaseModel):
    status: str  # "sent" | "failed" | "skipped"
    status_code: Optional[int] = None
    error: Optional[str] = None
    message_id: Optional[str] = None


class EmailMessage(BaseModel):
    to: str
    subject: str
    html: str
    text: Optional[str] = None
    reply_to: Optional[str] = None
    logo_url: Optional[str] = None


class EmailSender(Protocol):
    """Abstraction for email sending services (DIP)."""

    def send(self, message: EmailMessage) -> EmailResult:
        """Send a single email."""
        ...

    def send_bulk(self, messages: List[EmailMessage]) -> List[EmailResult]:
        """Send multiple emails."""
        ...


def get_email_sender() -> EmailSender:
    """Factory function for DI. Returns the configured EmailSender implementation."""
    from app.services.resend_email import ResendEmailSender
    return ResendEmailSender()
