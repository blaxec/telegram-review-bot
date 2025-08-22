# file: handlers/other.py

import asyncio
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from config import Durations

router = Router()

async def handle_unknown_messages(message: Message):
    """Ловит все сообщения, которые не были обработаны другими хэндлерами."""
    try:
        # Сначала пробуем удалить сообщение пользователя
        await message.delete()
    except TelegramBadRequest:
        # Если не получилось (например, нет прав), просто продолжаем
        pass
    
    # Отправляем ответное сообщение
    response_msg = await message.answer(
        "😕 Не могу распознать вашу команду. Пожалуйста, используйте кнопки меню или команду /start для перезапуска."
    )
    
    # Планируем удаление ответного сообщения через некоторое время
    async def delete_after_delay():
        await asyncio.sleep(Durations.DELETE_UNKNOWN_COMMAND_MESSAGE_DELAY)
        try:
            await response_msg.delete()
        except TelegramBadRequest:
            pass
    asyncio.create_task(delete_after_delay())

async def handle_unknown_callbacks(callback: CallbackQuery):
    """Ловит все колбэки от устаревших или неработающих кнопок."""
    try:
        await callback.answer(
            "Эта кнопка больше не активна. Пожалуйста, воспользуйтесь меню.",
            show_alert=True
        )
    except TelegramBadRequest:
        pass

# РЕГИСТРАЦИЯ УНИВЕРСАЛЬНЫХ ОБРАБОТЧИКОВ В ЛОКАЛЬНОМ РОУТЕРЕ
# Эти хендлеры будут срабатывать только если сообщение/колбэк
# не был обработан ни в одном из роутеров, подключенных РАНЕЕ в main.py
router.message.register(handle_unknown_messages)
router.callback_query.register(handle_unknown_callbacks)