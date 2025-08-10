# file: main.py

import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from redis.asyncio.client import Redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, REDIS_HOST, REDIS_PORT, ADMIN_IDS
from handlers import routers_list
from database import db_manager
from utils.antiflood import AntiFloodMiddleware
from utils.username_updater import UsernameUpdaterMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """Устанавливает команды, которые будут видны в меню Telegram."""
    user_commands = [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="stars", description="✨ Мой профиль и баланс"),
        BotCommand(command="promo", description="🎁 Ввести промокод")
    ]
    await bot.set_my_commands(user_commands)

    admin_commands = user_commands + [
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="viewhold", description="⏳ Посмотреть холд пользователя"),
        BotCommand(command="reviewhold", description="🔍 Проверить отзывы в холде"),
        BotCommand(command="reset_cooldown", description="❄️ Сбросить кулдауны пользователю"),
        BotCommand(command="fine", description="💸 Выписать штраф пользователю"),
        BotCommand(command="create_promo", description="✨ Создать промокод")
    ]

    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
            logger.info(f"Admin commands have been set for admin ID: {admin_id}")
        except Exception as e:
            logger.error(f"Failed to set admin commands for {admin_id}: {e}")


async def handle_telegram_bad_request(event: ErrorEvent):
    if isinstance(event.exception, TelegramBadRequest):
        if "query is too old" in event.exception.message or "query ID is invalid" in event.exception.message:
            logger.warning(f"Caught a 'query is too old' error. Ignoring update. Update: {event.update}")
            return True
    
    logger.error(f"Unhandled exception in error handler: {event.exception.__class__.__name__}: {event.exception}")
    return False


async def main():
    if not BOT_TOKEN:
        logger.critical("Bot token is not found! Please check your .env file.")
        return

    # --- Подключение к БД с ретраями ---
    max_db_retries = 5
    db_retry_delay = 3
    for attempt in range(max_db_retries):
        try:
            logger.info(f"Attempting to connect to the database... (Attempt {attempt + 1}/{max_db_retries})")
            await db_manager.init_db()
            logger.info("Successfully connected to the database.")
            break
        except ConnectionRefusedError as e:
            logger.error(f"Database connection refused: {e}. Retrying in {db_retry_delay} seconds...")
            if attempt < max_db_retries - 1:
                time.sleep(db_retry_delay)
            else:
                logger.critical("Failed to connect to the database after multiple retries. Exiting.")
                return
    
    # --- Инициализация зависимостей ---
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT)
    storage = RedisStorage(redis=redis_client)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # --- Создание и конфигурация Dispatcher ---
    # ИСПРАВЛЕНИЕ: Передаем зависимости в диспетчер ПРАВИЛЬНЫМ способом
    dp = Dispatcher(storage=storage, scheduler=scheduler)

    # Регистрация middleware
    dp.update.outer_middleware(UsernameUpdaterMiddleware())
    dp.message.middleware(AntiFloodMiddleware())
    
    # Регистрация роутеров
    dp.include_routers(*routers_list)
    
    # Регистрация обработчика ошибок
    dp.errors.register(handle_telegram_bad_request)

    # --- Запуск бота ---
    try:
        scheduler.start()
        await bot.delete_webhook(drop_pending_updates=True)
        await set_bot_commands(bot)
        logger.info("Bot is running and ready to process updates...")
        
        # ИСПРАВЛЕНИЕ: Используем стандартный, стабильный вызов start_polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    finally:
        await dp.storage.close()
        await bot.session.close()
        scheduler.shutdown()
        await redis_client.aclose()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")