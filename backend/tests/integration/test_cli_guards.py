"""The three guards on the command line.

The command line is how an admin account is managed, and it is the only
way one is created. Three things about it are guards rather than
features: the rule that an administrator has to be somebody the
identity provider knows, the rule about which accounts may be deleted,
and the rule that the demo data is never seeded into a production
deployment.
"""

import pytest
from app.cli import main, seed
from app.gateways.identity.clerk_admin import ClerkAdminError, ClerkUser
from app.models import AdminAction, Shop, User
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_shop, create_user


class _Reader:
    """A stand-in for the identity provider's own API."""

    def __init__(self, people: dict[str, ClerkUser] | None = None) -> None:
        self.people = people or {}
        self.known = "user_known"

    def get_user(self, user_id: str) -> ClerkUser:
        person = self.people.get(user_id)
        if person is None:
            raise ClerkAdminError("the identity provider could not be reached")
        return person


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


def test_an_admin_the_provider_does_not_know_is_refused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """An administrator is somebody who can sign in.

    The account is created from the identity provider's own record of
    the person, so a subject the provider has never heard of cannot
    become an administrator here.
    """
    from app.cli import create_admin

    reader = _Reader()
    assert create_admin(db_session, "user_nobody", reader) == 1
    assert "identity provider" in capsys.readouterr().err

    found = db_session.scalar(select(User).where(User.email == "new@example.com"))
    assert found is None


def test_an_admin_the_provider_knows_is_accepted(db_session: Session) -> None:
    from app.cli import create_admin

    reader = _Reader(
        {
            "user_known": ClerkUser(
                id="user_known",
                email="new@example.com",
                full_name="The Operator",
                email_verified=True,
            )
        }
    )
    assert create_admin(db_session, "user_known", reader) == 0

    found = db_session.scalar(select(User).where(User.email == "new@example.com"))
    assert found is not None
    assert found.role == "admin"
    assert found.clerk_user_id == "user_known"


def test_an_admin_with_a_shop_cannot_be_deleted(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """A shop row points at the account and does not cascade.

    Deleting the account would leave the shop behind, pointing at a
    user that is no longer there.
    """
    admin = create_user(db_session, email="admin@example.com", role="admin", full_name="Owner")
    create_user(db_session, email="spare@example.com", role="admin", full_name="Spare")
    create_shop(db_session, owner=admin)

    assert run(db_session, "delete-admin", "admin@example.com") == 1
    assert "shop" in capsys.readouterr().err

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
