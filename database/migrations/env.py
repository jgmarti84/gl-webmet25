# database/migrations/env.py
"""
Alembic environment configuration.

This file configures Alembic to:
1. Load database URL from environment variables (not alembic.ini)
2. Use our SQLAlchemy models for autogenerate
3. Support PostGIS geometry columns
"""
from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# Add the parent directory to path so we can import radar_db
# This handles both local development and Docker environments
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
sys.path.insert(0, "/app")  # Docker path

# Import our models and config
try:
    from radar_db.config import settings
    from radar_db.models import Base
except ImportError as e:
    print(f"Import error: {e}")
    print(f"sys.path: {sys.path}")
    raise

# This is the Alembic Config object
config = context.config

# Override sqlalchemy.url with our settings from environment
config.set_main_option('sqlalchemy.url', settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata

# Other values from the config, defined by the needs of env.py
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """
    Filter objects for autogenerate.
    
    This can be used to exclude certain tables from migrations,
    for example PostGIS system tables.
    """
    # Skip PostGIS internal tables
    if type_ == "table" and name.startswith("spatial_ref"):
        return False
    return True


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        # Important for PostGIS support
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            # Important settings for proper diff detection
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()