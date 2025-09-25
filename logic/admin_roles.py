# file: logic/admin_roles.py

import logging
from typing import List, Optional
from aiogram import Bot
from config import SUPER_ADMIN_ID, ADMIN_ID_1, ADMIN_IDS
from database import db_manager

logger = logging.getLogger(__name__)

# --- Константы для ключей в БД ---
YANDEX_TEXT_PROFILE_CHECK_ADMIN = "yandex_text_profile_check_admin"
YANDEX_TEXT_ISSUE_TEXT_ADMIN = "yandex_text_issue_text_admin"
YANDEX_TEXT_FINAL_CHECK_ADMIN = "yandex_text_final_check_admin"

YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN = "yandex_no_text_profile_check_admin"
YANDEX_NO_TEXT_FINAL_CHECK_ADMIN = "yandex_no_text_final_check_admin"

GOOGLE_PROFILE_CHECK_ADMIN = "google_profile_check_admin"
GOOGLE_LAST_REVIEWS_CHECK_ADMIN = "google_last_reviews_check_admin"
GOOGLE_ISSUE_TEXT_ADMIN = "google_issue_text_admin"
GOOGLE_FINAL_CHECK_ADMIN = "google_final_check_admin"

GMAIL_DEVICE_MODEL_CHECK_ADMIN = "gmail_device_model_check_admin"
GMAIL_ISSUE_DATA_ADMIN = "gmail_issue_data_admin"
GMAIL_FINAL_CHECK_ADMIN = "gmail_final_check_admin"

OTHER_HOLD_REVIEW_ADMIN = "other_hold_review_admin"

# --- Маппинг ключей и описаний для отображения ---
ROLE_DESCRIPTIONS = {
    YANDEX_TEXT_PROFILE_CHECK_ADMIN: "Проверка профиля (Яндекс, текст)",
    YANDEX_TEXT_ISSUE_TEXT_ADMIN: "Выдача текста (Яндекс)",
    YANDEX_TEXT_FINAL_CHECK_ADMIN: "Финальная проверка (Яндекс, текст)",
    YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN: "Проверка профиля (Яндекс, без текста)",
    YANDEX_NO_TEXT_FINAL_CHECK_ADMIN: "Финальная проверка (Яндекс, без текста)",
    GOOGLE_PROFILE_CHECK_ADMIN: "Проверка профиля (Google)",
    GOOGLE_LAST_REVIEWS_CHECK_ADMIN: "Проверка отзывов (Google)",
    GOOGLE_ISSUE_TEXT_ADMIN: "Выдача текста (Google)",
    GOOGLE_FINAL_CHECK_ADMIN: "Финальная проверка (Google)",
    GMAIL_DEVICE_MODEL_CHECK_ADMIN: "Проверка модели устройства (Gmail)",
    GMAIL_ISSUE_DATA_ADMIN: "Выдача данных (Gmail)",
    GMAIL_FINAL_CHECK_ADMIN: "Финальная проверка (Gmail)",
    OTHER_HOLD_REVIEW_ADMIN: "Проверка после холда"
}

# --- Маппинг типов задач и ролей ---
TASK_TO_ROLE_MAP = {
    "yandex_with_text_profile_screenshot": YANDEX_TEXT_PROFILE_CHECK_ADMIN,
    "yandex_with_text_issue_text": YANDEX_TEXT_ISSUE_TEXT_ADMIN,
    "yandex_with_text_final_verdict": YANDEX_TEXT_FINAL_CHECK_ADMIN,
    "yandex_without_text_profile_screenshot": YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN,
    "yandex_without_text_final_verdict": YANDEX_NO_TEXT_FINAL_CHECK_ADMIN,
    "google_profile": GOOGLE_PROFILE_CHECK_ADMIN,
    "google_last_reviews": GOOGLE_LAST_REVIEWS_CHECK_ADMIN,
    "google_issue_text": GOOGLE_ISSUE_TEXT_ADMIN,
    "google_final_verdict": GOOGLE_FINAL_CHECK_ADMIN,
    "gmail_device_model": GMAIL_DEVICE_MODEL_CHECK_ADMIN,
    "gmail_issue_data": GMAIL_ISSUE_DATA_ADMIN,
    "gmail_final_check": GMAIL_FINAL_CHECK_ADMIN,
    "other_hold_check": OTHER_HOLD_REVIEW_ADMIN
}


