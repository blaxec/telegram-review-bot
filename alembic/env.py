# file: alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# импортируем Base из ваших моделей, чтобы Alembic знал о них
from database.models import Base
target_metadata = Base.metadata

# это объект Alembic Config, который предоставляет доступ к
# значениям в .ini файле.
config = context.config

# Интерпретируем config файл для Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """
    Запускается в 'офлайн' режиме.
    Этот режим используется командой `alembic revision --autogenerate`.
    Он берет URL напрямую из alembic.ini.
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


def run_migrations_online() -> None:
    """
    Запускается в 'онлайн' режиме.
    Этот режим используется командой `alembic upgrade` внутри Docker.
    """
    # В этом режиме мы ИГНОРИРУЕМ alembic.ini и берем конфигурацию из кода,
    # чтобы использовать правильный URL (`...postgres_db...`)
    from config import DATABASE_URL
    from sqlalchemy.ext.asyncio import create_async_engine
    import asyncio

    # Для Alembic нужен синхронный URL
    sync_db_url = DATABASE_URL.replace("+asyncpg", "")

    connectable = create_async_engine(sync_db_url)

    async def run_async_migrations():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations, target_metadata)

    asyncio.run(run_async_migrations())


def do_run_migrations(connection, target_metadata):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()