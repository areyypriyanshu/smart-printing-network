import argparse
import logging
import sys
import uuid
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.logging import setup_logging
from app.models import AdminAction, Shop, ShopRate, User
from app.services import auth_service

logger = logging.getLogger(__name__)

SEED_PASSWORD = "spn-demo-password"


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
    for spec in SEED_SHOPS:
        existing = session.scalar(select(User).where(User.email == spec["email"]))
        if existing is not None:
            logger.info("seed: %s already exists, skipping", spec["email"])
            continue
        user, shop = auth_service.register_vendor(
            session,
            email=spec["email"],
            password=SEED_PASSWORD,
            full_name=spec["full_name"],
            shop_name=spec["shop_name"],
            shop_address=spec["shop_address"],
            latitude=spec["latitude"],
            longitude=spec["longitude"],
        )
        shop.is_verified = True
        shop.min_order_paise = spec["min_order_paise"]
        session.add_all(_full_rate_table(shop.id, spec["base_paise"]))
        session.commit()
        logger.info("seed: created %s (%s)", spec["shop_name"], spec["email"])

    customer = session.scalar(select(User).where(User.email == SEED_CUSTOMER["email"]))
    if customer is None:
        auth_service.register_customer(
            session,
            email=SEED_CUSTOMER["email"],
            password=SEED_PASSWORD,
            full_name=SEED_CUSTOMER["full_name"],
        )
        logger.info("seed: created customer %s", SEED_CUSTOMER["email"])

    print("Seed complete. Local credentials (password for all):", SEED_PASSWORD)
    for spec in SEED_SHOPS:
        print(f"  vendor: {spec['email']}")
    print("  customer:", SEED_CUSTOMER["email"])


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


def create_admin(session: Session, email: str, password: str, full_name: str) -> int:
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        print(f"An account with email {email} already exists", file=sys.stderr)
        return 1
    auth_service.register_admin(session, email=email, password=password, full_name=full_name)
    print(f"Created admin account {email}")
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


def main(argv: list[str] | None = None) -> int:
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
    admin_parser.add_argument("email", help="admin account email")
    admin_parser.add_argument("password", help="admin password")
    admin_parser.add_argument(
        "--name", default="Administrator", help="the name shown in the admin panel"
    )

    args = parser.parse_args(argv)

    setup_logging()

    with SessionLocal() as session:
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
            return create_admin(session, str(args.email), str(args.password), str(args.name))
    return 2


if __name__ == "__main__":
    sys.exit(main())
