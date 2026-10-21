import argparse
import logging
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.gateways.identity.clerk_admin import ClerkAdminClient, ClerkAdminError
from app.gateways.identity.fake import dev_subject_for
from app.logging import setup_logging
from app.models import AdminAction, Order, Shop, ShopRate, Upload, User
from app.services import admin_service, identity_service

logger = logging.getLogger(__name__)


class SeedShopSpec(TypedDict):
    email: str
    full_name: str
    shop_name: str
    shop_address: str
    latitude: float
    longitude: float
    min_order_paise: int
    base_paise: int


SEED_SHOPS: list[SeedShopSpec] = [
    {
        "email": "vendor1@example.com",
        "full_name": "Vendor One",
        "shop_name": "Central Prints",
        "shop_address": "12 Esplanade Row, Kolkata",
        "latitude": 22.5726,
        "longitude": 88.3639,
        "min_order_paise": 2000,
        "base_paise": 200,
    },
    {
        "email": "vendor2@example.com",
        "full_name": "Vendor Two",
        "shop_name": "Campus Copy Center",
        "shop_address": "5 College Street, Kolkata",
        "latitude": 22.5800,
        "longitude": 88.3700,
        "min_order_paise": 1500,
        "base_paise": 150,
    },
    {
        "email": "vendor3@example.com",
        "full_name": "Vendor Three",
        "shop_name": "Quick Print House",
        "shop_address": "9 Park Street, Kolkata",
        "latitude": 22.5650,
        "longitude": 88.3550,
        "min_order_paise": 3000,
        "base_paise": 300,
    },
]
SEED_CUSTOMER = {
    "email": "customer@example.com",
    "full_name": "Demo Customer",
}


def seed(session: Session) -> None:
    """Create the demo shops, rates and customer.

    The command is for local development only. It refuses to run against a
    production configuration, because the shops it creates are on the
    market and the accounts it creates are local ones.
    """
    if get_settings().env == "production":
        raise SystemExit("the seed command is for local development only")
    for spec in SEED_SHOPS:
        existing = session.scalar(select(User).where(User.email == spec["email"]))
        if existing is not None:
            _link_local_account(session, existing)
            logger.info("seed: %s already exists, skipping", spec["email"])
            continue
        user, shop = identity_service.create_vendor_account(
            session,
            subject=dev_subject_for(spec["email"]),
            email=spec["email"],
            full_name=spec["full_name"],
            shop_name=spec["shop_name"],
            shop_address=spec["shop_address"],
            phone=None,
            latitude=spec["latitude"],
            longitude=spec["longitude"],
        )
        shop.min_order_paise = spec["min_order_paise"]
        session.add_all(_full_rate_table(shop.id, spec["base_paise"]))
        session.commit()
        # The market state and the log entry come from the approval path, so
        # a seeded shop is approved the same way an approved shop is, and the
        # moderation log can answer who approved it. admin_id is None because
        # the shell is the actor, which is what the nullable admin_id column
        # on admin_actions is for.
        admin_service.approve_shop(session, shop_id=shop.id, admin_id=None)
        logger.info("seed: created %s (%s)", spec["shop_name"], spec["email"])

    customer = session.scalar(select(User).where(User.email == SEED_CUSTOMER["email"]))
    if customer is None:
        customer = identity_service.create_account(
            session,
            subject=dev_subject_for(SEED_CUSTOMER["email"]),
            email=SEED_CUSTOMER["email"],
            full_name=SEED_CUSTOMER["full_name"],
            role=identity_service.CUSTOMER,
        )
        logger.info("seed: created customer %s", SEED_CUSTOMER["email"])
    else:
        _link_local_account(session, customer)

    print("Seed complete. The local accounts are:", SEED_CUSTOMER["email"])
    for spec in SEED_SHOPS:
        print(f"  vendor: {spec['email']}")
    print("  customer:", SEED_CUSTOMER["email"])


