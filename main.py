# file: main.py

import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from config import BOT_TOKEN, ADMIN_ID_1, ADMIN_IDS, TESTER_IDS, Durations, REDIS_HOST, REDIS_PORT
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent, Message, BotCommandScopeDefault
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from handlers import (start, profile, support, earning, admin, gmail, 
                      stats, promo, other, ban_system, referral, admin_roles)
from database import db_manager
from utils.ban_middleware import BanMiddleware
from utils.username_updater import UsernameUpdaterMiddleware
from logic.reward_logic import distribute_rewards
from logic.cleanup_logic import check_and_expire_links, process_expired_holds

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
        BotCommand(command="roles", description="🛠️ Управление ролями админов"),
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="stat_rewards", description="🏆 Упр. наградами топа"),
        BotCommand(command="viewhold", description="⏳ Холд пользователя"),
        BotCommand(command="reviewhold", description="🔍 Проверить отзывы в холде"),
        BotCommand(command="reset_cooldown", description="❄️ Сбросить кулдауны"),
        BotCommand(command="fine", description="💸 Выписать штраф"),
        BotCommand(command="ban", description="🚫 Забанить"),
        BotCommand(command="unban", description="✅ Разбанить"),
        BotCommand(command="create_promo", description="✨ Создать промокод")
    ]

    tester_commands = user_commands + [
        BotCommand(command="skip", description="⚡️ [ТЕСТ] Пропустить таймер")
    ]
    
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    logger.info("Default user commands have been set for all users.")

    for admin_id in ADMIN_IDS:
        try:
            commands_to_set = admin_commands.copy()
            if admin_id == ADMIN_ID_1 and admin_id in TESTER_IDS:
                tester_only_commands = [cmd for cmd in tester_commands if cmd.command not in [ac.command for ac in commands_to_set]]
                commands_to_set.extend(tester_only_commands)
            
            await bot.set_my_commands(commands_to_set, scope=BotCommandScopeChat(chat_id=admin_id))
            logger.info(f"Admin commands set for admin ID: {admin_id}")
        except Exception as e:
            logger.error(f"Failed to set commands for admin {admin_id}: {e}")
            
    non_admin_testers = [tid for tid in TESTER_IDS if tid not in ADMIN_IDS]
    for tester_id in non_admin_testers:
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

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(admin_roles.router)
    dp.include_router(promo.router)
    dp.include_router(ban_system.router)
    dp.include_router(earning.router)
    dp.include_router(referral.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)
    dp.include_router(gmail.router)
    dp.include_router(stats.router)
    dp.include_router(other.router)
    
    dp.errors.register(handle_telegram_bad_request)

    scheduler.add_job(distribute_rewards, 'interval', minutes=30, args=[bot])
    scheduler.add_job(check_and_expire_links, 'interval', hours=6, args=[bot, dp.storage])
    scheduler.add_job(process_expired_holds, 'interval', minutes=1, args=[bot, dp.storage, scheduler])


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