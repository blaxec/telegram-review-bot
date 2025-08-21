# file: alembic/env.py

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
# ИСПРАВЛЕНИЕ: Импортируем create_async_engine напрямую
from sqlalchemy.ext.asyncio import create_async_engine

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
# Это нужно для оффлайн-режима
if DATABASE_URL:
    sync_db_url = DATABASE_URL.replace("+asyncpg", "")
    config.set_main_option("sqlalchemy.url", sync_db_url)


# Добавьте сюда метаданные вашей модели для поддержки Autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
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
    """Run migrations in 'online' mode."""
    # ИСПРАВЛЕНИЕ: Создаем движок напрямую из нашего асинхронного DATABASE_URL,
    # а не из конфигурации alembic.ini, чтобы гарантированно использовать asyncpg.
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())