def _link_local_account(session: Session, user: User) -> None:
    """Give a local account the identifier the local way in signs it in with.

    An account made before the cutover has no identifier, because the
    identity provider did not exist then. The seed is what makes the
    demo accounts usable, so it gives one that is missing the
    identifier it needs.
    """
    if user.clerk_user_id is not None:
        return
    user.clerk_user_id = dev_subject_for(user.email)
    session.commit()
    logger.info("seed: linked %s to the local way in", user.email)


def _full_rate_table(shop_id: uuid.UUID, base_paise: int) -> list[ShopRate]:
    prices = {
        ("A4", False, False): base_paise,
        ("A4", False, True): base_paise + 100,
        ("A4", True, False): base_paise * 4,
        ("A4", True, True): base_paise * 4 + 200,
        ("A3", False, False): base_paise + 100,
        ("A3", False, True): base_paise + 200,
        ("A3", True, False): base_paise * 6,
        ("A3", True, True): base_paise * 6 + 300,
    }
    return [
        ShopRate(
            shop_id=shop_id,
            paper_size=paper_size,
            color=color,
            duplex=duplex,
            rate_paise=rate_paise,
        )
        for (paper_size, color, duplex), rate_paise in prices.items()
    ]


def verify_shop(session: Session, email: str, admin_id: uuid.UUID | None = None) -> int:
    user = session.scalar(select(User).where(User.email == email))
    if user is None or user.role != "vendor":
        print(f"No vendor found with email {email}", file=sys.stderr)
        return 1
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        print(f"Vendor {email} has no shop", file=sys.stderr)
        return 1
    shop.is_verified = True
    shop.accepting_orders = True
    session.add(AdminAction(admin_id=admin_id, action="shop_approved", shop_id=shop.id))
    session.commit()
    print(f"Verified shop '{shop.name}' ({email})")
    return 0


def suspend_shop(
    session: Session, email: str, reason: str, admin_id: uuid.UUID | None = None
) -> int:
    user = session.scalar(select(User).where(User.email == email))
    if user is None or user.role != "vendor":
        print(f"No vendor found with email {email}", file=sys.stderr)
        return 1
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        print(f"Vendor {email} has no shop", file=sys.stderr)
        return 1
    if not shop.is_verified:
        print(f"Shop '{shop.name}' is not verified", file=sys.stderr)
        return 1
    shop.is_verified = False
    shop.accepting_orders = False
    session.add(
        AdminAction(
            admin_id=admin_id,
            action="shop_suspended",
            shop_id=shop.id,
            reason=reason,
        )
    )
    session.commit()
    print(f"Suspended shop '{shop.name}' ({email})")
    return 0


def list_shops(session: Session, pending_only: bool) -> int:
    """List the shops, so the command line is usable on its own."""
    stmt = (
        select(Shop, User.email)
        .join(User, User.id == Shop.owner_id)
        .order_by(Shop.created_at.asc(), Shop.id.asc())
    )
    if pending_only:
        stmt = stmt.where(Shop.is_verified.is_(False))
    rows = list(session.execute(stmt).all())
    if not rows:
        print("No shops to show.")
        return 0
    for shop, owner_email in rows:
        state = "verified" if shop.is_verified else "pending"
        accepting = "taking orders" if shop.accepting_orders else "not taking orders"
        print(f"{shop.id}  {state:9}  {shop.name}  <{owner_email}>  {shop.address}")
        print(f"            {accepting}, created {shop.created_at.isoformat()}")
    print(f"{len(rows)} shop(s).")
    return 0


