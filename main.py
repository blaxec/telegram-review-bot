# file: main.py

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

logger.info("--- СКРИПТ main.py ЗАПУЩЕН ---")

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from config import BOT_TOKEN, SUPER_ADMIN_ID, ADMIN_ID_1, ADMIN_ID_2, REDIS_HOST, REDIS_PORT
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent, BotCommandScopeDefault
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from handlers import (start, profile, support, earning, admin, gmail,
                      stats, promo, other, ban_system, referral, admin_roles, internship, posting) # ДОБАВЛЕН posting
from database import db_manager
from utils.ban_middleware import BanMiddleware
from utils.username_updater import UsernameUpdaterMiddleware
from logic.reward_logic import distribute_rewards
from logic.cleanup_logic import check_and_expire_links, process_expired_holds


async def sync_base_admins():
    """
    Синхронизирует базовых администраторов из config.py с базой данных
    при старте бота, чтобы гарантировать их наличие.
    """
    logger.info("Syncing base administrators from config to database...")
    if ADMIN_ID_1:
        admin1 = await db_manager.get_administrator(ADMIN_ID_1)
        if not admin1:
            await db_manager.add_administrator(
                user_id=ADMIN_ID_1,
                role='super_admin',
                is_tester=False, # По умолчанию не тестер
                added_by=0, # Системное добавление
                is_removable=False # Нельзя удалить
            )
            logger.info(f"Added non-removable super_admin from config: {ADMIN_ID_1}")

    if ADMIN_ID_2 and ADMIN_ID_2 != 0:
        admin2 = await db_manager.get_administrator(ADMIN_ID_2)
        if not admin2:
            await db_manager.add_administrator(
                user_id=ADMIN_ID_2,
                role='admin',
                is_tester=False,
                added_by=0,
                is_removable=False
            )
            logger.info(f"Added non-removable admin from config: {ADMIN_ID_2}")
    logger.info("Base administrators sync complete.")


async def set_bot_commands(bot: Bot):
    """
    Устанавливает списки команд для всех ролей пользователей.
    """
    user_commands = [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="stars", description="✨ Мой профиль и баланс"),
        BotCommand(command="promo", description="🎁 Ввести промокод"),
        BotCommand(command="unban_request", description="🙏 Подать запрос на разбан")
    ]
    
    admin_commands = user_commands + [
        BotCommand(command="dnd", description="🌙/☀️ Включить/выключить ночной режим"),
        BotCommand(command="pending_tasks", description="📥 Посмотреть задачи в очереди"),
    ]

    super_admin_commands = admin_commands + [
        BotCommand(command="panel", description="🛠️ Панель управления утилитами"), # ИЗМЕНЕНО
        BotCommand(command="posts", description="📮 Система рассылок"), # НОВАЯ
        BotCommand(command="roles_manage", description="👥 Управление админами"), # НОВАЯ
        BotCommand(command="internships", description="🎓 Управление стажировками"),
        BotCommand(command="roles", description="🛠️ Распределение ролей"),
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="stat_rewards", description="🏆 Упр. наградами топа"),
        BotCommand(command="amnesty", description="🙏 Запросы на разбан"),
        BotCommand(command="banlist", description="📜 Список забаненных"),
        BotCommand(command="promolist", description="📝 Список промокодов"),
    ]

    tester_commands = user_commands + [
        BotCommand(command="skip", description="⚡️ [ТЕСТ] Пропустить таймер")
    ]

    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    logger.info("Default user commands have been set for all users.")

    all_admins = await db_manager.get_all_administrators_by_role()
    for admin in all_admins:
        try:
            if admin.role == 'super_admin':
                commands_to_set = super_admin_commands.copy()
                if admin.is_tester:
                    tester_only_commands = [cmd for cmd in tester_commands if cmd.command not in [ac.command for ac in commands_to_set]]
                    commands_to_set.extend(tester_only_commands)
                await bot.set_my_commands(commands_to_set, scope=BotCommandScopeChat(chat_id=admin.user_id))
                logger.info(f"Super Admin commands set for admin ID: {admin.user_id}")
            else: # role == 'admin'
                commands_to_set = admin_commands.copy()
                if admin.is_tester:
                     tester_only_commands = [cmd for cmd in tester_commands if cmd.command not in [ac.command for ac in commands_to_set]]
                     commands_to_set.extend(tester_only_commands)
                await bot.set_my_commands(commands_to_set, scope=BotCommandScopeChat(chat_id=admin.user_id))
                logger.info(f"Regular Admin commands set for admin ID: {admin.user_id}")
        except Exception as e:
            logger.error(f"Failed to set commands for admin {admin.user_id}: {e}")
    

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
    logger.info("--- Вход в функцию main() ---")

    if not BOT_TOKEN:
        logger.critical("!!! BOT_TOKEN не найден! Завершение работы. !!!")
        return

    await db_manager.init_db()
    await sync_base_admins() # Синхронизация админов при старте

    storage = RedisStorage.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    scheduler = AsyncIOScheduler(timezone="UTC")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage, scheduler=scheduler)

    dp.update.outer_middleware(BanMiddleware())
    dp.update.outer_middleware(UsernameUpdaterMiddleware())

    # Подключение роутеров
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(admin_roles.router)
    dp.include_router(posting.router) # НОВЫЙ РОУТЕР
    dp.include_router(internship.router)
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
        logger.info("--- ЗАПУСК ПОЛЛИНГА ---")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await dp.storage.close()
        await bot.session.close()
        scheduler.shutdown()
        logger.info("--- БОТ ОСТАНОВЛЕН ---")


if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.critical("!!! BOT_TOKEN не был прочитан. Запуск отменен. !!!")
    else:
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Бот остановлен пользователем (Ctrl+C).")