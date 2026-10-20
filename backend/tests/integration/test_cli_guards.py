"""The three guards on the command line.

The command line is how an admin account is managed, and it is the only
way one is created. Three things about it are guards rather than
features: the password policy, the rule about which accounts may be
deleted, and the rule that the demo data is never seeded into a
production deployment.
"""

import io
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from app.cli import main, seed
from app.models import AdminAction, RefreshToken, Shop, User
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_user


class _KeepOpen:
    """A session that survives the `with` block the command line puts it in."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> bool:
        return False


def run(session: Session, *args: str) -> int:
    return main(list(args), session_factory=lambda: _KeepOpen(session))


def run_create_admin(session: Session, email: str, password: str = "password-123") -> int:
    with mock.patch("sys.stdin", io.StringIO(f"{password}\n")):
        return run(session, "create-admin", email, "--password-stdin")


def test_a_weak_admin_password_is_refused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same policy that the sign-up form holds.

    The form is the front door, so the policy belongs to the application
    and not to the form. The command line creates the account that can
    do the most damage, so it has to hold the same rule.
    """
    assert run_create_admin(db_session, "new@example.com", password="short") == 1
    assert "at least" in capsys.readouterr().err

    found = db_session.scalar(select(User).where(User.email == "new@example.com"))
    assert found is None


def test_a_strong_admin_password_is_accepted(db_session: Session) -> None:
    assert run_create_admin(db_session, "new@example.com", password="a-long-enough-password") == 0

    found = db_session.scalar(select(User).where(User.email == "new@example.com"))
    assert found is not None
    assert found.role == "admin"


def test_an_admin_with_a_session_cannot_be_deleted(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """A session row points at the account and does not cascade.

    Deleting the account would leave the session behind, pointing at a
    user that is no longer there.
    """
    admin = create_user(db_session, email="admin@example.com", role="admin", full_name="Owner")
    create_user(db_session, email="spare@example.com", role="admin", full_name="Spare")
    db_session.add(
        RefreshToken(
            user_id=admin.id,
            token_hash="a" * 64,
            family_id=admin.id,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    db_session.commit()

    assert run(db_session, "delete-admin", "admin@example.com") == 1
    assert "session" in capsys.readouterr().err

    found = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert found is not None


def test_an_admin_with_nothing_pointing_at_it_can_be_deleted(db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role="admin", full_name="Owner")
    create_user(db_session, email="spare@example.com", role="admin", full_name="Spare")

    assert run(db_session, "delete-admin", "admin@example.com") == 0

    found = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert found is None
    assert admin.id is not None


def test_the_seed_command_refuses_to_run_in_production(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demo accounts have a published password and the demo shops are
    on the market, so they are never seeded into a production database.
    """
    monkeypatch.setattr(
        "app.cli.get_settings",
        lambda: type("Settings", (), {"env": "production"})(),
    )

    with pytest.raises(SystemExit):
        seed(db_session)

    assert db_session.scalar(select(User).where(User.email == "customer@example.com")) is None
    assert db_session.scalar(select(Shop)) is None


def test_a_seeded_shop_goes_through_the_approval_path(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seed does not set the market state behind the moderation log's
    back. It uses the same approval an approved shop went through, so the
    log can answer who approved the shop and when.
    """
    monkeypatch.setattr(
        "app.cli.get_settings",
        lambda: type("Settings", (), {"env": "local"})(),
    )

    seed(db_session)

    shop = db_session.scalar(select(Shop).where(Shop.is_verified.is_(True)))
    assert shop is not None
    action = db_session.scalar(
        select(AdminAction).where(
            AdminAction.shop_id == shop.id, AdminAction.action == "shop_approved"
        )
    )
    assert action is not None
