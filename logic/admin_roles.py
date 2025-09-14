# file: logic/admin_roles.py

import logging
from aiogram import Bot
from database import db_manager
from config import ADMIN_ID_1, ADMIN_ID_2, ADMIN_IDS, Defaults

logger = logging.getLogger(__name__)

# --- Константы ключей для хранения в БД ---
# Yandex (с текстом)
YANDEX_TEXT_PROFILE_CHECK_ADMIN = "yandex_text_profile_check_admin"
YANDEX_TEXT_ISSUE_TEXT_ADMIN = "yandex_text_issue_text_admin"
YANDEX_TEXT_FINAL_CHECK_ADMIN = "yandex_text_final_check_admin"
# Yandex (без текста)
YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN = "yandex_no_text_profile_check_admin"
YANDEX_NO_TEXT_FINAL_CHECK_ADMIN = "yandex_no_text_final_check_admin"
# Google
GOOGLE_PROFILE_CHECK_ADMIN = "google_profile_check_admin"
GOOGLE_LAST_REVIEWS_CHECK_ADMIN = "google_last_reviews_check_admin"
GOOGLE_ISSUE_TEXT_ADMIN = "google_issue_text_admin"
GOOGLE_FINAL_CHECK_ADMIN = "google_final_check_admin"
# Gmail
GMAIL_DEVICE_MODEL_CHECK_ADMIN = "gmail_device_model_check_admin"
GMAIL_ISSUE_DATA_ADMIN = "gmail_issue_data_admin"
GMAIL_FINAL_CHECK_ADMIN = "gmail_final_check_admin"
# Другое
OTHER_HOLD_REVIEW_ADMIN = "other_hold_review_admin"


# --- Словарь для сопоставления ключей и описаний ---
ROLE_DESCRIPTIONS = {
    YANDEX_TEXT_PROFILE_CHECK_ADMIN: "Проверка скрина профиля",
    YANDEX_TEXT_ISSUE_TEXT_ADMIN: "Выдача текста",
    YANDEX_TEXT_FINAL_CHECK_ADMIN: "Финальная проверка",
    YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN: "Проверка скрина профиля",
    YANDEX_NO_TEXT_FINAL_CHECK_ADMIN: "Финальная проверка",
    GOOGLE_PROFILE_CHECK_ADMIN: "Проверка скрина профиля",
    GOOGLE_LAST_REVIEWS_CHECK_ADMIN: "Проверка последних отзывов",
    GOOGLE_ISSUE_TEXT_ADMIN: "Выдача текста",
    GOOGLE_FINAL_CHECK_ADMIN: "Финальная проверка",
    GMAIL_DEVICE_MODEL_CHECK_ADMIN: "Проверка модели устройства",
    GMAIL_ISSUE_DATA_ADMIN: "Выдача данных",
    GMAIL_FINAL_CHECK_ADMIN: "Финальная проверка аккаунта",
    OTHER_HOLD_REVIEW_ADMIN: "Проверка скрина после холда",
}

# --- Вспомогательные функции ---

async def get_admin_username(bot: Bot, admin_id: int) -> str:
    """Получает username администратора по его ID."""
    if not admin_id:
        return "Не назначен"
    try:
        admin_chat = await bot.get_chat(admin_id)
        return f"@{admin_chat.username}" if admin_chat.username else f"ID: {admin_id}"
    except Exception:
        return f"ID: {admin_id} (ошибка)"

async def _get_role_holder_id(key: str, default: int) -> int:
    """
    Базовая функция для получения ID администратора для конкретной роли.
    Иерархия: БД -> config.py (default) -> ADMIN_ID_1.
    """
    admin_id_str = await db_manager.get_system_setting(key)
    if admin_id_str and admin_id_str.isdigit():
        return int(admin_id_str)
    return default or ADMIN_ID_1

# --- Основные функции для получения ID ответственных ---

async def get_yandex_text_profile_admin() -> int:
    return await _get_role_holder_id(YANDEX_TEXT_PROFILE_CHECK_ADMIN, Defaults.DEFAULT_SCREENSHOT_CHECK_ADMIN)

async def get_yandex_text_issue_admin() -> int:
    return await _get_role_holder_id(YANDEX_TEXT_ISSUE_TEXT_ADMIN, Defaults.DEFAULT_TEXT_PROVIDER_ADMIN)

async def get_yandex_text_final_admin() -> int:
    return await _get_role_holder_id(YANDEX_TEXT_FINAL_CHECK_ADMIN, Defaults.DEFAULT_FINAL_VERDICT_ADMIN)

async def get_yandex_no_text_profile_admin() -> int:
    return await _get_role_holder_id(YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN, Defaults.DEFAULT_SCREENSHOT_CHECK_ADMIN)

