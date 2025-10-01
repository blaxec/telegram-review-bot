# file: logic/admin_roles.py

import logging
from typing import List
from aiogram import Bot
from database import db_manager
from config import ADMIN_ID_1, ADMIN_ID_2

logger = logging.getLogger(__name__)

# --- Ключи для хранения ролей в таблице SystemSetting ---
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

ROLE_DESCRIPTIONS = {
    YANDEX_TEXT_PROFILE_CHECK_ADMIN: "Проверка профиля Yandex (с текстом)",
    YANDEX_TEXT_ISSUE_TEXT_ADMIN: "Выдача текста Yandex",
    YANDEX_TEXT_FINAL_CHECK_ADMIN: "Финальная проверка Yandex (с текстом)",
    YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN: "Проверка профиля Yandex (без текста)",
    YANDEX_NO_TEXT_FINAL_CHECK_ADMIN: "Финальная проверка Yandex (без текста)",
    GOOGLE_PROFILE_CHECK_ADMIN: "Проверка профиля Google",
    GOOGLE_LAST_REVIEWS_CHECK_ADMIN: "Проверка последних отзывов Google",
    GOOGLE_ISSUE_TEXT_ADMIN: "Выдача текста Google",
    GOOGLE_FINAL_CHECK_ADMIN: "Финальная проверка Google",
    GMAIL_DEVICE_MODEL_CHECK_ADMIN: "Проверка устройства Gmail",
    GMAIL_ISSUE_DATA_ADMIN: "Выдача данных Gmail",
    GMAIL_FINAL_CHECK_ADMIN: "Финальная проверка Gmail",
    OTHER_HOLD_REVIEW_ADMIN: "Проверка отзывов после холда"
}

# --- Функции-геттеры для получения ответственного администратора ---

async def get_admin_username(bot: Bot, admin_id: int) -> str:
    """Получает @username администратора по ID, если возможно."""
    if admin_id == 0:
        return "N/A"
    try:
        admin_user = await bot.get_chat(admin_id)
        return f"@{admin_user.username}" if admin_user.username else f"ID: {admin_id}"
    except Exception as e:
        logger.warning(f"Could not get username for admin_id {admin_id}: {e}")
        return f"ID: {admin_id}"

async def get_responsible_admin(role_key: str, default_admin_id: int = ADMIN_ID_1) -> int:
    """Получает ID ответственного админа из БД или возвращает ID по умолчанию."""
    admin_id_str = await db_manager.get_system_setting(role_key)
    return int(admin_id_str) if admin_id_str else default_admin_id

async def get_yandex_text_profile_admin() -> int:
    return await get_responsible_admin(YANDEX_TEXT_PROFILE_CHECK_ADMIN, ADMIN_ID_1)

async def get_yandex_text_issue_admin() -> int:
    return await get_responsible_admin(YANDEX_TEXT_ISSUE_TEXT_ADMIN, ADMIN_ID_1)

async def get_yandex_text_final_admin() -> int:
    return await get_responsible_admin(YANDEX_TEXT_FINAL_CHECK_ADMIN, ADMIN_ID_2)

async def get_yandex_no_text_profile_admin() -> int:
    return await get_responsible_admin(YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN, ADMIN_ID_1)

async def get_yandex_no_text_final_admin() -> int:
    return await get_responsible_admin(YANDEX_NO_TEXT_FINAL_CHECK_ADMIN, ADMIN_ID_2)

async def get_google_profile_admin() -> int:
    return await get_responsible_admin(GOOGLE_PROFILE_CHECK_ADMIN, ADMIN_ID_1)

async def get_google_reviews_admin() -> int:
    return await get_responsible_admin(GOOGLE_LAST_REVIEWS_CHECK_ADMIN, ADMIN_ID_1)

async def get_google_issue_admin() -> int:
    return await get_responsible_admin(GOOGLE_ISSUE_TEXT_ADMIN, ADMIN_ID_1)

async def get_google_final_admin() -> int:
    return await get_responsible_admin(GOOGLE_FINAL_CHECK_ADMIN, ADMIN_ID_2)

async def get_gmail_device_admin() -> int:
    return await get_responsible_admin(GMAIL_DEVICE_MODEL_CHECK_ADMIN, ADMIN_ID_1)

