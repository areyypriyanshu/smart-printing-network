"""The sender that writes the message to the log.

This is what a local development machine uses, and what a deployment
must not use. A verification message carries a link that proves an
address, and that link is a secret: anybody who has it can verify the
address. Printing it to the log puts it wherever the log goes, so this
sender refuses to run when the environment is production.

The message is written as one log record, with the body on its own
lines, so that it can be read and copied out of the terminal.
"""

import logging

logger = logging.getLogger(__name__)


class ConsoleEmailSender:
    """Writes the message to the log instead of sending it."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "body": body})
        logger.info(
            "email_console",
            extra={"to": to, "subject": subject, "body": body},
        )
