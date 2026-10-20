"""The command line, which is how an admin account is managed.

There is no endpoint that creates, lists or removes an admin, on purpose.
An admin is the person who decides which shops are allowed to take
orders, so those accounts are managed by whoever holds the server. The
commands here are that tool.

The behaviour worth testing is the guarding, because the dangerous
mistakes are the ones that leave the platform with no admin at all, or
that destroy a moderation log.
"""

import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from app.cli import main
from app.errors import EmailTaken, Unauthenticated
from app.models import AdminAction, RefreshToken, User
from app.services import auth_service
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    DEFAULT_PASSWORD,
    create_full_rate_table,
    create_shop,
    create_unpaid_order,
    create_user,
)


class _KeepOpen:
    """A session that survives the `with` block the command line puts it in.

    The CLI closes the session it opens. The test session is owned by the
    fixture, so it must not be closed by the code under test.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> bool:
        return False


def run(session: Session, *args: str) -> int:
    """Run a command against the test database."""
    return main(list(args), session_factory=lambda: _KeepOpen(session))


def run_create_admin(session: Session, email: str, password: str = "password-123") -> int:
    """Run create-admin with the password on standard input.

    The password is not an argument, because an argument ends up in the
    shell history, in the process list and in the container metadata.
    """
    with mock.patch("sys.stdin", io.StringIO(f"{password}\n")):
        return run(session, "create-admin", email, "--password-stdin")


def make_admin(session: Session, email: str = "admin@example.com") -> User:
    return create_user(session, email=email, role="admin", full_name="Owner")


def make_spare_admin(session: Session) -> User:
    """A second admin, so the last-admin guard does not get in the way.

    The guard refuses to deactivate or delete the only active admin,
    because that would leave nobody who can undo it from the panel. A
    test that is about something else has to create a spare.
    """
    return create_user(session, email="spare@example.com", role="admin", full_name="Spare")


def test_listing_admins_shows_the_accounts_and_their_state(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    make_admin(db_session, "one@example.com")
    make_admin(db_session, "two@example.com")

    assert run(db_session, "list-admins") == 0

    output = capsys.readouterr().out
    assert "one@example.com" in output
    assert "two@example.com" in output
    assert "2 admin account(s), 2 active." in output


def test_listing_admins_shows_a_deactivated_account(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    make_admin(db_session)
    make_spare_admin(db_session)

    assert run(db_session, "deactivate-admin", "admin@example.com") == 0
    capsys.readouterr()

    assert run(db_session, "list-admins") == 0

    output = capsys.readouterr().out
    assert "deactivated" in output
    assert "1 active" in output


def test_listing_admins_when_there_are_none(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(db_session, "list-admins") == 0

    output = capsys.readouterr().out
    assert "There are no admin accounts." in output
    assert "create-admin" in output


def test_deactivating_an_admin_revokes_their_access(db_session: Session) -> None:
    admin = make_admin(db_session)
    make_spare_admin(db_session)

    assert run(db_session, "deactivate-admin", "admin@example.com") == 0

    db_session.refresh(admin)
    assert admin.is_active is False


def test_deactivating_an_admin_refuses_the_last_active_one(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """Otherwise the panel can be locked out by accident."""
    admin = make_admin(db_session)

    assert run(db_session, "deactivate-admin", "admin@example.com") == 1

    db_session.refresh(admin)
    assert admin.is_active is True
    assert "only active admin" in capsys.readouterr().err


def test_deactivating_one_of_several_admins_is_allowed(db_session: Session) -> None:
    make_admin(db_session, "one@example.com")
    second = make_admin(db_session, "two@example.com")

    assert run(db_session, "deactivate-admin", "two@example.com") == 0

    db_session.refresh(second)
    assert second.is_active is False


def test_deactivating_an_account_that_is_not_an_admin_is_refused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    create_user(db_session, email="customer@example.com", role="customer")

    assert run(db_session, "deactivate-admin", "customer@example.com") == 1

    assert "No admin account" in capsys.readouterr().err


def test_activating_an_admin_gives_their_access_back(db_session: Session) -> None:
    admin = make_admin(db_session)
    run(db_session, "deactivate-admin", "admin@example.com")

    assert run(db_session, "activate-admin", "admin@example.com") == 0

    db_session.refresh(admin)
    assert admin.is_active is True


def test_a_deleted_admin_cannot_sign_in(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """A deactivated admin is refused at the door, not just at the door check.

    The check on `is_active` happens on the login as well as on every
    authenticated request, so a deactivated admin cannot get a new token
    and an old token stops working too.
    """
    from app.services import auth_service

    make_admin(db_session)
    make_spare_admin(db_session)
    run(db_session, "deactivate-admin", "admin@example.com")

    with pytest.raises(Unauthenticated) as raised:
        auth_service.login(db_session, email="admin@example.com", password=DEFAULT_PASSWORD)
    assert "disabled" in str(raised.value)


def test_deleting_a_pristine_admin_removes_it(db_session: Session) -> None:
    make_admin(db_session)
    make_spare_admin(db_session)

    assert run(db_session, "delete-admin", "admin@example.com") == 0

    assert db_session.scalar(select(User).where(User.email == "admin@example.com")) is None


def test_deleting_an_admin_with_a_recorded_decision_is_refused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """The moderation log is worth more than a tidy table."""
    admin = make_admin(db_session)
    owner = create_user(db_session, email="owner@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner)
    db_session.add(AdminAction(admin_id=admin.id, action="shop_approved", shop_id=shop.id))
    db_session.commit()

    assert run(db_session, "delete-admin", "admin@example.com") == 1

    assert db_session.scalar(select(User).where(User.email == "admin@example.com")) is not None
    assert "recorded decision" in capsys.readouterr().err


def test_deleting_the_last_active_admin_is_refused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    make_admin(db_session)

    assert run(db_session, "delete-admin", "admin@example.com") == 1

    assert db_session.scalar(select(User).where(User.email == "admin@example.com")) is not None
    assert "only active admin" in capsys.readouterr().err


def test_creating_an_admin_twice_is_refused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_create_admin(db_session, "new@example.com") == 0
    capsys.readouterr()

    assert run_create_admin(db_session, "new@example.com") == 1

    assert "already exists" in capsys.readouterr().err


def test_a_deactivated_admin_cannot_be_recreated(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deactivating is not a way to get a fresh account with the same email.

    Use activate-admin instead, so the history stays attached to the one
    account.
    """
    make_admin(db_session)
    run(db_session, "deactivate-admin", "admin@example.com")
    capsys.readouterr()

    assert run_create_admin(db_session, "admin@example.com") == 1

    assert "already exists" in capsys.readouterr().err


