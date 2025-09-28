# file: alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- ОТЛАДКА: Жестко задаем URL для локального теста ---
# Этот URL будет использоваться ТОЛЬКО для команды `alembic revision`
LOCAL_TEST_URL = "postgresql://postgres:password@localhost:5433/telegram_bot_db"

# импортируем Base из ваших моделей
from database.models import Base
target_metadata = Base.metadata

# это объект Alembic Config
config = context.config

# Интерпретируем config файл для Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- ИЗМЕНЕНИЕ: Устанавливаем URL напрямую для `revision` ---
config.set_main_option("sqlalchemy.url", LOCAL_TEST_URL)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # Используем наш жестко заданный URL
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
    # Создаем движок на основе нашего жестко заданного URL
    connectable = engine_from_config(
        {"sqlalchemy.url": config.get_main_option("sqlalchemy.url")},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

# Когда мы запускаем `alembic revision`, context.is_offline_mode() возвращает True
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()