async def get_gmail_data_admin() -> int:
    return await get_responsible_admin(GMAIL_ISSUE_DATA_ADMIN, ADMIN_ID_1)

async def get_gmail_final_admin() -> int:
    return await get_responsible_admin(GMAIL_FINAL_CHECK_ADMIN, ADMIN_ID_2)

async def get_other_hold_admin() -> int:
    return await get_responsible_admin(OTHER_HOLD_REVIEW_ADMIN, ADMIN_ID_1)

async def get_all_roles_readable(bot: Bot) -> str:
    """Собирает информацию обо всех ролях и ответственных в читаемый текст."""
    roles_data = {
        "📍 Яндекс (с текстом)": [
            (YANDEX_TEXT_PROFILE_CHECK_ADMIN, await get_yandex_text_profile_admin()),
            (YANDEX_TEXT_ISSUE_TEXT_ADMIN, await get_yandex_text_issue_admin()),
            (YANDEX_TEXT_FINAL_CHECK_ADMIN, await get_yandex_text_final_admin()),
        ],
        "📍 Яндекс (без текста)": [
            (YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN, await get_yandex_no_text_profile_admin()),
            (YANDEX_NO_TEXT_FINAL_CHECK_ADMIN, await get_yandex_no_text_final_admin()),
        ],
        "🌍 Google Maps": [
            (GOOGLE_PROFILE_CHECK_ADMIN, await get_google_profile_admin()),
            (GOOGLE_LAST_REVIEWS_CHECK_ADMIN, await get_google_reviews_admin()),
            (GOOGLE_ISSUE_TEXT_ADMIN, await get_google_issue_admin()),
            (GOOGLE_FINAL_CHECK_ADMIN, await get_google_final_admin()),
        ],
        "📧 Gmail": [
            (GMAIL_DEVICE_MODEL_CHECK_ADMIN, await get_gmail_device_admin()),
            (GMAIL_ISSUE_DATA_ADMIN, await get_gmail_data_admin()),
            (GMAIL_FINAL_CHECK_ADMIN, await get_gmail_final_admin()),
        ],
        "📦 Другое": [
            (OTHER_HOLD_REVIEW_ADMIN, await get_other_hold_admin())
        ]
    }

    full_text = "<b>⚙ Текущее распределение ролей:</b>\n\n"
    for category, tasks in roles_data.items():
        full_text += f"<b>{category}:</b>\n"
        for key, admin_id in tasks:
            description = ROLE_DESCRIPTIONS.get(key, key)
            admin_name = await get_admin_username(bot, admin_id)
            full_text += f"  - <i>{description}:</i> {admin_name}\n"
        full_text += "\n"
        
    return full_text

# ИСПРАВЛЕНА ОШИБКА: Теперь функция корректно await-ит и возвращает список ID.
async def get_admins_for_task(task_type: str) -> List[int]:
    """
    Возвращает список ID администраторов, ответственных за данный тип задачи.
    """
    task_map = {
        # Google
        "google_profile": get_google_profile_admin,
        "google_last_reviews": get_google_reviews_admin,
        "google_issue_text": get_google_issue_admin,
        "google_final_verdict": get_google_final_admin,
        # Yandex with text
        "yandex_with_text_profile_screenshot": get_yandex_text_profile_admin,
        "yandex_with_text_issue_text": get_yandex_text_issue_admin,
        "yandex_with_text_final_verdict": get_yandex_text_final_admin,
        # Yandex without text
        "yandex_without_text_profile_screenshot": get_yandex_no_text_profile_admin,
        "yandex_without_text_final_verdict": get_yandex_no_text_final_admin,
        # Gmail
        "gmail_device_model": get_gmail_device_admin,
        "gmail_issue_data": get_gmail_data_admin,
        "gmail_final_check": get_gmail_final_admin,
        # Other
        "other_hold_check": get_other_hold_admin,
    }

    get_admin_func = task_map.get(task_type)

    if get_admin_func:
        admin_id = await get_admin_func()
        return [admin_id] if admin_id else []
    else:
        logger.warning(f"No specific admin found for task type '{task_type}'. Defaulting to all admins.")
        all_admins = await db_manager.get_all_administrators_by_role()
        return [admin.user_id for admin in all_admins]