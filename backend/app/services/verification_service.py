"""Prove that an email address belongs to the person who gave it.

The address is a login name and a display name, and until it has been
proved it is only a claim. The claim is proved by a link that is sent
to the address and clicked there. The token in that link is the only
secret involved, and it is stored as a hash, the way a refresh token
is, so a row that is read from the database cannot be turned into a
link that proves anything.

An account is created even when the message about it cannot be sent. A
mail server that is down is not a reason to refuse the account, and the
customer can ask for another link.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.config import Settings
from app.errors import EmailTaken, InvalidVerificationToken, PasswordMismatch
from app.gateways.email import EmailSender
from app.gateways.email.base import EmailError
from app.models import EmailVerificationToken, User

logger = logging.getLogger(__name__)

#: How many random bytes the token has. It is a bearer secret, so it
#: is as long as it needs to be and no longer.
TOKEN_BYTES = 32

SUBJECT = "Confirm your email address"

INVALID_LINK = "This link is not valid any more. Ask for a new one and try again."


@dataclass(frozen=True)
class IssuedToken:
    """A token that was sent, and when it stops working."""

    token: str
    expires_at: datetime


def issue_token(
    session: Session,
    settings: Settings,
    *,
    user: User,
    now: datetime | None = None,
) -> IssuedToken:
    """Make a token for an account and remember its hash.

    The tokens that were sent before are removed, so a link that is
    older than the newest one stops working. That is what a customer
    expects when they ask for the message again: the first link they
    clicked was probably the one they did not mean to click.
    """
    current = now if now is not None else datetime.now(UTC)
    session.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = current + timedelta(minutes=settings.email_verification_ttl_minutes)
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=expires_at,
        )
    )
    session.commit()
    return IssuedToken(token=token, expires_at=expires_at)


def send_verification(
    session: Session,
    sender: EmailSender,
    settings: Settings,
    *,
    user: User,
    now: datetime | None = None,
) -> IssuedToken:
    """Send the link that proves the address, and say when it stops working.

    A failure to send is logged and swallowed. The token is still
    valid, so a customer who asks for another link gets a new one and
    the old one is removed.
    """
    issued = issue_token(session, settings, user=user, now=now)
    link = verification_link(settings, issued.token)
    try:
        sender.send(
            to=user.email,
            subject=SUBJECT,
            body=message_body(link=link, full_name=user.full_name),
        )
    except EmailError:
        logger.error(
            "verification_email_failed",
            extra={"user_id": str(user.id), "email": user.email},
        )
    return issued


def verify(session: Session, *, token: str, now: datetime | None = None) -> User:
    """Prove the address, and return the account it belongs to.

    A link that has already been used is answered with the account it
    proved, because the customer clicked it twice and the second click
    is not a mistake. Every other way of failing says the same thing,
    so that a link cannot be probed to find out whether it was ever
    valid.
    """
    current = now if now is not None else datetime.now(UTC)
    row = session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == _hash(token))
    )
    if row is None:
        raise InvalidVerificationToken(INVALID_LINK)
    user = session.get(User, row.user_id)
    if user is None:
        raise InvalidVerificationToken(INVALID_LINK)
    if row.used_at is not None:
        if user.email_verified:
            return user
        raise InvalidVerificationToken(INVALID_LINK)
    if row.expires_at <= current:
        raise InvalidVerificationToken("This link has expired. Ask for a new one and try again.")
    row.used_at = current
    user.email_verified = True
    session.commit()
    return user


def change_email(session: Session, *, user: User, email: str, password: str) -> User:
    """Put a different address on the account.

    This is the way out of a mistyped address. Without it, an account
    made with an address nobody can read is an account that can never
    be proved, and the address it holds can never be used by the
    person it belongs to.

    The password is asked for, because changing the address is how an
    account is taken over, and a session that was stolen is not the
    password. The new address is unverified until it is proved, and the
    links that were sent to the old one stop working.
    """
    if not security.verify_password(password, user.password_hash):
        raise PasswordMismatch("That password is not right")
    try:
        user.email = email
        user.email_verified = False
        session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailTaken("An account with this email already exists") from exc
    return user


def verification_link(settings: Settings, token: str) -> str:
    """The address the customer opens to prove the address."""
    base = settings.app_base_url.rstrip("/")
    return f"{base}/verify-email?token={token}"


def message_body(*, link: str, full_name: str) -> str:
    """The text of the message.

    It is plain text, and the link is on a line of its own, so that it
    can be copied out of a mail client that will not open a link on its
    own.
    """
    return (
        f"Hello {full_name},\n"
        "\n"
        "Confirm your email address for Smart Printing Network. This link "
        "works once, and it stops working tomorrow.\n"
        "\n"
        f"{link}\n"
        "\n"
        "If you did not make this account, ignore this message and nobody "
        "will know the address works.\n"
    )


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
