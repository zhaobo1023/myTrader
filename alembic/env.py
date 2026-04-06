# -*- coding: utf-8 -*-
"""
Alembic env.py - configured to use api.config.Settings and api.models
"""
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Import application config and models
from api.config import settings
from api.dependencies import Base
import api.models  # noqa: F401 - ensure all models are registered

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata

# Database URL from api.config (sync URL for Alembic)
# We use it directly instead of config.set_main_option to avoid
# configparser interpolation issues with % in URL-encoded passwords
DATABASE_URL = settings.sync_database_url

# Only include tables that are registered in our ORM models.
# This prevents Alembic from generating DROP TABLE for production tables
# that exist in the DB but are not managed by this ORM.
_managed_tables = set(target_metadata.tables.keys())


def include_object(obj, name, type_, reflected, compare_to):
    """Filter: only manage tables/indexes that belong to our ORM models."""
    if type_ == 'table':
        return name in _managed_tables
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
