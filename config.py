import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1", 6127982184))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", 7205028708))
ADMIN_IDS = [ADMIN_ID_1, ADMIN_ID_2]

FINAL_CHECK_ADMIN = ADMIN_ID_1

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS", "password")
    DB_HOST = os.getenv("DB_HOST", "postgres_db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "telegram_bot_db")
    
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    redis_parsed_url = urlparse(REDIS_URL)
    REDIS_HOST = redis_parsed_url.hostname
    REDIS_PORT = redis_parsed_url.port
else:
    REDIS_HOST = os.getenv("REDIS_HOST", "redis_db")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))