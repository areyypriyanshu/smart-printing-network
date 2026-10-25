"""Sending one message to one address.

The gateway is an interface: the application must not know how a
message is delivered, and the delivery must be replaceable in a test
without a network.

A message is a recipient, a subject and a body. The body is plain
text. There is no HTML template and no attachment, because the only
message this application sends is a link, and a link in plain text is a
link that works in every mail client, on a phone, and in the text
viewer of a student who has never seen a mail client.
"""

from typing import Protocol


class EmailError(Exception):
    """The message could not be handed over.

    A failed delivery is not a reason to refuse the thing the customer
    asked for. An account is created even when the message about it
    cannot be sent, and the customer can ask for another one.
    """


class EmailSender(Protocol):
    """Sends one message to one address."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Send the message, or raise `EmailError`."""
        ...
