"""Tests for the purge_expired_verifications job.

A token that has expired is a secret nobody can use any more, and the
row that holds it is only clutter.
"""

from datetime import UTC, datetime, timedelta

from app.jobs import purge_expired_verifications
from app.models import EmailVerificationToken
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_user

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _token(session: Session, *, expires_at: datetime) -> EmailVerificationToken:
    user = create_user(session, email=f"user{expires_at.timestamp()}@example.com")
    row = EmailVerificationToken(
        user_id=user.id,
        token_hash="a" * 63 + str(int(expires_at.timestamp()))[-1],
        expires_at=expires_at,
    )
    session.add(row)
    session.commit()
    return row


def test_a_token_past_its_time_is_deleted(db_session: Session) -> None:
    _token(db_session, expires_at=NOW - timedelta(minutes=1))

    deleted = purge_expired_verifications.run(db_session, now=NOW)

    assert deleted == 1
    assert list(db_session.scalars(select(EmailVerificationToken))) == []


def test_a_token_that_is_still_good_is_kept(db_session: Session) -> None:
    _token(db_session, expires_at=NOW + timedelta(hours=1))

    deleted = purge_expired_verifications.run(db_session, now=NOW)

    assert deleted == 0
    assert len(list(db_session.scalars(select(EmailVerificationToken)))) == 1


def test_running_it_twice_deletes_nothing_the_second_time(db_session: Session) -> None:
    _token(db_session, expires_at=NOW - timedelta(minutes=1))

    assert purge_expired_verifications.run(db_session, now=NOW) == 1
    assert purge_expired_verifications.run(db_session, now=NOW) == 0
