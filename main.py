# file: main.py

import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from config import REDIS_HOST, REDIS_PORT, Durations
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent, Message, CallbackQuery
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ИЗМЕНЕНИЕ: Импортируем ADMIN_ID_1 напрямую для явного указания главного админа
from config import BOT_TOKEN, ADMIN_ID_1, ADMIN_IDS
from handlers import start, profile, support, earning, admin, gmail, stats, promo, other
from database import db_manager
from utils.antiflood import AntiFloodMiddleware
from utils.username_updater import UsernameUpdaterMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


# ИЗМЕНЕНИЕ: Логика функции полностью переписана для разделения команд
async def set_bot_commands(bot: Bot):
    # 1. Определяем базовый набор команд для всех пользователей (и для "Шадоу")
    user_commands = [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="stars", description="✨ Мой профиль и баланс"),
        BotCommand(command="promo", description="🎁 Ввести промокод")
    ]
    
    # 2. Определяем полный набор команд для главного админа ("Адам")
    admin_commands = user_commands + [
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="viewhold", description="⏳ Посмотреть холд пользователя"),
        BotCommand(command="reviewhold", description="🔍 Проверить отзывы в холде"),
        BotCommand(command="reset_cooldown", description="❄️ Сбросить кулдауны пользователю"),
        BotCommand(command="fine", description="💸 Выписать штраф пользователю"),
        BotCommand(command="create_promo", description="✨ Создать промокод")
    ]

    # 3. Устанавливаем команды по умолчанию для ВСЕХ пользователей.
    # Это гарантирует, что у "Шадоу" (ADMIN_ID_2) и обычных пользователей будет этот список.
    await bot.set_my_commands(user_commands)
    logger.info("Default user commands have been set.")

    # 4. Устанавливаем РАСШИРЕННЫЙ набор команд только для главного администратора ("Адам")
    # Эта настройка переопределит дефолтную только для его ID.
    if ADMIN_ID_1 != 0:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID_1))
            logger.info(f"Full admin commands have been set for the main admin (ID: {ADMIN_ID_1}).")
        except Exception as e:
            logger.error(f"Failed to set admin commands for main admin {ADMIN_ID_1}: {e}")
    else:
        logger.warning("Main admin ID (ADMIN_ID_1) is not set. Admin commands menu will not be displayed.")


async def handle_telegram_bad_request(event: ErrorEvent):
    if isinstance(event.exception, TelegramBadRequest) and ("query is too old" in event.exception.message or "query ID is invalid" in event.exception.message):
        logger.warning(f"Caught a 'query is too old' error. Ignoring. Update: {event.update}")
        return True
    logger.error(f"Unhandled exception in error handler: {event.exception.__class__.__name__}: {event.exception}")
    return False

async def main():
    if not BOT_TOKEN:
        logger.critical("Bot token is not found! Please check your .env file.")
        return

    await db_manager.init_db()
    
    storage = RedisStorage.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    logger.info("Using RedisStorage for FSM.")
    
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage, scheduler=scheduler)

    dp.update.outer_middleware(UsernameUpdaterMiddleware())

    # --- РЕГИСТРАЦИЯ РОУТЕРОВ ---
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)
    dp.include_router(earning.router)
    dp.include_router(promo.router)
    dp.include_router(admin.router)
    dp.include_router(gmail.router)
    dp.include_router(stats.router)
    
    # Роутер для "всего остального" регистрируется ПОСЛЕДНИМ
    dp.include_router(other.router)
    
    dp.errors.register(handle_telegram_bad_request)

    try:
        scheduler.start()
        await bot.delete_webhook(drop_pending_updates=True)
        await set_bot_commands(bot)
        logger.info("Bot is running and ready to process updates...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await dp.storage.close()
        await bot.session.close()
        scheduler.shutdown()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")