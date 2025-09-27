# file: alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
from dotenv import load_dotenv

# --- ИЗМЕНЕНИЕ: Загружаем .env ---
load_dotenv()

# это объект Alembic Config, который предоставляет доступ к
# значениям в .ini файле.
config = context.config

# Интерпретируем config файл для Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- ИЗМЕНЕНИЕ: Простая и надежная установка URL ---
# Приоритет:
# 1. Переменная DATABASE_URL_ALEMBIC из .env (для локального `alembic revision`)
# 2. Переменная DATABASE_URL из config.py (для `alembic upgrade` внутри Docker)

db_url = os.getenv("DATABASE_URL_ALEMBIC")
if not db_url:
    from config import DATABASE_URL
    db_url = DATABASE_URL

# Убираем асинхронный драйвер, так как autogenerate работает в синхронном режиме
if db_url:
    config.set_main_option("sqlalchemy.url", db_url.replace("+asyncpg", ""))

# импортируем Base из ваших моделей, чтобы Alembic знал о них
from database.models import Base
target_metadata = Base.metadata

# --- КОНЕЦ ИЗМЕНЕНИЙ ---

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


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Эта функция будет вызываться ТОЛЬКО при `alembic upgrade`,
    # где connectable создается из правильного URL
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()