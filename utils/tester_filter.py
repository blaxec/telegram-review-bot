# file: telegram-review-bot-main/utils/tester_filter.py

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from typing import Union

from database import db_manager

class IsTester(Filter):
    """
    Проверяет, является ли пользователь, отправивший сообщение,
    тестировщиком, делая запрос к базе данных.
    """
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        user_id = obj.from_user.id
        # Пользователь считается тестером, если у него есть запись в таблице администраторов
        # и флаг is_tester установлен в True.
        admin_record = await db_manager.get_administrator(user_id)
        return admin_record is not None and admin_record.is_tester