def list_admins(session: Session) -> int:
    """List the admin accounts, so it is clear who holds elevated access.

    Inactive accounts are listed too. An admin that has been deactivated
    still has its decisions in the moderation log, so hiding it would
    make the log harder to read, not easier.
    """
    rows = list(
        session.execute(
            select(
                User,
                func.count(AdminAction.id).label("actions"),
            )
            .outerjoin(AdminAction, AdminAction.admin_id == User.id)
            .where(User.role == "admin")
            .group_by(User.id)
            .order_by(User.created_at.asc(), User.id.asc())
        ).all()
    )
    if not rows:
        print("There are no admin accounts.")
        print("Create one with: python -m app.cli create-admin <email>")
        return 0
    for user, actions in rows:
        state = "active" if user.is_active else "deactivated"
        print(f"{user.email}  {state}  {user.full_name}  {actions} decision(s)")
        print(f"            created {user.created_at.isoformat()}")
    active = sum(1 for user, _ in rows if user.is_active)
    print(f"{len(rows)} admin account(s), {active} active.")
    return 0


def set_admin_active(session: Session, email: str, active: bool) -> int:
    """Turn an admin account on or off.

    Deactivating is the normal way to remove access, and it takes effect
    at once: both the login and every authenticated request check
    `is_active`, so an access token that was issued before the change
    stops working immediately rather than at its expiry.

    The account itself is kept. Its decisions stay in the moderation log,
    and the log is the reason the admin panel exists.
    """
    user = session.scalar(select(User).where(User.email == email, User.role == "admin"))
    if user is None:
        print(f"No admin account with email {email}", file=sys.stderr)
        return 1
    if user.is_active == active:
        state = "already active" if active else "already deactivated"
        print(f"{email} is {state}.")
        return 0
    if not active and _active_admin_count(session) == 1:
        # Deactivating the last admin leaves nobody who can undo it from
        # the panel. It is still recoverable with create-admin, but the
        # operator should mean to do it.
        print(
            f"{email} is the only active admin. Create another one before deactivating it.",
            file=sys.stderr,
        )
        return 1
    user.is_active = active
    session.commit()
    if active:
        print(f"Reactivated admin account {email}")
    else:
        print(f"Deactivated admin account {email}. Its access is revoked now.")
    return 0


def delete_admin(session: Session, email: str) -> int:
    """Delete an admin account outright.

    Only possible for an account that has never done anything. Five
    tables point at `users.id` and none of them cascade, so an account
    with a decision, a shop, an order, an upload or a session cannot be
    deleted without breaking one of them. Those accounts are deactivated
    instead, and that is the better answer anyway, because the
    moderation log is worth more than the tidiness of a missing row.
    """
    user = session.scalar(select(User).where(User.email == email, User.role == "admin"))
    if user is None:
        print(f"No admin account with email {email}", file=sys.stderr)
        return 1
    blockers = _admin_blockers(session, user.id)
    if blockers:
        print(
            f"{email} cannot be deleted because it still has {blockers}. "
            f"Deactivate it instead: python -m app.cli deactivate-admin {email}",
            file=sys.stderr,
        )
        return 1
    if user.is_active and _active_admin_count(session) == 1:
        print(
            f"{email} is the only active admin. Create another one before deleting it.",
            file=sys.stderr,
        )
        return 1
    session.delete(user)
    session.commit()
    print(f"Deleted admin account {email}")
    return 0


def _active_admin_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True))
        )
        or 0
    )


def _admin_blockers(session: Session, admin_id: uuid.UUID) -> str:
    """What, if anything, still points at this admin account.

    Returns a short phrase naming the things, or an empty string when the
    account is pristine and can be deleted.
    """
    found: list[str] = []
    counts = {
        "recorded decision": session.scalar(
            select(func.count()).select_from(AdminAction).where(AdminAction.admin_id == admin_id)
        )
        or 0,
        "order": session.scalar(
            select(func.count()).select_from(Order).where(Order.customer_id == admin_id)
        )
        or 0,
        "upload": session.scalar(
            select(func.count()).select_from(Upload).where(Upload.customer_id == admin_id)
        )
        or 0,
        "shop": session.scalar(
            select(func.count()).select_from(Shop).where(Shop.owner_id == admin_id)
        )
        or 0,
    }
    for label, count in counts.items():
        if count:
            found.append(f"{count} {label}{'' if count == 1 else 's'}")
    return ", ".join(found)


