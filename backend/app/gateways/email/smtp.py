"""The sender that hands the message to an SMTP server.

The standard library does this, so nothing is added to the dependency
list. The message is sent over a connection that is closed again
straight away, which is what a server that is not busy expects.

Two kinds of server are supported: one that starts the connection in
the clear and is upgraded with STARTTLS, which is the usual one on port
587, and one that expects the connection to be encrypted from the
first byte, which is the usual one on port 465.
"""

import smtplib
from email.message import EmailMessage

from app.gateways.email.base import EmailError

DEFAULT_TIMEOUT_SECONDS = 10.0


class SmtpEmailSender:
    """Sends the message over SMTP."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        use_tls: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._use_tls = use_tls
        self._timeout = timeout

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["To"] = to
        message["From"] = self._sender
        message["Subject"] = subject
        message.set_content(body)
        try:
            with self._connect() as smtp:
                if self._username:
                    if not self._use_tls and smtp.has_extn("starttls"):
                        smtp.starttls()
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailError(f"the message could not be sent: {exc}") from exc

    def _connect(self) -> smtplib.SMTP:
        if self._use_tls:
            return smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout)
        return smtplib.SMTP(self._host, self._port, timeout=self._timeout)
