import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.errors import EmailTaken, Unauthenticated
from app.models import RefreshToken, Shop, User

REFRESH_COOKIE = "spn_refresh"

#: The hash of a value nobody knows. It is used to spend the same work on a
#: login for an address that does not exist as on one that does, so that the
#: response time does not disclose which addresses are registered.
_UNKNOWN_ACCOUNT_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$m1R/gA8/zB8YG8kwQeYrkA"
    "$FT3/czf63PVKxdDPJi8b9TrQQBc/vwIUYwUeo53R9Sk"
)


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_in: int


def register_customer(session: Session, *, email: str, password: str, full_name: str) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        has_password=True,
        full_name=full_name,
        role="customer",
    )
    session.add(user)
    _commit_or_email_taken(session)
    return user


def register_vendor(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    shop_name: str,
    shop_address: str,
    phone: str | None = None,
    latitude: float,
    longitude: float,
) -> tuple[User, Shop]:
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        has_password=True,
        full_name=full_name,
        role="vendor",
    )
    try:
        session.add(user)
        # The shop needs the owner's id, so the user row is flushed before
        # the shop is built. That flush is where the unique email
        # constraint is hit, so it has to sit inside the same guard as the
        # commit. Otherwise a duplicate email escapes as a 500 instead of
        # the 409 the API promises.
        session.flush()
        shop = Shop(
            owner_id=user.id,
            name=shop_name,
            address=shop_address,
            phone=phone,
            location=WKTElement(f"POINT({longitude} {latitude})", srid=4326),
        )
        session.add(shop)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailTaken("An account with this email already exists") from exc
    return user, shop


def register_admin(session: Session, *, email: str, password: str, full_name: str) -> User:
    """Create an admin account.

    There is deliberately no endpoint that calls this. An admin is the
    person who decides which shops are allowed to take orders, so an open
    signup for one would hand that decision to whoever found the form
    first. Admin accounts are created from the command line by the
    operator, who already has the server.
    """
    security.validate_password_strength(password)
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        has_password=True,
        full_name=full_name,
        role="admin",
    )
    session.add(user)
    _commit_or_email_taken(session)
    return user


def login(session: Session, *, email: str, password: str) -> tuple[User, TokenBundle]:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        # Spend the same work on an address that does not exist as on one
        # that does, so the response time does not say which addresses are
        # registered. The hash is of a value nobody knows, so the check
        # always fails and the error is the same one.
        security.verify_password(password, _UNKNOWN_ACCOUNT_HASH)
        raise Unauthenticated("Invalid email or password")
    if not security.verify_password(password, user.password_hash):
        raise Unauthenticated("Invalid email or password")
    if not user.is_active:
        raise Unauthenticated("Account is disabled")
    return user, sign_in(session, user)


def sign_in(session: Session, user: User) -> TokenBundle:
    """The tokens for an account that has just been proved.

    The login uses it, and so does a sign in with a provider: in both
    cases the account is known and the work of checking it is already
    done. The family is new every time, so a token that was stolen
    cannot be used beside the one the owner has.
    """
    bundle = _issue_tokens(session, user, family_id=uuid.uuid4())
    session.commit()
    return bundle


def set_password(session: Session, *, user: User, password: str) -> User:
    """Give a provider-only account a password while it is authenticated.

    A Google-only account is not a dead end: it can add a local password
    without changing its verified email or disconnecting the provider.
    The account must not overwrite an existing password through this path;
    changing one belongs to password reset, which remains out of scope.
    """
    if user.has_password:
        raise Unauthenticated("This account already has a password")
    user.password_hash = security.hash_password(password)
    user.has_password = True
    session.commit()
    return user


def refresh(session: Session, refresh_token: str) -> tuple[User, TokenBundle]:
    token_hash = _hash_refresh_token(refresh_token)
    row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is None:
        raise Unauthenticated("Invalid refresh token")
    if row.revoked_at is not None:
        _revoke_family(session, row.family_id)
        session.commit()
        raise Unauthenticated("Refresh token already used")
    if row.expires_at <= _now():
        raise Unauthenticated("Refresh token expired")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthenticated("Invalid refresh token")
    revoked_id = session.scalar(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
        .returning(RefreshToken.id)
    )
    if revoked_id is None:
        _revoke_family(session, row.family_id)
        session.commit()
        raise Unauthenticated("Refresh token already used")
    bundle = _issue_tokens(session, user, family_id=row.family_id)
    session.commit()
    return user, bundle


def logout(session: Session, refresh_token: str) -> None:
    token_hash = _hash_refresh_token(refresh_token)
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    session.commit()


def _issue_tokens(session: Session, user: User, *, family_id: uuid.UUID) -> TokenBundle:
    settings = get_settings()
    refresh_plain = secrets.token_urlsafe(48)
    session.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id,
            token_hash=_hash_refresh_token(refresh_plain),
            expires_at=_now() + timedelta(days=settings.refresh_token_days),
        )
    )
    session.flush()
    return TokenBundle(
        access_token=security.create_access_token(user.id, user.role),
        refresh_token=refresh_plain,
        expires_in=settings.access_token_minutes * 60,
    )


def _revoke_family(session: Session, family_id: uuid.UUID) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _commit_or_email_taken(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailTaken("An account with this email already exists") from exc
