"""Moi truong chay Alembic (Database Engineer, D1).

- URL ket noi KHONG doc tu alembic.ini hay os.environ: lay tu app.core.config.settings
  thong qua app.db.session.engine, cung engine ma Backend va Worker dung.
- Khong in URL/mat khau ra man hinh hay log.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import event

# Register business models
import app.db.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# ---------------------------------------------------------------------------
# Import tat ca models nghiep vu de Alembic phat hien cac bang
# (PBI-002: them models tu day tro di)
# ---------------------------------------------------------------------------
import app.modules.assessments.models  # noqa: F401, E402
import app.modules.cvs.models  # noqa: F401, E402
import app.modules.github.models  # noqa: F401, E402
import app.modules.roadmaps.models  # noqa: F401, E402
import app.modules.users.models  # noqa: F401, E402

# ---------------------------------------------------------------------------

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


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table_comment":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
