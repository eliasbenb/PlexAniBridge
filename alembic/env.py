from __future__ import with_statement

import pathlib
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

import src.models  # noqa: F401
from src import config as app_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = src.models.Base.metadata

db_url = f"sqlite:///{app_config.DATA_PATH / 'plexanibridge.db'}"
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(
        db_url,
        echo=False,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
