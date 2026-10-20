"""The sender that keeps the messages, for the tests.

A test that needs to know what was sent reads `messages`. Nothing
leaves the process, so the test suite needs no mail server and no
network.
"""

from app.gateways.email.base import EmailError  # noqa: F401


class MemoryEmailSender:
    """Keeps the messages in memory instead of sending them."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "body": body})

    @property
    def last_body(self) -> str:
        """The body of the last message, or an empty string."""
        return self.messages[-1]["body"] if self.messages else ""
