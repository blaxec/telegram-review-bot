# file: main.py

import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from config import REDIS_HOST, REDIS_PORT, Durations, TESTER_IDS, ADMIN_IDS
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent, Message, BotCommandScopeDefault
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID_1
from handlers import start, profile, support, earning, admin, gmail, stats, promo, other, ban_system, referral
from database import db_manager
from utils.ban_middleware import BanMiddleware
from utils.username_updater import UsernameUpdaterMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """
    Устанавливает разные списки команд для админов, тестеров и обычных пользователей.
    """
    user_commands = [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="stars", description="✨ Мой профиль и баланс"),
        BotCommand(command="promo", description="🎁 Ввести промокод")
    ]
    
    admin_commands = user_commands + [
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="viewhold", description="⏳ Холд пользователя"),
        BotCommand(command="reviewhold", description="🔍 Проверить отзывы в холде"),
        BotCommand(command="reset_cooldown", description="❄️ Сбросить кулдауны"),
        BotCommand(command="fine", description="💸 Выписать штраф"),
        BotCommand(command="ban", description="🚫 Забанить"),
        BotCommand(command="unban", description="✅ Разбанить"),
        BotCommand(command="create_promo", description="✨ Создать промокод"),
        BotCommand(command="reward_top", description="🏆 Наградить топ пользователей")
    ]

    tester_commands = user_commands + [
        BotCommand(command="skip", description="⚡️ [ТЕСТ] Пропустить таймер")
    ]
    
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    logger.info("Default user commands have been set for all users.")

    for admin_id in ADMIN_IDS:
        try:
            commands_to_set = admin_commands
            if admin_id in TESTER_IDS:
                # Добавляем команду skip, если админ также является тестером, избегая дубликатов
                commands_to_set = admin_commands + [cmd for cmd in tester_commands if cmd not in admin_commands]
            
            await bot.set_my_commands(commands_to_set, scope=BotCommandScopeChat(chat_id=admin_id))
            logger.info(f"Admin commands set for admin ID: {admin_id}")
        except Exception as e:
            logger.error(f"Failed to set commands for admin {admin_id}: {e}")
            
    for tester_id in TESTER_IDS:
        if tester_id not in ADMIN_IDS:
            try:
                await bot.set_my_commands(tester_commands, scope=BotCommandScopeChat(chat_id=tester_id))
                logger.info(f"Tester commands set for tester ID: {tester_id}")
            except Exception as e:
                logger.error(f"Failed to set commands for tester {tester_id}: {e}")


async def handle_telegram_bad_request(event: ErrorEvent):
    if isinstance(event.exception, TelegramBadRequest) and ("query is too old" in event.exception.message or "query ID is invalid" in event.exception.message):
        logger.warning(f"Caught a 'query is too old' error. Ignoring. Update: {event.update}")
        return True
    if isinstance(event.exception, TelegramBadRequest) and "message is not modified" in event.exception.message:
        logger.warning("Caught 'message is not modified' error. Ignoring.")
        return True
        
    logger.error(f"Unhandled exception in error handler: {event.exception.__class__.__name__}: {event.exception}")
    return False

async def main():
    logger.warning("--- STARTING BOT: CHECKING IDs ---")
    logger.warning(f"ADMIN_IDS list: {ADMIN_IDS}")
    logger.warning(f"TESTER_IDS list: {TESTER_IDS}")
    logger.warning("----------------------------------")

    if not BOT_TOKEN:
        logger.critical("Bot token is not found! Please check your .env file.")
        return

    await db_manager.init_db()
    
    storage = RedisStorage.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    logger.info("Using RedisStorage for FSM.")
    
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage, scheduler=scheduler)

    dp.update.outer_middleware(BanMiddleware())
    dp.update.outer_middleware(UsernameUpdaterMiddleware())

    # --- НАЧАЛО ИЗМЕНЕНИЙ: ФИНАЛЬНЫЙ, ПРАВИЛЬНЫЙ ПОРЯДОК РЕГИСТРАЦИИ РОУТЕРОВ ---
    # 1. Сначала регистрируем роутеры, которые ловят КОМАНДЫ.
    # Это гарантирует, что /skip, /start и другие команды будут пойманы до того,
    # как сработают обработчики сообщений в состояниях.
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(promo.router)
    dp.include_router(ban_system.router)
    
    # 2. Роутер earning идет следующим, так как в нем есть команда /skip.
    dp.include_router(earning.router)
    
    # 3. Затем все остальные роутеры, которые в основном работают с состояниями (FSM) и колбэками.
    # Порядок между ними уже не так критичен.
    dp.include_router(referral.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)
    dp.include_router(gmail.router)
    dp.include_router(stats.router)
    
    # 4. Роутер "other" для отлова неизвестных команд ВСЕГДА ДОЛЖЕН БЫТЬ ПОСЛЕДНИМ.
    dp.include_router(other.router)
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
    
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