from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401
from app.config import get_settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers` is off on purpose. The default is on, and
    # that switches off every logger that already exists and is not named
    # in alembic.ini, which is every logger in the application. A
    # migration must not change the logging of the process it runs in:
    # the test suite runs the migration in the same process as the
    # application, and the application was then logging nothing at all.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

POSTGIS_SCHEMAS = {"topology", "tiger", "tiger_data"}
POSTGIS_TABLES = {"spatial_ref_sys"}
LEGACY_AUTH_TABLES = {"refresh_tokens", "email_verification_tokens"}
LEGACY_AUTH_USER_COLUMNS = {"password_hash", "has_password"}


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    if type_ == "schema" and name in POSTGIS_SCHEMAS:
        return False
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    return True


def include_object(
    object_: object,
    name: str,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Keep the old authentication schema out of the current model comparison.

    The current application no longer maps these objects, but the physical
    schema remains until a later contraction release. The previous image still
    needs them for rollback, so Alembic must neither drop them nor report them
    as drift during this compatibility window. The later contraction removes
    this allow-list in the same change as its reversible migration.
    """
    if type_ == "table" and name in LEGACY_AUTH_TABLES:
        return False
    if type_ == "column" and getattr(object_, "table", None) is not None:
        table = object_.table
        if table.name == "users" and name in LEGACY_AUTH_USER_COLUMNS:
            return False
    return True


def _database_url() -> str:
    override: str | None = config.attributes.get("database_url")
    return override or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-c search_path=public"},
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
