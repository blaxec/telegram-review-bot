import os
from dotenv import load_dotenv
from urllib.parse import urlparse

# Загружаем переменные из файла .env в окружение
load_dotenv()

# --- Конфигурация бота и администраторов ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1", 6127982184))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", 7205028708))
ADMIN_IDS = [ADMIN_ID_1, ADMIN_ID_2]

# Главный администратор, получающий все уведомления и проверки
FINAL_CHECK_ADMIN = ADMIN_ID_1


# --- Конфигурация подключения к базе данных PostgreSQL ---

# Сначала пытаемся получить полную строку подключения DATABASE_URL из .env
# Это полезно для развертывания на хостингах типа Heroku
DATABASE_URL = os.getenv("DATABASE_URL")

# Если переменной DATABASE_URL нет, собираем ее из отдельных компонентов.
# Это стандартный сценарий для локальной разработки с Docker.
if not DATABASE_URL:
    # Получаем каждый параметр из .env. Если его там нет, используем значение по умолчанию.
    # Значения по умолчанию ("postgres", "password", "localhost" и т.д.)
    # соответствуют тем, что указаны в docker-compose.yml
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "telegram_bot_db")
    
    # Формируем полную строку подключения для SQLAlchemy
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


# Асинхронный драйвер asyncpg, который мы используем, требует, чтобы
# строка подключения начиналась с "postgresql+asyncpg://".
# Этот блок кода проверяет текущую строку и корректно заменяет префикс,
# если это необходимо, для совместимости с SQLAlchemy 2.0.
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        # Эта проверка на случай, если пользователь уже указал "postgresql://"
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


# --- Конфигурация подключения к Redis ---

# Аналогично PostgreSQL, сначала ищем полную строку REDIS_URL
REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    # Если полная строка есть, парсим ее, чтобы извлечь хост и порт
    redis_parsed_url = urlparse(REDIS_URL)
    REDIS_HOST = redis_parsed_url.hostname
    REDIS_PORT = redis_parsed_url.port
else:
    # Если полной строки нет, берем хост и порт из отдельных переменных .env
    # или используем значения по умолчанию для локального Docker
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))