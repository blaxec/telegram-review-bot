# file: alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os

# это объект Alembic Config, который предоставляет доступ к
# значениям в .ini файле.
config = context.config

# Интерпретируем config файл для Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- ВАЖНО: импортируем модели ПОСЛЕ настройки URL ---
# Сначала настраиваем URL, потом импортируем все остальное,
# чтобы избежать преждевременного чтения конфигов.
from database.models import Base
target_metadata = Base.metadata

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
    # В этом режиме мы ИГНОРИРУЕМ config.py и используем alembic.ini,
    # но Docker Compose сам подставит нужные переменные окружения.
    # Поэтому нам нужно, чтобы URL для Docker был в alembic.ini.
    
    # Чтобы это работало и локально, и в Docker, мы будем
    # использовать переменную окружения прямо в alembic.ini.
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


# --- ИЗМЕНЕНИЕ: Убираем импорт dotenv и сложную логику ---
# Alembic сам будет читать alembic.ini, а Docker подставит нужные переменные.
# Логика теперь находится в alembic.ini.

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()