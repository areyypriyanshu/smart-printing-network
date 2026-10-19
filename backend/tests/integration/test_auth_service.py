from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from app.errors import EmailTaken, Unauthenticated
from app.models import RefreshToken
from app.services import auth_service
from sqlalchemy import select
from sqlalchemy.orm import Session

CREDENTIALS = {
    "email": "service@example.com",
    "password": "password-123",
    "full_name": "Service User",
}


def test_password_hash_is_argon2id(db_session: Session) -> None:
    user = auth_service.register_customer(db_session, **CREDENTIALS)

    assert user.password_hash.startswith("$argon2id$")


def test_duplicate_email_is_rejected_case_insensitively(db_session: Session) -> None:
    auth_service.register_customer(db_session, **CREDENTIALS)

    with pytest.raises(EmailTaken):
        auth_service.register_customer(
            db_session, **{**CREDENTIALS, "email": "SERVICE@example.com"}
        )


def test_refresh_rotates_and_reuse_revokes_whole_family(db_session: Session) -> None:
    auth_service.register_customer(db_session, **CREDENTIALS)
    _user, first = auth_service.login(
        db_session, email=CREDENTIALS["email"], password=CREDENTIALS["password"]
    )

    _user, second = auth_service.refresh(db_session, first.refresh_token)
    assert second.refresh_token != first.refresh_token

    with pytest.raises(Unauthenticated):
        auth_service.refresh(db_session, first.refresh_token)

    with pytest.raises(Unauthenticated):
        auth_service.refresh(db_session, second.refresh_token)


def test_expired_refresh_token_is_rejected(db_session: Session) -> None:
    user = auth_service.register_customer(db_session, **CREDENTIALS)
    expired_plain = "expired-token-value"
    db_session.add(
        RefreshToken(
            user_id=user.id,
            family_id=user.id,
            token_hash=sha256(expired_plain.encode()).hexdigest(),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    with pytest.raises(Unauthenticated):
        auth_service.refresh(db_session, expired_plain)


def test_logout_revokes_token(db_session: Session) -> None:
    auth_service.register_customer(db_session, **CREDENTIALS)
    _user, tokens = auth_service.login(
        db_session, email=CREDENTIALS["email"], password=CREDENTIALS["password"]
    )

    auth_service.logout(db_session, tokens.refresh_token)

    with pytest.raises(Unauthenticated):
        auth_service.refresh(db_session, tokens.refresh_token)


def test_refresh_stores_only_hashes(db_session: Session) -> None:
    auth_service.register_customer(db_session, **CREDENTIALS)
    _user, tokens = auth_service.login(
        db_session, email=CREDENTIALS["email"], password=CREDENTIALS["password"]
    )

    rows = list(db_session.scalars(select(RefreshToken)))

    assert rows
    assert all(row.token_hash != tokens.refresh_token for row in rows)
    assert all(len(row.token_hash) == 64 for row in rows)