def test_the_admin_id_attribution_survives_a_deactivation(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """A decision keeps pointing at the admin who made it."""
    admin = make_admin(db_session)
    make_spare_admin(db_session)
    owner = create_user(db_session, email="owner@example.com", role="vendor")
    create_shop(db_session, owner=owner)
    run(db_session, "verify-shop", "owner@example.com", "--by", "admin@example.com")
    capsys.readouterr()

    run(db_session, "deactivate-admin", "admin@example.com")

    action = db_session.scalar(select(AdminAction))
    assert action is not None
    assert action.admin_id == admin.id


def _make_old_customer(session: Session, email: str, days: int = 40) -> User:
    """A customer account that was made long ago and never used."""
    user = create_user(session, email=email)
    user.created_at = datetime.now(UTC) - timedelta(days=days)
    session.commit()
    return user


def test_pruning_lists_the_accounts_that_were_never_used(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing is deactivated until the operator says so."""
    _make_old_customer(db_session, "unused@example.com")

    assert run(db_session, "prune-unused-accounts") == 0

    output = capsys.readouterr().out
    assert "unused@example.com" in output
    assert "--apply" in output


def test_pruning_leaves_the_accounts_alone_until_it_is_asked(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    user = _make_old_customer(db_session, "unused@example.com")

    run(db_session, "prune-unused-accounts")
    capsys.readouterr()

    db_session.refresh(user)
    assert user.is_active is True


def test_pruning_deactivates_the_accounts_when_it_is_asked(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deactivated, not deleted: the address is still spoken for."""
    user = _make_old_customer(db_session, "unused@example.com")

    assert run(db_session, "prune-unused-accounts", "--apply") == 0

    db_session.refresh(user)
    assert user.is_active is False


def test_a_deactivated_account_keeps_its_address(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """Otherwise somebody else could take the address of a closed account."""
    _make_old_customer(db_session, "unused@example.com")

    assert run(db_session, "deactivate-account", "unused@example.com") == 0

    with pytest.raises(EmailTaken):
        auth_service.register_customer(
            db_session,
            email="unused@example.com",
            password=DEFAULT_PASSWORD,
            full_name="Test User",
        )


def test_an_account_that_came_back_is_not_unused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """A session since the account was made says a person was there."""
    user = _make_old_customer(db_session, "returning@example.com")
    db_session.add(
        RefreshToken(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.commit()

    assert run(db_session, "prune-unused-accounts") == 0

    assert "returning@example.com" not in capsys.readouterr().out


def test_an_account_that_ordered_is_not_unused(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    customer = _make_old_customer(db_session, "ordered@example.com")
    shop_owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=shop_owner)
    db_session.add_all(create_full_rate_table(db_session, shop))
    db_session.commit()
    create_unpaid_order(db_session, customer=customer, shop=shop)

    assert run(db_session, "prune-unused-accounts") == 0

    assert "ordered@example.com" not in capsys.readouterr().out
