# file: main.py

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, REDIS_HOST, REDIS_PORT
from handlers import routers_list
from database import db_manager
from utils.antiflood import AntiFloodMiddleware
from utils.blocking import BlockingMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    bot = None
    redis_client = None
    scheduler = None
    dp = None

    try:
        if not BOT_TOKEN:
            logger.critical("Bot token is not found! Please check your .env file.")
            return

        await db_manager.init_db()
        redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT)
        storage = RedisStorage(redis=redis_client)

        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        scheduler = AsyncIOScheduler(timezone="UTC")

        dp = Dispatcher(storage=storage)

        # Middleware регистрируются в том порядке, в котором должны срабатывать
        dp.message.middleware(AntiFloodMiddleware())
        dp.message.middleware(BlockingMiddleware())
        # Блокировка для callback'ов не нужна, т.к. прерывающие команды - текстовые
        
        dp.include_routers(*routers_list)

        logger.info("Starting bot...")
        await bot.delete_webhook(drop_pending_updates=True)
        scheduler.start()

        await dp.start_polling(bot, scheduler=scheduler, dp=dp)
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