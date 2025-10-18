# file: logic/admin_roles.py

import logging
from typing import List, Tuple
import asyncio

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

def get_tasks_for_category(category: str, subcategory: str = None) -> List[str]:
    """Возвращает список ключей ролей для указанной категории."""
    if category == "yandex":
        if subcategory == "text":
            return [YANDEX_TEXT_PROFILE_CHECK_ADMIN, YANDEX_TEXT_ISSUE_TEXT_ADMIN, YANDEX_TEXT_FINAL_CHECK_ADMIN]
        elif subcategory == "no_text":
            return [YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN, YANDEX_NO_TEXT_FINAL_CHECK_ADMIN]
    elif category == "google":
        return [GOOGLE_PROFILE_CHECK_ADMIN, GOOGLE_LAST_REVIEWS_CHECK_ADMIN, GOOGLE_ISSUE_TEXT_ADMIN, GOOGLE_FINAL_CHECK_ADMIN]
    elif category == "gmail":
        return [GMAIL_DEVICE_MODEL_CHECK_ADMIN, GMAIL_ISSUE_DATA_ADMIN, GMAIL_FINAL_CHECK_ADMIN]
    elif category == "other":
        return [OTHER_HOLD_REVIEW_ADMIN]
    return []

def get_category_from_role_key(role_key: str) -> Tuple[str, str | None]:
    """Определяет категорию и подкатегорию по ключу роли."""
    if "yandex" in role_key:
        subcategory = "no_text" if "no_text" in role_key else "text"
        return "yandex", subcategory
    elif "google" in role_key:
        return "google", None
    elif "gmail" in role_key:
        return "gmail", None
    elif "other" in role_key:
        return "other", None
    return "unknown", None

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

async def get_all_roles_readable_optimized(bot: Bot) -> str:
    """
    Оптимизированная версия: собирает информацию обо всех ролях, минимизируя запросы.
    """
    roles_data_structure = {
        "**📍 Яндекс (с текстом):**": [
            YANDEX_TEXT_PROFILE_CHECK_ADMIN, YANDEX_TEXT_ISSUE_TEXT_ADMIN, YANDEX_TEXT_FINAL_CHECK_ADMIN
        ],
        "**📍 Яндекс (без текста):**": [
            YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN, YANDEX_NO_TEXT_FINAL_CHECK_ADMIN
        ],
        "**🌍 Google Maps:**": [
            GOOGLE_PROFILE_CHECK_ADMIN, GOOGLE_LAST_REVIEWS_CHECK_ADMIN, GOOGLE_ISSUE_TEXT_ADMIN, GOOGLE_FINAL_CHECK_ADMIN
        ],
        "**📧 Gmail:**": [
            GMAIL_DEVICE_MODEL_CHECK_ADMIN, GMAIL_ISSUE_DATA_ADMIN, GMAIL_FINAL_CHECK_ADMIN
        ],
        "**📦 Другое:**": [
            OTHER_HOLD_REVIEW_ADMIN
        ]
    }
    
    # 1. Получаем все настройки ролей из БД одним запросом
    all_role_keys = [key for sublist in roles_data_structure.values() for key in sublist]
    all_settings = await db_manager.get_system_settings_batch(all_role_keys)
    
    # 2. Собираем все уникальные ID админов, которые реально назначены
    admin_ids = {int(setting.value) for setting in all_settings if setting.value and setting.value.isdigit()}
    admin_ids.update([ADMIN_ID_1, ADMIN_ID_2]) # Добавляем дефолтных
    
    # 3. Получаем информацию (username) для этих ID
    admins_info = await db_manager.get_administrators_details(list(admin_ids))
    admins_map = {admin.user_id: f"@{admin.username}" if admin.username else f"ID: {admin.user_id}" for admin in admins_info}

    # 4. Формируем текст
    full_text = "**⚙ Текущее распределение ролей:**\n\n"
    for category, keys in roles_data_structure.items():
        full_text += f"{category}\n"
        for key in keys:
            # Находим настройку для текущего ключа
            admin_id_str = next((s.value for s in all_settings if s.key == key), None)
            
            # Определяем ID админа (с учетом дефолтного значения)
            if key in [YANDEX_TEXT_FINAL_CHECK_ADMIN, YANDEX_NO_TEXT_FINAL_CHECK_ADMIN, GOOGLE_FINAL_CHECK_ADMIN, GMAIL_FINAL_CHECK_ADMIN]:
                admin_id = int(admin_id_str) if admin_id_str else ADMIN_ID_2
            else:
                admin_id = int(admin_id_str) if admin_id_str else ADMIN_ID_1
            
            description = ROLE_DESCRIPTIONS.get(key, key)
            admin_name = admins_map.get(admin_id, f"ID: {admin_id}") # Берем имя из кэша
            full_text += f"  - *{description}:* {admin_name}\n"
        full_text += "\n"
        
    return full_text


async def get_admins_for_task(task_type: str) -> List[int]:
    """
    Возвращает список ID администраторов, ответственных за данный тип задачи.
    """
    task_map = {
        "google_profile": get_google_profile_admin,
        "google_last_reviews": get_google_reviews_admin,
        "google_issue_text": get_google_issue_admin,
        "google_final_verdict": get_google_final_admin,
        "yandex_with_text_profile_screenshot": get_yandex_text_profile_admin,
        "yandex_with_text_issue_text": get_yandex_text_issue_admin,
        "yandex_with_text_final_verdict": get_yandex_text_final_admin,
        "yandex_without_text_profile_screenshot": get_yandex_no_text_profile_admin,
        "yandex_without_text_final_verdict": get_yandex_no_text_final_admin,
        "gmail_device_model": get_gmail_device_admin,
        "gmail_issue_data": get_gmail_data_admin,
        "gmail_final_check": get_gmail_final_admin,
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