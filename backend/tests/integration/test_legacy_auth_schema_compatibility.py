"""The contraction drops the pre-Clerk local auth schema entirely."""

from app.models import User
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine


def test_legacy_auth_schema_is_gone_after_contraction(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    # 0017 dropped these objects; the ORM and the physical schema agree.
    assert "refresh_tokens" not in tables
    assert "email_verification_tokens" not in tables
    assert "password_hash" not in user_columns
    assert "has_password" not in user_columns
    assert "email_verified" in user_columns

    # The current ORM never selects password material, and the local
    # verification cache stays enforced.
    assert "password_hash" not in User.__table__.columns
    assert "has_password" not in User.__table__.columns
    assert "email_verified" in User.__table__.columns
    statement = str(select(User).compile(engine))
    assert "password_hash" not in statement
    assert "has_password" not in statement
