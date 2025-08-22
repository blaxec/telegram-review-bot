# file: config.py

import os
import logging
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
logger = logging.getLogger(__name__)

# --- Основные настройки бота ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1", 0))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", 0))
ADMIN_IDS = [ADMIN_ID_1, ADMIN_ID_2]

# ID канала, куда будут отправляться заявки на вывод.
WITHDRAWAL_CHANNEL_ID = int(os.getenv("WITHDRAWAL_CHANNEL_ID", 0))
FINAL_CHECK_ADMIN = ADMIN_ID_2 # Админ для финальной проверки

print("!!! DEBUG: Loaded ADMIN_ID_1 =", ADMIN_ID_1)
print("!!! DEBUG: Loaded ADMIN_ID_2 =", ADMIN_ID_2)

if WITHDRAWAL_CHANNEL_ID > 0:
    logger.warning(f"!!! КОНФИГУРАЦИЯ: WITHDRAWAL_CHANNEL_ID ({WITHDRAWAL_CHANNEL_ID}) является положительным числом.")
    logger.warning("!!! Для приватных каналов ID должен быть отрицательным и начинаться с -100.")
    logger.warning("!!! Бот, скорее всего, не сможет отправлять сообщения в канал. Пожалуйста, проверьте ID.")

# --- Награды (в звездах) ---
class Rewards:
    GOOGLE_REVIEW = 15.0
    YANDEX_WITH_TEXT = 50.0
    YANDEX_WITHOUT_TEXT = 15.0
    GMAIL_ACCOUNT = 5.0
    REFERRAL_EARNING = 0.45
    ADMIN_ADD_STARS = 999.0 # Награда для админ-команды /addstars

# --- Длительности и тайминги ---
class Durations:
    # Длительность холда для отзывов (в минутах)
    HOLD_GOOGLE_MINUTES = 5
    HOLD_YANDEX_WITH_TEXT_MINUTES = 24 * 60  # 1 день
    HOLD_YANDEX_WITHOUT_TEXT_MINUTES = 72 * 60 # 3 дня

    # Длительность кулдаунов (в часах)
    # ИЗМЕНЕНИЕ: Заменена одна переменная на три раздельные для гибкой настройки
    COOLDOWN_GOOGLE_REVIEW_HOURS = 5 / 60  # 5 минут
    COOLDOWN_YANDEX_WITH_TEXT_HOURS = 5 / 60  # 5 минут
    COOLDOWN_YANDEX_WITHOUT_TEXT_HOURS = 5 / 60 # 5 минут
    
    COOLDOWN_GMAIL_HOURS = 24
    COOLDOWN_WARNING_BLOCK_HOURS = 24

    # Тайминги для FSM-задач (в минутах)
    TASK_GOOGLE_LIKING_TIMEOUT = 10
    TASK_GOOGLE_LIKING_CONFIRM_APPEARS = 5
    TASK_GOOGLE_REVIEW_TIMEOUT = 15
    TASK_GOOGLE_REVIEW_CONFIRM_APPEARS = 7
    TASK_YANDEX_LIKING_TIMEOUT = 10
    TASK_YANDEX_LIKING_CONFIRM_APPEARS = 5
    TASK_YANDEX_REVIEW_TIMEOUT = 25
    TASK_YANDEX_REVIEW_CONFIRM_APPEARS = 10

    # Время жизни информационных сообщений (в секундах)
    DELETE_WELCOME_MESSAGE_DELAY = 15
    DELETE_INFO_MESSAGE_DELAY = 25
    DELETE_UNKNOWN_COMMAND_MESSAGE_DELAY = 10

# --- Лимиты и пороги ---
class Limits:
    MIN_WITHDRAWAL_AMOUNT = 15.0
    MIN_TRANSFER_AMOUNT = 1.0
    WARNINGS_THRESHOLD_FOR_BAN = 3


# --- Настройки подключения к базам данных ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS", "password")
    DB_HOST = os.getenv("DB_HOST", "postgres_db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "telegram_bot_db")
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
     DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    redis_parsed_url = urlparse(REDIS_URL)
    REDIS_HOST = redis_parsed_url.hostname
    REDIS_PORT = redis_parsed_url.port
else:
    REDIS_HOST = os.getenv("REDIS_HOST", "redis_db")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))