async def get_admin_for_role(role_key: str) -> int:
    """Получает ID админа для конкретной роли из БД, иначе возвращает ID по умолчанию."""
    admin_id_str = await db_manager.get_system_setting(role_key)
    if admin_id_str and admin_id_str.isdigit():
        return int(admin_id_str)
    return SUPER_ADMIN_ID

async def get_admins_for_task(task_type: str) -> List[int]:
    """Возвращает список ID админов, ответственных за данный тип задачи."""
    role_key = TASK_TO_ROLE_MAP.get(task_type)
    if role_key:
        admin_id = await get_admin_for_role(role_key)
        return [admin_id]
    
    # Если задача не требует конкретного ответственного, отправляем всем
    logger.warning(f"No specific role found for task type '{task_type}'. Notifying all admins.")
    return ADMIN_IDS


async def get_admin_username(bot: Bot, admin_id: int) -> str:
    """Получает @username админа, если возможно."""
    try:
        user = await bot.get_chat(admin_id)
        return f"@{user.username}" if user.username else f"ID: {admin_id}"
    except Exception:
        return f"ID: {admin_id}"

# --- Геттеры для каждой роли ---

async def get_yandex_text_profile_admin() -> int:
    return await get_admin_for_role(YANDEX_TEXT_PROFILE_CHECK_ADMIN)

async def get_yandex_text_issue_admin() -> int:
    return await get_admin_for_role(YANDEX_TEXT_ISSUE_TEXT_ADMIN)

async def get_yandex_text_final_admin() -> int:
    return await get_admin_for_role(YANDEX_TEXT_FINAL_CHECK_ADMIN)

async def get_yandex_no_text_profile_admin() -> int:
    return await get_admin_for_role(YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN)

async def get_yandex_no_text_final_admin() -> int:
    return await get_admin_for_role(YANDEX_NO_TEXT_FINAL_CHECK_ADMIN)

async def get_google_profile_admin() -> int:
    return await get_admin_for_role(GOOGLE_PROFILE_CHECK_ADMIN)

async def get_google_reviews_admin() -> int:
    return await get_admin_for_role(GOOGLE_LAST_REVIEWS_CHECK_ADMIN)

async def get_google_issue_admin() -> int:
    return await get_admin_for_role(GOOGLE_ISSUE_TEXT_ADMIN)

async def get_google_final_admin() -> int:
    return await get_admin_for_role(GOOGLE_FINAL_CHECK_ADMIN)

async def get_gmail_device_admin() -> int:
    return await get_admin_for_role(GMAIL_DEVICE_MODEL_CHECK_ADMIN)

async def get_gmail_data_admin() -> int:
    return await get_admin_for_role(GMAIL_ISSUE_DATA_ADMIN)

async def get_gmail_final_admin() -> int:
    return await get_admin_for_role(GMAIL_FINAL_CHECK_ADMIN)

async def get_other_hold_admin() -> int:
    return await get_admin_for_role(OTHER_HOLD_REVIEW_ADMIN)

# --- Форматирование вывода ---

async def get_all_roles_readable(bot: Bot) -> str:
    """Собирает информацию обо всех ролях в читаемый текст."""
    text = "<b>⚙️ Текущее распределение ролей:</b>\n\n"
    
    all_roles = list(ROLE_DESCRIPTIONS.keys())
    
    for role_key in all_roles:
        description = ROLE_DESCRIPTIONS.get(role_key, "Неизвестная роль")
        admin_id = await get_admin_for_role(role_key)
        admin_name = await get_admin_username(bot, admin_id)
        text += f"<b>{description}:</b> {admin_name}\n"
        
    return text