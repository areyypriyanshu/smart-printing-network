"""The email gateway.

The application must not know how a message is delivered, and the
delivery must be replaceable in a test without a network. These tests
cover the two things that are easy to get wrong: the sender that
writes a secret to the log, and the sender that talks to a server that
is not there.
"""

import logging

import pytest
from app.config import Settings
from app.gateways.email import (
    ConsoleEmailSender,
    EmailError,
    MemoryEmailSender,
    SmtpEmailSender,
    build_email_sender,
)


def _settings(**overrides: object) -> Settings:
    base = {
        "env": "local",
        "payment_provider": "fake",
        "fake_webhook_secret": "a-secret",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_the_console_sender_writes_the_message_to_the_log() -> None:
    """A local machine has no mail box, so the link is printed."""
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture()
    logger = logging.getLogger("app.gateways.email.console")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    sender = ConsoleEmailSender()
    try:
        sender.send(to="a@example.com", subject="Confirm", body="the link")
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    assert records[0].body == "the link"  # type: ignore[attr-defined]
    assert records[0].to == "a@example.com"  # type: ignore[attr-defined]
    assert sender.messages[0]["to"] == "a@example.com"


def test_the_console_sender_is_not_allowed_in_production() -> None:
    """The link in a message proves an address, and that link is a secret."""
    with pytest.raises(ValueError) as refused:
        build_email_sender(_settings(env="production", email_provider="console"))

    assert "production" in str(refused.value)


def test_smtp_needs_a_host() -> None:
    with pytest.raises(ValueError):
        build_email_sender(_settings(email_provider="smtp", smtp_host=""))


def test_an_unknown_provider_is_an_error() -> None:
    with pytest.raises(ValueError):
        build_email_sender(_settings(email_provider="carrier-pigeon"))


def test_a_server_that_is_not_there_is_an_error() -> None:
    """A mail server that is down must not take the application down with it."""
    sender = SmtpEmailSender(
        host="127.0.0.1",
        port=1,
        username="",
        password="",
        sender="no-reply@spn.local",
    )

    with pytest.raises(EmailError):
        sender.send(to="a@example.com", subject="Confirm", body="the link")


def test_the_memory_sender_keeps_the_message() -> None:
    sender = MemoryEmailSender()

    sender.send(to="a@example.com", subject="Confirm", body="the link")

    assert sender.last_body == "the link"
    assert sender.messages[0]["subject"] == "Confirm"
