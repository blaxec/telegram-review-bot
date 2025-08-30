# file: telegram-review-bot-main/utils/tester_filter.py

from aiogram.filters import Filter
from aiogram.types import Message
from typing import Union

from config import TESTER_IDS

class IsTester(Filter):
    """
    Проверяет, является ли пользователь, отправивший сообщение,
    тестировщиком.
    """
    async def __call__(self, obj: Union[Message]) -> bool:
        # Проверяем, что у объекта есть поле from_user и у него есть id
        if hasattr(obj, 'from_user') and hasattr(obj.from_user, 'id'):
            return obj.from_user.id in TESTER_IDS
        return False