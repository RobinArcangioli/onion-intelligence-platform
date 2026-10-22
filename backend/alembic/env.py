"""Configuration Alembic : URL issue uniquement de l'environnement."""
from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.base import Base
from app import models  # noqa: F401 (enregistrement ORM)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def database_url() -> str:
    url = os.getenv("OIP_DATABASE_URL", "")
    if not url:
        raise RuntimeError("OIP_DATABASE_URL est requis pour les migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata,
                              compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
