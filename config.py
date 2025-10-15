#file: config.py
import os
import logging
from urllib.parse import urlparse
from datetime import timedelta
logger = logging.getLogger(name)
#--- Основные настройки бота и ролей ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
#ID Главного Администратора (полный доступ)
#Используется для эксклюзивных команд и как получатель критических уведомлений
ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1") or 0)
SUPER_ADMIN_ID = ADMIN_ID_1 # Создаем псевдоним для нового кода с фильтрами
#ID второго администратора (если есть) для ролей по умолчанию
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2") or 0)
#СПИСОК ВСЕХ АДМИНИСТРАТОРОВ (включая главного) для общей логики
#Сначала берем ID из ADMIN_IDS, если их нет, формируем из ADMIN_ID_1 и ADMIN_ID_2
#ЭТИ СПИСКИ СТАНУТ УСТАРЕВШИМИ ПОСЛЕ ПЕРЕХОДА НА ДИНАМИЧЕСКИЕ РОЛИ,
#НО ОСТАВЛЕНЫ ДЛЯ ПЕРВОНАЧАЛЬНОЙ СИНХРОНИЗАЦИИ
ADMIN_IDS_STR = os.getenv("ADMIN_IDS")
if ADMIN_IDS_STR:
    ADMIN_IDS = [int(admin_id) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip().isdigit()]
else:
    ADMIN_IDS = [admin_id for admin_id in [ADMIN_ID_1, ADMIN_ID_2] if admin_id != 0]
#Гарантируем, что главный админ всегда в списке ADMIN_IDS
if ADMIN_ID_1 and ADMIN_ID_1 not in ADMIN_IDS:
    ADMIN_IDS.insert(0, ADMIN_ID_1)
#ID Тестировщиков для команды /skip (также станет устаревшим)
TESTER_IDS_STR = os.getenv("TESTER_IDS", "")
TESTER_IDS = [int(tester_id) for tester_id in TESTER_IDS_STR.split(',') if tester_id.strip().isdigit()]
#ID канала, куда будут отправляться заявки на вывод
WITHDRAWAL_CHANNEL_ID = int(os.getenv("WITHDRAWAL_CHANNEL_ID") or 0)
#--- Роли администраторов по умолчанию (останутся для системы ролей) ---
class Defaults:
    DEFAULT_SCREENSHOT_CHECK_ADMIN = ADMIN_ID_1
    DEFAULT_TEXT_PROVIDER_ADMIN = ADMIN_ID_1
    DEFAULT_FINAL_VERDICT_ADMIN = ADMIN_ID_2 if ADMIN_ID_2 else ADMIN_ID_1
#--- Ключи для внешних API ---
GOOGLE_API_KEY_1 = os.getenv("GOOGLE_API_KEY_1")
GOOGLE_API_KEY_2 = os.getenv("GOOGLE_API_KEY_2")
GOOGLE_API_KEYS = [key for key in [GOOGLE_API_KEY_1, GOOGLE_API_KEY_2] if key]
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama3-70b-8192")
#--- ПАРАМЕТРЫ ПЛАТНОГО РАЗБАНА ---
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
PAID_UNBAN_COST_STARS = int(os.getenv("PAID_UNBAN_COST_STARS") or 1)
if not GOOGLE_API_KEYS:
    logger.warning("!!! КОНФИГУРАЦИЯ: Не найдены GOOGLE_API_KEY_1 и GOOGLE_API_KEY_2 в .env файле.")
    logger.warning("!!! Функция автоматической проверки скриншотов (OCR) будет отключена.")
if WITHDRAWAL_CHANNEL_ID > 0:
    logger.warning(f"!!! КОНФИГУРАЦИЯ: WITHDRAWAL_CHANNEL_ID ({WITHDRAWAL_CHANNEL_ID}) является положительным числом.")
    logger.warning("!!! Для приватных каналов ID должен быть отрицательным и начинаться с -100.")
    logger.warning("!!! Бот, скорее всего, не сможет отправлять сообщения в канал. Пожалуйста, проверьте ID.")
if not PAYMENT_PROVIDER_TOKEN:
    logger.warning("!!! КОНФИГУРАЦИЯ: Не найден PAYMENT_PROVIDER_TOKEN в .env файле.")
    logger.warning("!!! Функция платного разбана будет недоступна (или будет работать в режиме заглушки).")
#--- Награды (в звездах) ---
class Rewards:
# Устаревшие награды, будут заменены динамическими
    GOOGLE_REVIEW = 15.0
    YANDEX_WITH_TEXT = 50.0
    YANDEX_WITHOUT_TEXT = 15.0
    GMAIL_ACCOUNT = 5.0
    ADMIN_ADD_STARS = 999.0
