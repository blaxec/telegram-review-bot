# file: utils/username_updater.py

import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database import db_manager

logger = logging.getLogger(__name__)

class UsernameUpdaterMiddleware(BaseMiddleware):
    """
    Этот middleware проверяет при каждом сообщении или колбэке,
    не изменился ли юзернейм пользователя, и обновляет его в базе данных.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Пытаемся получить пользователя из события
        user = data.get("event_from_user")
        
        if user:
            # Получаем текущий юзернейм из базы
            db_user = await db_manager.get_user(user.id)
            
            # Сравниваем юзернейм из Telegram с тем, что в базе
            # Учитываем случаи, когда юзернейм добавляется или удаляется (становится None)
            if db_user and db_user.username != user.username:
                logger.info(f"Username changed for user {user.id}: from '{db_user.username}' to '{user.username}'. Updating DB.")
                await db_manager.update_username(user.id, user.username)

        return await handler(event, data)