"""
Alembic Migration Environment Configuration

Configure Alembic connection with SQLAlchemy models and database
"""

import asyncio
import logging
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import application configuration and models
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import Base
from app.models import Order, OrderItem, Outbox, SagaStep  # Ensure all models are loaded

# Read Alembic configuration
config = context.config

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger('alembic.env')

# Set MetaData target
target_metadata = Base.metadata

def get_database_url():
    """Get database connection URL"""
    settings = get_settings()
    # Use sync version of database URL for migrations
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    logger.info(f"Using database URL: {sync_url.split('@')[1] if '@' in sync_url else sync_url}")
    return sync_url

def run_migrations_offline() -> None:
    """
    Run migrations in offline mode
    
    This mode configures context with just a URL without engine
    Suitable for --sql mode to generate SQL scripts
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Support batch mode for SQLite and other databases
        compare_type=True,     # Compare column type changes
        compare_server_default=True,  # Compare default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute actual migration operations"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
        # Custom comparison functions (if needed)
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def include_object(object, name, type_, reflected, compare_to):
    """
    Custom object inclusion logic
    
    Decide which database objects should be included in migrations
    """
    # Exclude certain tables or indexes (if needed)
    if type_ == "table" and name in ["alembic_version"]:
        return False
    
    # Include all other objects
    return True


async def run_async_migrations() -> None:
    """
    Run migrations in async mode
    
    Use async engine for migration operations
    """
    # Create async engine configuration
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Migrations don't need connection pool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in online mode
    
    This mode requires actual database connection
    """
    # Override database URL in config
    config.set_main_option("sqlalchemy.url", get_database_url())
    
    connectable = context.config.attributes.get("connection", None)

    if connectable is None:
        # Create sync engine for migrations
        connectable = create_engine(
            get_database_url(),
            poolclass=pool.NullPool,  # Migrations don't need connection pool
        )

    # For sync engine, run migrations directly
    with connectable.connect() as connection:
        do_run_migrations(connection)


# Choose appropriate migration mode based on context
if context.is_offline_mode():
    logger.info("Running migrations in offline mode")
    run_migrations_offline()
else:
    logger.info("Running migrations in online mode")
    run_migrations_online()