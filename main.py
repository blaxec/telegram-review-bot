# file: main.py

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging

# --- АГРЕССИВНАЯ ОТЛАДКА В САМОМ НАЧАЛЕ ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

logger.info("--- СКРИПТ main.py ЗАПУЩЕН ---")
bot_token_value = None
try:
    bot_token_value = os.getenv("BOT_TOKEN")
    if bot_token_value:
        logger.info(f"УСПЕХ: Переменная BOT_TOKEN успешно прочитана в Python. Длина токена: {len(bot_token_value)}.")
    else:
        logger.critical("!!! КРИТИЧЕСКАЯ ОШИБКА: Python не смог прочитать переменную BOT_TOKEN из окружения (os.getenv вернул None).")
except Exception as e:
    logger.critical(f"!!! КРИТИЧЕСКАЯ ОШИБКА: Произошло исключение при чтении BOT_TOKEN: {e}")
# --- КОНЕЦ ОТЛАДКИ ---


import asyncio
import time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
# Обратите внимание, что BOT_TOKEN теперь импортируется после проверки
from config import BOT_TOKEN, SUPER_ADMIN_ID, ADMIN_IDS, TESTER_IDS, Durations, REDIS_HOST, REDIS_PORT, PAYMENT_PROVIDER_TOKEN
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent, Message, BotCommandScopeDefault
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from handlers import (start, profile, support, earning, admin, gmail,
                      stats, promo, other, ban_system, referral, admin_roles, internship)
from database import db_manager
from utils.ban_middleware import BanMiddleware
from utils.username_updater import UsernameUpdaterMiddleware
from logic.reward_logic import distribute_rewards
from logic.cleanup_logic import check_and_expire_links, process_expired_holds


async def set_bot_commands(bot: Bot):
    """
    Устанавливает разные списки команд для админов, тестеров и обычных пользователей.
    """
    user_commands = [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="stars", description="✨ Мой профиль и баланс"),
        BotCommand(command="promo", description="🎁 Ввести промокод"),
        BotCommand(command="unban_request", description="🙏 Подать запрос на разбан")
    ]
    
    # Команды для ОБЫЧНЫХ администраторов
    admin_commands = user_commands + [
        BotCommand(command="dnd", description="🌙/☀️ Включить/выключить ночной режим"),
        BotCommand(command="pending_tasks", description="📥 Посмотреть задачи в очереди"),
        BotCommand(command="viewhold", description="⏳ Холд пользователя"),
        BotCommand(command="reset_cooldown", description="❄️ Сбросить кулдауны"),
        BotCommand(command="fine", description="💸 Выписать штраф"),
    ]

    # Команды для ГЛАВНОГО администратора (включают все команды обычного)
    super_admin_commands = admin_commands + [
        BotCommand(command="internships", description="🎓 Управление стажировками"),
        BotCommand(command="roles", description="🛠️ Управление ролями админов"),
        BotCommand(command="admin_refs", description="🔗 Управление ссылками"),
        BotCommand(command="stat_rewards", description="🏆 Упр. наградами топа"),
        BotCommand(command="amnesty", description="🙏 Список запросов на разбан"),
        BotCommand(command="banlist", description="📜 Список забаненных"),
        BotCommand(command="promolist", description="📝 Список промокодов"),
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
            if admin_id == SUPER_ADMIN_ID:
                commands_to_set = super_admin_commands.copy()
                if admin_id in TESTER_IDS:
                    tester_only_commands = [cmd for cmd in tester_commands if cmd.command not in [ac.command for ac in commands_to_set]]
                    commands_to_set.extend(tester_only_commands)
                await bot.set_my_commands(commands_to_set, scope=BotCommandScopeChat(chat_id=admin_id))
                logger.info(f"Super Admin commands set for admin ID: {admin_id}")
            else:
                commands_to_set = admin_commands.copy()
                if admin_id in TESTER_IDS:
                     tester_only_commands = [cmd for cmd in tester_commands if cmd.command not in [ac.command for ac in commands_to_set]]
                     commands_to_set.extend(tester_only_commands)
                await bot.set_my_commands(commands_to_set, scope=BotCommandScopeChat(chat_id=admin_id))
                logger.info(f"Regular Admin commands set for admin ID: {admin_id}")
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
    logger.info("--- Вход в функцию main() ---")

    if not BOT_TOKEN:
        logger.critical("!!! ПРОВЕРКА ВНУТРИ main(): BOT_TOKEN не найден! Завершение работы. !!!")
        return

    await db_manager.init_db()

    storage = RedisStorage.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0")

    scheduler = AsyncIOScheduler(timezone="UTC")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage, scheduler=scheduler)

    dp.update.outer_middleware(BanMiddleware())
    dp.update.outer_middleware(UsernameUpdaterMiddleware())

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(admin_roles.router)
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
    logger.info("--- Секция if __name__ == '__main__' ---")
    if not bot_token_value:
        logger.critical("!!! ПРОВЕРКА ПЕРЕД ЗАПУСКОМ: BOT_TOKEN не был прочитан. Запуск отменен. !!!")
    else:
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Бот остановлен пользователем (Ctrl+C).")