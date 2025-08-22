# file: handlers/other.py

import asyncio
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from config import Durations

# Создаем новый роутер специально для "прочих" обработчиков
router = Router()

@router.message()
async def handle_unknown_messages(message: Message):
    """
    Этот обработчик ловит ЛЮБЫЕ сообщения, которые не были пойманы
    другими, более специфичными обработчиками в других роутерах.
    """
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    
    response_msg = await message.answer(
        "😕 Не могу распознать вашу команду. Пожалуйста, используйте кнопки меню или команду /start для перезапуска."
    )
    
    async def delete_after_delay():
        await asyncio.sleep(Durations.DELETE_UNKNOWN_COMMAND_MESSAGE_DELAY)
        try:
            await response_msg.delete()
        except TelegramBadRequest:
            pass
    asyncio.create_task(delete_after_delay())

@router.callback_query()
async def handle_unknown_callbacks(callback: CallbackQuery):
    """
    Этот обработчик ловит ЛЮБЫЕ нажатия на инлайн-кнопки, которые
    не были пойманы другими обработчиками.
    """
    try:
        await callback.answer(
            "Эта кнопка больше не активна. Пожалуйста, воспользуйтесь меню.",
            show_alert=True
        )
    except TelegramBadRequest:
        pass