async def get_yandex_no_text_final_admin() -> int:
    return await _get_role_holder_id(YANDEX_NO_TEXT_FINAL_CHECK_ADMIN, Defaults.DEFAULT_FINAL_VERDICT_ADMIN)

async def get_google_profile_admin() -> int:
    return await _get_role_holder_id(GOOGLE_PROFILE_CHECK_ADMIN, Defaults.DEFAULT_SCREENSHOT_CHECK_ADMIN)

async def get_google_reviews_admin() -> int:
    return await _get_role_holder_id(GOOGLE_LAST_REVIEWS_CHECK_ADMIN, Defaults.DEFAULT_SCREENSHOT_CHECK_ADMIN)

async def get_google_issue_admin() -> int:
    return await _get_role_holder_id(GOOGLE_ISSUE_TEXT_ADMIN, Defaults.DEFAULT_TEXT_PROVIDER_ADMIN)

async def get_google_final_admin() -> int:
    return await _get_role_holder_id(GOOGLE_FINAL_CHECK_ADMIN, Defaults.DEFAULT_FINAL_VERDICT_ADMIN)

async def get_gmail_device_admin() -> int:
    return await _get_role_holder_id(GMAIL_DEVICE_MODEL_CHECK_ADMIN, Defaults.DEFAULT_SCREENSHOT_CHECK_ADMIN)

async def get_gmail_data_admin() -> int:
    return await _get_role_holder_id(GMAIL_ISSUE_DATA_ADMIN, Defaults.DEFAULT_TEXT_PROVIDER_ADMIN)

async def get_gmail_final_admin() -> int:
    return await _get_role_holder_id(GMAIL_FINAL_CHECK_ADMIN, Defaults.DEFAULT_FINAL_VERDICT_ADMIN)

async def get_other_hold_admin() -> int:
    return await _get_role_holder_id(OTHER_HOLD_REVIEW_ADMIN, Defaults.DEFAULT_FINAL_VERDICT_ADMIN)

# --- Логика для отображения и обновления ---

async def get_all_roles_readable(bot: Bot) -> str:
    """Формирует читабельное сообщение со всеми текущими настройками ролей."""
    
    yandex_text_tasks = {
        YANDEX_TEXT_PROFILE_CHECK_ADMIN: await get_yandex_text_profile_admin(),
        YANDEX_TEXT_ISSUE_TEXT_ADMIN: await get_yandex_text_issue_admin(),
        YANDEX_TEXT_FINAL_CHECK_ADMIN: await get_yandex_text_final_admin(),
    }
    yandex_no_text_tasks = {
        YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN: await get_yandex_no_text_profile_admin(),
        YANDEX_NO_TEXT_FINAL_CHECK_ADMIN: await get_yandex_no_text_final_admin(),
    }
    google_tasks = {
        GOOGLE_PROFILE_CHECK_ADMIN: await get_google_profile_admin(),
        GOOGLE_LAST_REVIEWS_CHECK_ADMIN: await get_google_reviews_admin(),
        GOOGLE_ISSUE_TEXT_ADMIN: await get_google_issue_admin(),
        GOOGLE_FINAL_CHECK_ADMIN: await get_google_final_admin(),
    }
    gmail_tasks = {
        GMAIL_DEVICE_MODEL_CHECK_ADMIN: await get_gmail_device_admin(),
        GMAIL_ISSUE_DATA_ADMIN: await get_gmail_data_admin(),
        GMAIL_FINAL_CHECK_ADMIN: await get_gmail_final_admin(),
    }
    other_tasks = {
        OTHER_HOLD_REVIEW_ADMIN: await get_other_hold_admin(),
    }

    async def format_task_block(tasks: dict) -> str:
        lines = []
        for key, admin_id in tasks.items():
            description = ROLE_DESCRIPTIONS.get(key, key)
            admin_name = await get_admin_username(bot, admin_id)
            lines.append(f"- {description}: <b>{admin_name}</b>")
        return "\n".join(lines)

    text = "<b>⚙ Текущие настройки админов</b>\n\n"
    text += "<b>📍 Яндекс (с текстом)</b>\n" + await format_task_block(yandex_text_tasks) + "\n\n"
    text += "<b>📍 Яндекс (без текста)</b>\n" + await format_task_block(yandex_no_text_tasks) + "\n\n"
    text += "<b>🌍 Google Maps</b>\n" + await format_task_block(google_tasks) + "\n\n"
    text += "<b>📧 Gmail</b>\n" + await format_task_block(gmail_tasks) + "\n\n"
    text += "<b>📦 Другие задачи</b>\n" + await format_task_block(other_tasks)
    
    return text