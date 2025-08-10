# file: test_main.py

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
import os

# Загружаем переменные из .env файла
load_dotenv()

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)

# Получаем токен и ID админов
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1", 0))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", 0))
ADMINS = [ADMIN_ID_1, ADMIN_ID_2]

# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ТЕСТОВЫЕ ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def test_start(message: Message):
    """Проверяет, что бот в принципе отвечает."""
    await message.answer(f"Минимальный бот работает! Ваш ID: {message.from_user.id}")

@dp.message(Command("admintest"), F.from_user.id.in_(ADMINS))
async def test_admin_command(message: Message):
    """Проверяет, что фильтр админа работает."""
    await message.answer("✅ Вы успешно прошли проверку как администратор!")
    
@dp.message()
async def catch_all(message: Message):
    """Ловит все, что не подошло выше."""
    await message.answer(f"Сообщение поймано, но не обработано. Проверьте команду.\nВаш ID: {message.from_user.id}")


async def main():
    print("="*50)
    print(f"Запуск минимального бота...")
    print(f"Токен найден: {'Да' if BOT_TOKEN else 'Нет'}")
    print(f"Загруженные ID администраторов: {ADMINS}")
    print("="*50)
    
    if not BOT_TOKEN:
        print("!!! КРИТИЧЕСКАЯ ОШИБКА: Токен не найден в .env файле.")
        return
        
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())