"""What a login attempt tells a stranger.

Two things: how long it took, and which account it counted against.
Both have been a way in, and both are rules now.
"""

import time

import pytest
from app.errors import Unauthenticated
from app.models import User
from app.routers.auth import _account_key
from app.services import auth_service
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_user


def test_the_same_work_is_spent_on_both_paths(db_session: Session) -> None:
    """Both paths run a password verification, so both cost the same.

    The measurement is loose on purpose: it only has to catch a path that
    does no work at all, which is orders of magnitude faster.
    """
    customer = create_user(db_session, email="known@example.com")

    def timeit(email: str) -> float:
        started = time.perf_counter()
        with pytest.raises(Unauthenticated):
            auth_service.login(db_session, email=email, password="wrong-password")
        return time.perf_counter() - started

    known = timeit(customer.email)
    unknown = timeit("nobody@example.com")

    # The unknown path must not be less than half the work of the known
    # one. A path that skipped the hash would be thousands of times
    # faster, so this catches the regression without being a timing test
    # that flakes.
    assert unknown > known / 2


def test_the_rate_limit_key_is_the_account_not_the_spelling(db_session: Session) -> None:
    """Two spellings of one address are one account.

    The limit is on the account, so the key has to be the account the
    database resolves. Keying on the spelling would give an attacker a
    fresh bucket for every way of writing the same address.
    """
    customer = create_user(db_session, email="person@example.com")

    key = _account_key(db_session, "person@example.com")
    other = _account_key(db_session, "PERSON@example.com")

    assert key == other
    assert str(customer.id) in key


def test_an_unknown_address_still_gets_its_own_key(db_session: Session) -> None:
    """A stranger's addresses must not share one bucket.

    If they did, one attacker could lock every unknown address out of
    the login form at once, which is a denial of service for free.
    """
    first = _account_key(db_session, "nobody@example.com")
    second = _account_key(db_session, "nobody-else@example.com")

    assert first != second


def test_an_admin_cannot_be_created_with_a_weak_password(db_session: Session) -> None:
    with pytest.raises(ValueError, match="at least"):
        auth_service.register_admin(
            db_session, email="admin@example.com", password="short", full_name="Admin"
        )

    found = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert found is None
