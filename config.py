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

# --- НОВАЯ НАСТРОЙКА: ID Тестировщиков для команды /skip ---
TESTER_IDS_STR = os.getenv("TESTER_IDS", "")
TESTER_IDS = [int(tester_id) for tester_id in TESTER_IDS_STR.split(',') if tester_id.strip().isdigit()]


# ID канала, куда будут отправляться заявки на вывод.
WITHDRAWAL_CHANNEL_ID = int(os.getenv("WITHDRAWAL_CHANNEL_ID", 0))
FINAL_CHECK_ADMIN = ADMIN_ID_2 # Админ для финальной проверки

# --- Ключи для Google Gemini ---
GOOGLE_API_KEY_1 = os.getenv("GOOGLE_API_KEY_1")
GOOGLE_API_KEY_2 = os.getenv("GOOGLE_API_KEY_2")
GOOGLE_API_KEYS = [key for key in [GOOGLE_API_KEY_1, GOOGLE_API_KEY_2] if key]

# --- ИЗМЕНЕНИЕ: Добавляем настройку модели Groq ---
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.1-70b-versatile")


if not GOOGLE_API_KEYS:
    logger.warning("!!! КОНФИГУРАЦИЯ: Не найдены GOOGLE_API_KEY_1 и GOOGLE_API_KEY_2 в .env файле.")
    logger.warning("!!! Функция автоматической проверки скриншотов (OCR) будет отключена.")


if WITHDRAWAL_CHANNEL_ID > 0:
    logger.warning(f"!!! КОНФИГУРАЦИЯ: WITHDRAWAL_CHANNEL_ID ({WITHDRAWAL_CHANNEL_ID}) является положительным числом.")
    logger.warning("!!! Для приватных каналов ID должен быть отрицательным и начинаться с -100.")
    logger.warning("!!! Бот, скорее всего, не сможет отправлять сообщения в канал. Пожалуйста, проверьте ID.")

# --- Награды (в звездах) ---
class Rewards:
    # Стандартные награды
    GOOGLE_REVIEW = 15.0
    YANDEX_WITH_TEXT = 50.0
    YANDEX_WITHOUT_TEXT = 15.0
    GMAIL_ACCOUNT = 5.0 # Стандартная награда
    ADMIN_ADD_STARS = 999.0 # Награда для админ-команды /addstars

    # Награды для реферальной системы
    # ПУТЬ 1: Google
    REFERRAL_GOOGLE_REVIEW = 0.45
    # ПУТЬ 2: Gmail
    GMAIL_FOR_REFERRAL_USER = 4.5 # Сколько получает сам реферал
    REFERRAL_GMAIL_ACCOUNT = 0.5 # Сколько получает реферер
    # ПУТЬ 3: Yandex
    REFERRAL_YANDEX_WITH_TEXT = 1.2
    REFERRAL_YANDEX_WITHOUT_TEXT = 0.6

    # --- ДОБАВЛЕНО: Награды для топа пользователей ---
    # Ключ - место в топе, значение - сумма награды
    TOP_USER_REWARDS = {
        1: 50.0,  # 1-е место
        2: 30.0,  # 2-е место
        3: 15.0   # 3-е место
    }


# --- Длительности и тайминги ---
class Durations:
    # Длительность холда для отзывов (в минутах)
    HOLD_GOOGLE_MINUTES = 5
    HOLD_YANDEX_WITH_TEXT_MINUTES = 24 * 60  # 1 день
    HOLD_YANDEX_WITHOUT_TEXT_MINUTES = 72 * 60 # 3 дня

    # Длительность кулдаунов (в часах)
    COOLDOWN_GOOGLE_REVIEW_HOURS = 5 / 60  # 5 минут
    COOLDOWN_YANDEX_WITH_TEXT_HOURS = 5 / 60  # 5 минут
    COOLDOWN_YANDEX_WITHOUT_TEXT_HOURS = 5 / 60 # 5 минут
    
    COOLDOWN_GMAIL_HOURS = 24
    COOLDOWN_WARNING_BLOCK_HOURS = 24

    # Кулдаун для запроса на разбан (в минутах)
    COOLDOWN_UNBAN_REQUEST_MINUTES = 30

    # Тайминги для FSM-задач (в минутах)
    TASK_GOOGLE_LIKING_TIMEOUT = 10
    TASK_GOOGLE_LIKING_CONFIRM_APPEARS = 5
    TASK_GOOGLE_REVIEW_TIMEOUT = 17
    TASK_GOOGLE_REVIEW_CONFIRM_APPEARS = 5
    TASK_YANDEX_LIKING_TIMEOUT = 10
    TASK_YANDEX_LIKING_CONFIRM_APPEARS = 5
    TASK_YANDEX_REVIEW_TIMEOUT = 25
    TASK_YANDEX_REVIEW_CONFIRM_APPEARS = 10
    TASK_GMAIL_VERIFICATION_TIMEOUT = 5 # Таймер на отправку созданного Gmail на проверку

    # --- ДОБАВЛЕНО: Таймаут ожидания текста от администратора ---
    AWAIT_ADMIN_TEXT_TIMEOUT_MINUTES = 60

    # Время жизни информационных сообщений (в секундах)
    DELETE_WELCOME_MESSAGE_DELAY = 15
    DELETE_INFO_MESSAGE_DELAY = 25
    DELETE_UNKNOWN_COMMAND_MESSAGE_DELAY = 10
    DELETE_ADMIN_REPLY_DELAY = 10
    DELETE_UNBAN_REQUEST_DELAY = 15


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