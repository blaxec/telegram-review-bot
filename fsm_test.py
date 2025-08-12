# file: fsm_test.py

import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Загружаем переменные из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Укажите ваш ID администратора прямо здесь для чистоты теста
ADMIN_ID = int(os.getenv("ADMIN_ID_1", 0))

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

# Определяем состояния прямо в файле
class TestStates(StatesGroup):
    waiting_for_message = State()

# Создаем диспетчер с MemoryStorage
dp = Dispatcher(storage=MemoryStorage())

# --- Обработчики ---

@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def start_test(message: Message):
    """Отправляет кнопку для начала теста."""
    kb = [[InlineKeyboardButton(text="Нажми меня, чтобы установить состояние", callback_data="set_state")]]
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    await message.answer("Тест FSM. Нажмите кнопку ниже.", reply_markup=markup)

@dp.callback_query(F.data == "set_state", F.from_user.id == ADMIN_ID)
async def set_state_handler(callback: CallbackQuery, state: FSMContext):
    """Устанавливает состояние и сообщает об этом."""
    await state.set_state(TestStates.waiting_for_message)
    current_state = await state.get_state()
    await callback.message.answer(f"✅ Состояние установлено: `{current_state}`. Теперь отправьте любое сообщение.")
    await callback.answer()
    logging.info(f"--- FSM state set to: {current_state} for user {callback.from_user.id} ---")

@dp.message(F.state == TestStates.waiting_for_message, F.from_user.id == ADMIN_ID)
async def message_in_state_handler(message: Message, state: FSMContext):
    """Ловит сообщение, если состояние было установлено ПРАВИЛЬНО."""
    current_state = await state.get_state()
    await message.answer(
        f"🎉 ПОБЕДА! Сообщение поймано в состоянии: `{current_state}`.\n"
        f"Это значит, что FSM работает."
    )
    await state.clear()

@dp.message(F.from_user.id == ADMIN_ID)
async def catch_all_admin_messages(message: Message, state: FSMContext):
    """Ловит сообщение админа, если оно НЕ попало в обработчик выше."""
    current_state = await state.get_state()
    await message.answer(
        f"❌ ПРОВАЛ. Сообщение НЕ было поймано в нужном состоянии.\n"
        f"Текущее состояние, которое видит бот: `{current_state}`."
    )
    logging.warning(f"--- FAILED. Message from {message.from_user.id} was not caught. Current state is: {current_state} ---")

async def main():
    if not BOT_TOKEN or ADMIN_ID == 0:
        logging.critical("Не найден BOT_TOKEN или ADMIN_ID_1 в .env файле!")
        return
        
    logging.info(f"Запуск стерильного теста для админа с ID: {ADMIN_ID}")
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())