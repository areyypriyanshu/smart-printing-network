import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings
from app.errors import Unauthenticated

_password_hasher = PasswordHasher()

#: The password policy, in one place, so that every path that creates an
#: account holds the same rule.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password: str) -> str:
    """One password policy for every path that creates an account.

    The password is returned unchanged. This is used as a Pydantic
    AfterValidator, and an AfterValidator's return value replaces the field
    value, so a validator that returned None would store None.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"the password must be at most {MAX_PASSWORD_LENGTH} characters")
    return password


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> tuple[uuid.UUID, str]:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise Unauthenticated("Invalid or expired token") from exc
    try:
        return uuid.UUID(str(payload["sub"])), str(payload["role"])
    except (KeyError, ValueError) as exc:
        raise Unauthenticated("Invalid token") from exc
