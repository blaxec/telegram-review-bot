# file: telegram-review-bot-main/utils/access_filters.py

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from typing import Union

from config import ADMIN_IDS, SUPER_ADMIN_ID

class IsAdmin(Filter):
    """
    Проверяет, является ли пользователь администратором (обычным или главным).
    """
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        if hasattr(obj, 'from_user') and hasattr(obj.from_user, 'id'):
            return obj.from_user.id in ADMIN_IDS
        return False

class IsSuperAdmin(Filter):
    """
    Проверяет, является ли пользователь Главным администратором.
    """
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        if hasattr(obj, 'from_user') and hasattr(obj.from_user, 'id'):
            return obj.from_user.id == SUPER_ADMIN_ID
        return False