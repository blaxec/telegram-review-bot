# file: telegram-review-bot-main/utils/access_filters.py

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from typing import Union

# УДАЛЯЕМ ИМПОРТЫ ИЗ CONFIG
# from config import ADMIN_IDS, SUPER_ADMIN_ID, TESTER_IDS
from database import db_manager

class IsAdmin(Filter):
    """
    Проверяет, является ли пользователь администратором (обычным или главным),
    делая запрос к базе данных.
    """
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        user_id = obj.from_user.id
        admin = await db_manager.get_administrator(user_id)
        # Доступ есть, если запись существует (роль 'admin' или 'super_admin')
        return admin is not None

class IsSuperAdmin(Filter):
    """
    Проверяет, является ли пользователь Главным администратором,
    делая запрос к базе данных.
    """
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        user_id = obj.from_user.id
        admin = await db_manager.get_administrator(user_id)
        # Доступ есть, только если запись существует И роль 'super_admin'
        return admin is not None and admin.role == 'super_admin'

class IsTester(Filter):
    """
    Проверяет, является ли пользователь тестером,
    делая запрос к базе данных.
    """
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        user_id = obj.from_user.id
        admin = await db_manager.get_administrator(user_id)
        # Доступ есть, только если запись существует И флаг is_tester установлен в True
        return admin is not None and admin.is_tester