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

from config import BOT_TOKEN, REDIS_HOST, REDIS_PORT, ADMIN_ID_1
from handlers import routers_list
from database import db_manager
from utils.antiflood import AntiFloodMiddleware
from utils.blocking import BlockingMiddleware
from utils.username_updater import UsernameUpdaterMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def set_bot_commands(bot: Bot):
    """Устанавливает команды, которые будут видны в меню Telegram."""
    user_commands = [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="stars", description="✨ Мой профиль и баланс")
    ]
    await bot.set_my_commands(user_commands)

    admin_commands = user_commands + [
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="viewhold", description="⏳ Посмотреть холд юзера"),
        BotCommand(command="reviewhold", description="🔍 Проверить отзывы в холде"),
        BotCommand(command="reset_cooldown", description="❄️ Сбросить кулдауны юзеру")
    ]
    
    try:
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID_1))
    except Exception as e:
        logger.error(f"Failed to set admin commands for {ADMIN_ID_1}: {e}")

# --- НОВОЕ: Глобальный обработчик ошибок ---
async def handle_telegram_bad_request(event: ErrorEvent):
    """
    Перехватывает ошибки TelegramBadRequest, чтобы бот не падал из-за устаревших callback_query.
    """
    if isinstance(event.exception, TelegramBadRequest):
        # Проверяем текст ошибки
        if "query is too old" in event.exception.message or "query ID is invalid" in event.exception.message:
            logger.warning(f"Caught a 'query is too old' error. Ignoring update. Update: {event.update}")
            return True # Сообщаем диспетчеру, что ошибка обработана
    
    # Для всех остальных ошибок, позволяем им обрабатываться дальше (например, выводиться в лог как ERROR)
    logger.error(f"Unhandled exception caught in error handler: {event.exception}")
    return False


async def main():
    bot = None
    redis_client = None
    scheduler = None
    dp = None

    try:
        if not BOT_TOKEN:
            logger.critical("Bot token is not found! Please check your .env file.")
            return

        max_db_retries = 5
        db_retry_delay = 3
        for attempt in range(max_db_retries):
            try:
                logger.info(f"Attempting to connect to the database... (Attempt {attempt + 1}/{max_db_retries})")
                await db_manager.init_db()
                logger.info("Successfully connected to the database.")
                break
            except ConnectionRefusedError as e:
                logger.error(f"Database connection refused: {e}. PostgreSQL might still be starting. Retrying in {db_retry_delay} seconds...")
                if attempt < max_db_retries - 1:
                    time.sleep(db_retry_delay)
                else:
                    logger.critical("Failed to connect to the database after multiple retries. Exiting.")
                    return
        
        redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT)
        storage = RedisStorage(redis=redis_client)

        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        scheduler = AsyncIOScheduler(timezone="UTC")

        dp = Dispatcher(storage=storage)
        
        # --- НОВОЕ: Регистрация глобального обработчика ошибок ---
        dp.errors.register(handle_telegram_bad_request)

        dp.update.outer_middleware(UsernameUpdaterMiddleware())
        dp.message.middleware(AntiFloodMiddleware())
        dp.update.middleware(BlockingMiddleware()) # ИЗМЕНЕНО: Применяем ко всем update, а не только к message
        
        dp.include_routers(*routers_list)

        max_tg_retries = 5
        tg_retry_delay = 5
        for attempt in range(max_tg_retries):
            try:
                logger.info(f"Attempting to connect to Telegram API... (Attempt {attempt + 1}/{max_tg_retries})")
                await bot.delete_webhook(drop_pending_updates=True)
                await set_bot_commands(bot)
                logger.info("Successfully connected and set up bot commands.")
                break
            except TelegramNetworkError as e:
                logger.error(f"Network error on startup: {e}. Retrying in {tg_retry_delay} seconds...")
                if attempt < max_tg_retries - 1:
                    time.sleep(tg_retry_delay)
                    tg_retry_delay *= 2
                else:
                    logger.critical("Failed to connect to Telegram API after multiple retries. Exiting.")
                    return

        logger.info("Starting bot...")
        scheduler.start()

        await dp.start_polling(bot, scheduler=scheduler, dp=dp)

    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        logger.info("Bot polling cancelled.")
    except Exception as e:
        logger.exception("Unhandled exception in main(): %s", e)
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown()
        if dp and bot:
             await dp.storage.close()
        if bot and bot.session:
            await bot.session.close()
        if redis_client:
            await redis_client.aclose()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")