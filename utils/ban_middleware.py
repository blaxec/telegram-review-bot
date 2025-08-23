# file: utils/ban_middleware.py

import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database import db_manager

logger = logging.getLogger(__name__)

class BanMiddleware(BaseMiddleware):
    """
    Этот middleware проверяет при каждом событии, не забанен ли пользователь.
    Если пользователь забанен, он блокирует выполнение любых команд,
    кроме /unban_request.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Пытаемся получить объект пользователя из данных события
        user = data.get("event_from_user")
        
        # Если в событии нет информации о пользователе (редкий случай), пропускаем
        if not user:
            return await handler(event, data)
        
        # Получаем актуальную информацию о пользователе из базы данных
        db_user = await db_manager.get_user(user.id)
        
        # Проверяем, существует ли пользователь в базе и забанен ли он
        if db_user and db_user.is_banned:
            
            # Проверяем, является ли событие сообщением с командой /unban_request
            # Если да, то РАЗРЕШАЕМ его обработку, чтобы пользователь мог подать апелляцию
            if isinstance(event, Message) and event.text == "/unban_request":
                return await handler(event, data)
            
            # Если это любое другое действие от забаненного пользователя, БЛОКИРУЕМ его
            
            # Если это сообщение
            if isinstance(event, Message):
                await event.answer(
                    "Вы заблокированы и не можете использовать бота.\n"
                    "Для подачи запроса на амнистию используйте команду /unban_request"
                )
            # Если это нажатие на инлайн-кнопку
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("Доступ заблокирован.", show_alert=True)
                except:
                    # Игнорируем возможные ошибки, если колбэк устарел
                    pass

            # Возвращаем None, чтобы прервать дальнейшую обработку этого события
            return None 
            
        # Если пользователь не забанен, просто передаем управление следующему обработчику
        return await handler(event, data)