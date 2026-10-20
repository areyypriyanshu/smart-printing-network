from app.config import Settings
from app.gateways.email.base import EmailError, EmailSender
from app.gateways.email.console import ConsoleEmailSender
from app.gateways.email.memory import MemoryEmailSender
from app.gateways.email.smtp import SmtpEmailSender

__all__ = [
    "ConsoleEmailSender",
    "EmailError",
    "EmailSender",
    "MemoryEmailSender",
    "SmtpEmailSender",
    "build_email_sender",
]


def build_email_sender(settings: Settings) -> EmailSender:
    """The sender the application uses.

    The provider name is matched exactly, and an unknown name is an
    error rather than a silent fallback: the fallback would be the
    console sender, which writes a verification link to the log.
    """
    provider = settings.email_provider.strip().lower()
    if provider == "smtp":
        if not settings.smtp_host:
            raise ValueError("SMTP_HOST must be set when EMAIL_PROVIDER=smtp")
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            sender=settings.smtp_from,
            use_tls=settings.smtp_use_tls,
        )
    if provider == "console":
        if settings.env == "production":
            raise ValueError(
                "EMAIL_PROVIDER=console is not allowed when ENV=production: "
                "it writes the verification link to the log, and that link is "
                "a secret."
            )
        return ConsoleEmailSender()
    raise ValueError(f"Unknown EMAIL_PROVIDER: {settings.email_provider!r}")
