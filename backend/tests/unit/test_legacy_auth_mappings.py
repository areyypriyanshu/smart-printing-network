"""The current Clerk app must not load or map pre-Clerk auth material."""

from app.db import Base
from app.models import User
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


def test_user_queries_do_not_select_legacy_password_columns() -> None:
    statement = str(select(User).compile(dialect=postgresql.dialect()))

    assert "users.password_hash" not in statement
    assert "users.has_password" not in statement


def test_legacy_auth_tables_are_not_in_current_orm_metadata() -> None:
    assert "refresh_tokens" not in Base.metadata.tables
    assert "email_verification_tokens" not in Base.metadata.tables


def test_email_verification_state_remains_mapped() -> None:
    assert "email_verified" in User.__table__.columns
