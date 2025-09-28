# file: alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- ВАЖНО: Никаких импортов из config.py! ---

# это объект Alembic Config, который предоставляет доступ к
# значениям в .ini файле.
config = context.config

# Интерпретируем config файл для Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- ИМПОРТИРУЕМ МОДЕЛИ ЗДЕСЬ ---
from database.models import Base
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # Берет URL из alembic.ini
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
    # Создает движок на основе секции [alembic] в alembic.ini
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