# file: alembic/env.py

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# импортируем Base из ваших моделей, чтобы Alembic знал о них
from database.models import Base
# импортируем URL базы данных из конфига
from config import DATABASE_URL


# это объект Alembic Config, который предоставляет доступ к
# значениям в .ini файле.
config = context.config

# Интерпретируем config файл для Python logging.
# Эта строка в основном настраивает логгеры.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Устанавливаем URL базы данных из нашего конфига, если он есть
# Это более гибко, чем жестко задавать его в alembic.ini
if DATABASE_URL:
    # Убираем +asyncpg, так как alembic работает в синхронном режиме при генерации
    sync_db_url = DATABASE_URL.replace("+asyncpg", "")
    config.set_main_option("sqlalchemy.url", sync_db_url)


# Добавьте сюда метаданные вашей модели для поддержки Autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
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
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Helper function to run migrations within a transaction."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # ИСПРАВЛЕНИЕ: Используем правильный атрибут 'config_ini_section'
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())