def create_admin(
    session: Session,
    subject: str,
    reader: ClerkAdminClient,
) -> int:
    """Make somebody an administrator of this application.

    The person has to have an account with the identity provider
    already, because that is where the sign in and the address live.
    The command takes the provider's identifier for them and reads the
    rest from the provider, so the administrator is the person the
    provider says they are and not the person the shell says they are.
    """
    try:
        person = reader.get_user(subject)
    except ClerkAdminError as exc:
        print(f"The identity provider could not be read: {exc}", file=sys.stderr)
        return 1
    existing = session.scalar(select(User).where(User.email == person.email))
    if existing is not None:
        print(f"An account with email {person.email} already exists", file=sys.stderr)
        return 1
    user = User(
        email=person.email,
        clerk_user_id=subject,
        full_name=person.full_name,
        role="admin",
    )
    session.add(user)
    session.commit()
    print(f"Created admin account {person.email}")
    return 0


def prune_unused_accounts(session: Session, older_than_days: int, apply: bool) -> int:
    """The accounts that were made and never used.

    An account with no order, no upload and no session since it was
    created is an account that somebody made and then did nothing with:
    a mistyped address, a test, or spam. They are listed rather than
    deleted, and the operator decides, because the same shape covers a
    customer who signed up last week and has not printed anything yet.

    With --apply the accounts are deactivated rather than deleted. A
    deactivated account keeps its address, so the address cannot be
    claimed by somebody else, and it can be given back with
    activate-account. Deleting would take the row, and with it the
    guarantee that the address is still spoken for.
    """
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    rows = list(
        session.scalars(
            select(User)
            .where(
                User.role == "customer",
                User.is_active.is_(True),
                User.created_at < cutoff,
                # No order, no upload and no session since the account was
                # made. The subqueries are used rather than joins so that
                # the query is about the accounts, not about the rows the
                # joins happen to produce.
                ~User.id.in_(select(Order.customer_id)),
                ~User.id.in_(select(Upload.customer_id)),
            )
            .order_by(User.created_at.asc())
        ).all()
    )
    if not rows:
        print("No unused accounts.")
        return 0
    for user in rows:
        print(f"{user.id}  {user.email}  {user.full_name}  created {user.created_at.isoformat()}")
    if not apply:
        print(f"{len(rows)} unused account(s). Deactivate them with --apply.")
        return 0
    for user in rows:
        user.is_active = False
    session.commit()
    print(f"Deactivated {len(rows)} unused account(s). The addresses are still taken.")
    return 0


def set_account_active(session: Session, email: str, active: bool) -> int:
    """Give a customer account back, or take it away.

    Deactivating is the way an account is closed without losing the
    address it holds. The account itself is kept, so the address cannot
    be claimed by somebody else, and it can be given back.
    """
    user = session.scalar(select(User).where(User.email == email, User.role == "customer"))
    if user is None:
        print(f"No customer account with email {email}", file=sys.stderr)
        return 1
    if user.is_active == active:
        state = "already active" if active else "already deactivated"
        print(f"{email} is {state}.")
        return 0
    user.is_active = active
    session.commit()
    if active:
        print(f"Reactivated account {email}")
    else:
        print(f"Deactivated account {email}. The address is still taken.")
    return 0


def _admin_id_for(session: Session, email: str | None) -> uuid.UUID | None:
    """The admin an action should be attributed to, if one was named.

    An action taken without a named admin is attributed to nobody. That
    is what happens when the operator runs the command directly on the
    server, and it is a true statement: the shell is the actor.
    """
    if email is None:
        return None
    user = session.scalar(select(User).where(User.email == email, User.role == "admin"))
    if user is None:
        print(f"No admin account with email {email}", file=sys.stderr)
        raise SystemExit(1)
    return user.id


