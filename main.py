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

from config import BOT_TOKEN, ADMIN_IDS
# ИЗМЕНЕНИЕ: Добавлен импорт нового роутера 'other'
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


async def set_bot_commands(bot: Bot):
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
        except Exception as e:
            logger.error(f"Failed to set admin commands for {admin_id}: {e}")

async def handle_telegram_bad_request(event: ErrorEvent):
    if isinstance(event.exception, TelegramBadRequest) and ("query is too old" in event.exception.message or "query ID is invalid" in event.exception.message):
        logger.warning(f"Caught a 'query is too old' error. Ignoring. Update: {event.update}")
        return True
    logger.error(f"Unhandled exception in error handler: {event.exception.__class__.__name__}: {event.exception}")
    return False

# ИЗМЕНЕНИЕ: Удалены функции handle_unknown_messages и handle_unknown_callbacks, 
# так как они перенесены в handlers/other.py

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
    # Сначала регистрируем все роутеры с конкретными командами
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)
    dp.include_router(earning.router)
    dp.include_router(promo.router)
    dp.include_router(admin.router)
    dp.include_router(gmail.router)
    dp.include_router(stats.router)
    
    # ИЗМЕНЕНИЕ: Удалена прямая регистрация универсальных обработчиков
    # dp.message.register(handle_unknown_messages)
    # dp.callback_query.register(handle_unknown_callbacks)
    
    # ИЗМЕНЕНИЕ: Роутер для "всего остального" регистрируется ПОСЛЕДНИМ
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