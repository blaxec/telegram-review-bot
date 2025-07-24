# file: config.py

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1", 6127982184))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", 7205028708))
ADMIN_IDS = [ADMIN_ID_1, ADMIN_ID_2]

# --- Конфигурация базы данных ---
# Приоритет для DATABASE_URL из окружения (для Render)
DATABASE_URL = os.getenv("DATABASE_URL")

# Если DATABASE_URL не задан, собираем из частей (для локальной разработки)
if not DATABASE_URL:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "telegram_bot_db")
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Убедимся, что URL совместим с asyncpg
# Render предоставляет URL, начинающийся с "postgres://", а SQLAlchemy требует "postgresql+asyncpg://"
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


# --- Конфигурация Redis ---
# Аналогичный паттерн для Redis
REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    # Парсим URL от Render, например: "redis://red-d20cd815pdvs73ccthb0:6379"
    # Для библиотеки redis нужны хост и порт отдельно
    from urllib.parse import urlparse
    redis_parsed_url = urlparse(REDIS_URL)
    REDIS_HOST = redis_parsed_url.hostname
    REDIS_PORT = redis_parsed_url.port
else:
    # Фоллбэк для локальной разработки
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))