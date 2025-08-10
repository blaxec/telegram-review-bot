# file: final_main.py

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties # ИСПРАВЛЕНИЕ: Добавлен необходимый импорт
from config import BOT_TOKEN, ADMIN_IDS
from handlers import start, admin  # <-- Импортируем ТОЛЬКО start и admin

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN:
        logger.critical("!!! КРИТИЧЕСКАЯ ОШИБКА: Токен не найден в .env файле.")
        return

    # Создаем базовые объекты без лишних зависимостей
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    logger.info("="*50)
    logger.info("ЗАПУСК В РЕЖИМЕ ИЗОЛЯЦИИ. РЕГИСТРИРУЕМ ТОЛЬКО start И admin РОУТЕРЫ.")
    logger.info(f"Загруженные ID администраторов: {ADMIN_IDS}")
    logger.info("="*50)

    # Регистрируем только два самых важных роутера
    dp.include_router(start.router)
    dp.include_router(admin.router)
    
    # Удаляем старые обновления и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")