# Реферальные награды (теперь в процентах, эти значения устарели)
    REFERRAL_REWARD_PERCENT = 10.0 # 10%
    REFERRAL_GOOGLE_REVIEW = 0.45 
    GMAIL_FOR_REFERRAL_USER = 4.5
    REFERRAL_GMAIL_ACCOUNT = 0.5
    REFERRAL_YANDEX_WITH_TEXT = 1.2
    REFERRAL_YANDEX_WITHOUT_TEXT = 0.6

    TOP_USER_REWARDS = {
    1: 50.0,
    2: 30.0,
    3: 15.0}
#--- Длительности и тайминги ---
class Durations:
    HOLD_GOOGLE_MINUTES = 5
    HOLD_YANDEX_WITH_TEXT_MINUTES = 24 * 60
    HOLD_YANDEX_WITHOUT_TEXT_MINUTES = 72 * 60
    HOLD_TESTER_MINUTES = 1
    COOLDOWN_GOOGLE_REVIEW_HOURS = 5 / 60
    COOLDOWN_YANDEX_WITH_TEXT_HOURS = 5 / 60
    COOLDOWN_YANDEX_WITHOUT_TEXT_HOURS = 5 / 60
    COOLDOWN_GMAIL_HOURS = 24
    COOLDOWN_WARNING_BLOCK_HOURS = 24
    COOLDOWN_UNBAN_REQUEST_MINUTES = 30
    CONFIRMATION_TIMEOUT_MINUTES = 30
    TASK_GOOGLE_LIKING_TIMEOUT = 10
    TASK_GOOGLE_LIKING_CONFIRM_APPEARS = 5
    TASK_GOOGLE_REVIEW_TIMEOUT = 17
    TASK_GOOGLE_REVIEW_CONFIRM_APPEARS = 5
    TASK_YANDEX_LIKING_TIMEOUT = 10
    TASK_YANDEX_LIKING_CONFIRM_APPEARS = 5
    TASK_YANDEX_REVIEW_TIMEOUT = 25
    TASK_YANDEX_REVIEW_CONFIRM_APPEARS = 10
    TASK_GMAIL_VERIFICATION_TIMEOUT = 5
    AWAIT_ADMIN_TEXT_TIMEOUT_MINUTES = 60
    DELETE_WELCOME_MESSAGE_DELAY = 15
    DELETE_INFO_MESSAGE_DELAY = 25
    DELETE_UNKNOWN_COMMAND_MESSAGE_DELAY = 10
    DELETE_ADMIN_REPLY_DELAY = 10
    DELETE_UNBAN_REQUEST_DELAY = 15
    SCREENSHOT_SUBMIT_TIMEOUT_MINUTES = 5 # Новый таймер
#--- Лимиты и пороги ---
class Limits:
    MIN_WITHDRAWAL_AMOUNT = 15.0
    MIN_TRANSFER_AMOUNT = 10.0
    WARNINGS_THRESHOLD_FOR_BAN = 3
    LINKS_PER_PAGE = 10
#--- Экономика и игры ---
    TRANSFER_COMMISSION_PERCENT = float(os.getenv("TRANSFER_COMMISSION_PERCENT") or 5.0)
    STAKE_THRESHOLD_REWARD = 50.0
    STAKE_AMOUNT = 5.0
    NOVICE_HELP_AMOUNT = 0.5
#--- Депозитные планы ---
DEPOSIT_PLANS = {
"starter": {
"name": "Стартовый",
"rate_percent": 1.0,
"period_hours": 12,
"duration_days": 3,
"min_amount": 10.0,
"description": "+1% каждые 12 часов в течение 3 дней (неотзывной)"
},
"pro": {
"name": "Профессионал",
"rate_percent": 2.0,
"period_hours": 8,
"duration_days": 5,
"min_amount": 100.0,
"description": "+2% каждые 8 часов в течение 5 дней (неотзывной)"
},
"investor": {
"name": "Инвестор",
"rate_percent": 3.0,
"period_hours": 24,
"duration_days": 4,
"min_amount": 500.0,
"description": "+3% каждые 24 часа в течение 4 дней (неотзывной)"
}
}
#Категории для AI сценариев
AI_SCENARIO_CATEGORIES = ["Кафе/Ресторан", "Автосервис", "Салон красоты", "Общее"]
#--- Настройки подключения к базам данных ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS", "password")
    DB_HOST = os.getenv("DB_HOST", "postgres_db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "telegram_bot_db")
    DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
elif DATABASE_URL.startswith("postgres://"):
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
    REDIS_PORT = int(os.getenv("REDIS_PORT") or 6379)