"""Alembic migration environment for IT Talent AI Profile."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import event

# Register business models
import app.modules.analysis.models
import app.modules.assessments.models
import app.modules.auth.models
import app.modules.cvs.models
import app.modules.github.models
import app.modules.roadmaps.models
import app.modules.users.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


# Set search_path BEFORE SQLAlchemy initializes the connection.
@event.listens_for(engine, "connect", insert=True)
def set_search_path(dbapi_connection, connection_record):
    previous_autocommit = dbapi_connection.autocommit

    try:
        dbapi_connection.autocommit = True

        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION search_path TO public")
    finally:
        dbapi_connection.autocommit = previous_autocommit


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in (None, "ita")

    if type_ == "table":
        qualified_name = parent_names.get("schema_qualified_table_name")
        return qualified_name in target_metadata.tables

    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                include_schemas=True,
                include_name=include_name,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