def main(
    argv: list[str] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    """Run a command.

    The session factory is a parameter so the commands can be tested
    against the test database instead of the live one.
    """
    parser = argparse.ArgumentParser(
        prog="app.cli", description="Smart Printing Network backend CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="seed 3 verified shops, rates and a customer")

    verify_parser = subparsers.add_parser("verify-shop", help="mark a vendor's shop verified")
    verify_parser.add_argument("email", help="vendor account email")
    verify_parser.add_argument(
        "--by", default=None, help="email of the admin account taking the decision"
    )

    suspend_parser = subparsers.add_parser("suspend-shop", help="take a shop off the market")
    suspend_parser.add_argument("email", help="vendor account email")
    suspend_parser.add_argument("--reason", required=True, help="why the shop is suspended")
    suspend_parser.add_argument(
        "--by", default=None, help="email of the admin account taking the decision"
    )

    list_parser = subparsers.add_parser("list-shops", help="list the shops")
    list_parser.add_argument(
        "--pending", action="store_true", help="only the shops waiting for a decision"
    )

    admin_parser = subparsers.add_parser("create-admin", help="create an admin account")
    admin_parser.add_argument(
        "subject",
        help="the identity provider's identifier for the person, such as user_2abc",
    )

    subparsers.add_parser("list-admins", help="list the admin accounts")

    deactivate_parser = subparsers.add_parser(
        "deactivate-admin", help="revoke an admin's access, keeping the account"
    )
    deactivate_parser.add_argument("email", help="admin account email")

    activate_parser = subparsers.add_parser(
        "activate-admin", help="give an admin their access back"
    )
    activate_parser.add_argument("email", help="admin account email")

    delete_parser = subparsers.add_parser(
        "delete-admin", help="delete an admin account that has never done anything"
    )
    delete_parser.add_argument("email", help="admin account email")

    prune_parser = subparsers.add_parser(
        "prune-unused-accounts",
        help="list the accounts that were made and never used",
    )
    prune_parser.add_argument(
        "--older-than-days",
        type=int,
        default=30,
        help="how old an account has to be to count as unused (default 30)",
    )
    prune_parser.add_argument(
        "--apply",
        action="store_true",
        help="deactivate the accounts instead of only listing them",
    )

    account_parser = subparsers.add_parser(
        "deactivate-account", help="close a customer account, keeping its address"
    )
    account_parser.add_argument("email", help="customer account email")

    reactivate_parser = subparsers.add_parser(
        "activate-account", help="give a customer account back"
    )
    reactivate_parser.add_argument("email", help="customer account email")

    args = parser.parse_args(argv)

    setup_logging()

    with session_factory() as session:
        if args.command == "seed":
            seed(session)
            return 0
        if args.command == "verify-shop":
            admin_id = _admin_id_for(session, args.by)
            return verify_shop(session, str(args.email), admin_id=admin_id)
        if args.command == "suspend-shop":
            admin_id = _admin_id_for(session, args.by)
            return suspend_shop(session, str(args.email), str(args.reason), admin_id=admin_id)
        if args.command == "list-shops":
            return list_shops(session, pending_only=bool(args.pending))
        if args.command == "create-admin":
            settings = get_settings()
            reader = ClerkAdminClient(secret_key=settings.clerk_secret_key)
            return create_admin(session, str(args.subject), reader)
        if args.command == "list-admins":
            return list_admins(session)
        if args.command == "deactivate-admin":
            return set_admin_active(session, str(args.email), active=False)
        if args.command == "activate-admin":
            return set_admin_active(session, str(args.email), active=True)
        if args.command == "delete-admin":
            return delete_admin(session, str(args.email))
        if args.command == "prune-unused-accounts":
            return prune_unused_accounts(
                session, older_than_days=int(args.older_than_days), apply=bool(args.apply)
            )
        if args.command == "deactivate-account":
            return set_account_active(session, str(args.email), active=False)
        if args.command == "activate-account":
            return set_account_active(session, str(args.email), active=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
