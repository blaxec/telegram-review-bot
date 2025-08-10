# file: final_main.py

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis

from config import BOT_TOKEN, ADMIN_IDS, REDIS_HOST, REDIS_PORT
from database import db_manager
from handlers import start, admin

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN:
        logger.critical("!!! КРИТИЧЕСКАЯ ОШИБКА: Токен не найден в .env файле.")
        return

    # --- ВОЗВРАЩАЕМ ПОДКЛЮЧЕНИЕ К ХРАНИЛИЩАМ ---
    try:
        await db_manager.init_db()
        logger.info("Успешное подключение к базе данных PostgreSQL.")
    except Exception as e:
        logger.critical(f"!!! ОШИБКА ПОДКЛЮЧЕНИЯ К POSTGRESQL: {e}")
        return
        
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT)
    storage = RedisStorage(redis=redis_client)
    logger.info("Успешное подключение к Redis.")
    # -----------------------------------------------

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage) # <-- Передаем хранилище в диспетчер

    logger.info("="*50)
    logger.info("ЗАПУСК. ЭТАП 1: FSM и База данных активны.")
    logger.info(f"Загруженные ID администраторов: {ADMIN_IDS}")
    logger.info("="*50)

    dp.include_router(start.router)
    dp.include_router(admin.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")