"""The compatibility release drops ORM dependencies before schema contraction."""

from app.models import User
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine


def test_legacy_auth_schema_stays_available_for_rollback(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    assert {"refresh_tokens", "email_verification_tokens"} <= tables
    assert {"password_hash", "has_password", "email_verified"} <= user_columns

    # This image must not load password material on ordinary account queries,
    # while the physical schema remains available to the previous image.
    assert "password_hash" not in User.__table__.columns
    assert "has_password" not in User.__table__.columns
    assert "email_verified" in User.__table__.columns
    statement = str(select(User).compile(engine))
    assert "password_hash" not in statement
    assert "has_password" not in statement
    with engine.connect() as connection:
        connection.execute(select(User).limit(1)).all()

        # Compile and run the previous version's auth-schema read shape
        # against the retained physical schema. LIMIT 0 checks every
        # legacy column without reading password or token material.
        connection.execute(text("SELECT password_hash, has_password FROM users LIMIT 0")).all()
        connection.execute(
            text(
                "SELECT id, user_id, family_id, token_hash, expires_at, revoked_at, created_at "
                "FROM refresh_tokens LIMIT 0"
            )
        ).all()
        connection.execute(
            text(
                "SELECT id, user_id, token_hash, expires_at, used_at, created_at "
                "FROM email_verification_tokens LIMIT 0"
            )
        ).all()
