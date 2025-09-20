# file: telegram-review-bot-main/handlers/admin_roles.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from config import SUPER_ADMIN_ID, ADMIN_IDS
from keyboards import inline
from database import db_manager
from logic import admin_roles
from utils.access_filters import IsSuperAdmin # НОВЫЙ ФИЛЬТР

router = Router()
logger = logging.getLogger(__name__)


# --- Команда /roles ---
@router.message(Command("roles"), IsSuperAdmin()) # Изменен фильтр
async def cmd_roles(message: Message):
    """Точка входа в управление ролями."""
    await message.answer(
        "🛠️ <b>Управление ролями администраторов</b>\n\n"
        "Выберите категорию для настройки ответственных.",
        reply_markup=await inline.get_roles_main_menu()
    )

# --- Навигация по меню ---

@router.callback_query(F.data == "roles_back:main", IsSuperAdmin()) # Изменен фильтр
async def roles_back_to_main(callback: CallbackQuery):
    """Возврат в главное меню ролей."""
    await callback.message.edit_text(
        "🛠️ <b>Управление ролями администраторов</b>\n\n"
        "Выберите категорию для настройки ответственных.",
        reply_markup=await inline.get_roles_main_menu()
    )

@router.callback_query(F.data.startswith("roles_cat:"), IsSuperAdmin()) # Изменен фильтр
async def roles_select_category(callback: CallbackQuery, bot: Bot):
    """Выбор основной категории (Яндекс, Google и т.д.)."""
    category = callback.data.split(":")[1]
    
    if category == "yandex":
        await callback.message.edit_text(
            "<b>📍 Яндекс.Карты</b>\n\nВыберите тип задачи для настройки.",
            reply_markup=await inline.get_roles_yandex_menu()
        )
    elif category == "google":
        await callback.message.edit_text(
            "<b>🌍 Google Maps</b>\n\nНажмите на задачу, чтобы сменить ответственного.",
            reply_markup=await inline.get_task_switching_keyboard(bot, "google")
        )
    elif category == "gmail":
        await callback.message.edit_text(
            "<b>📧 Gmail</b>\n\nНажмите на задачу, чтобы сменить ответственного.",
            reply_markup=await inline.get_task_switching_keyboard(bot, "gmail")
        )
    elif category == "other":
        await callback.message.edit_text(
            "<b>📦 Другие задачи</b>\n\nНажмите на задачу, чтобы сменить ответственного.",
            reply_markup=await inline.get_task_switching_keyboard(bot, "other")
        )

@router.callback_query(F.data.startswith("roles_subcat:"), IsSuperAdmin()) # Изменен фильтр
async def roles_select_subcategory(callback: CallbackQuery, bot: Bot):
    """Выбор подкатегории (например, Яндекс с текстом/без)."""
    subcategory = callback.data.split(":")[1] # yandex_text или yandex_no_text
    category, sub_type = subcategory.split("_", 1) # yandex, text

    title_map = {
        "text": "📝 Яндекс (с текстом)",
        "no_text": "🚫 Яндекс (без текста)",
    }
    
    await callback.message.edit_text(
        f"<b>{title_map.get(sub_type)}</b>\n\nНажмите на задачу, чтобы сменить ответственного.",
        reply_markup=await inline.get_task_switching_keyboard(bot, category, sub_type)
    )

@router.callback_query(F.data == "roles_back:yandex", IsSuperAdmin()) # Изменен фильтр
async def roles_back_to_yandex_cat(callback: CallbackQuery):
    """Возврат к выбору типа Яндекс задач."""
    await callback.message.edit_text(
        "<b>📍 Яндекс.Карты</b>\n\nВыберите тип задачи для настройки.",
        reply_markup=await inline.get_roles_yandex_menu()
    )
    
# --- Логика переключения и отображения ---

@router.callback_query(F.data.startswith("roles_switch:"), IsSuperAdmin()) # Изменен фильтр
async def roles_switch_admin(callback: CallbackQuery, bot: Bot):
    """Переключает администратора для выбранной задачи."""
    role_key = callback.data.split(":", 1)[1]
    
    current_admin_id_str = await db_manager.get_system_setting(role_key)
    current_admin_id = int(current_admin_id_str) if current_admin_id_str else SUPER_ADMIN_ID
    
    # Определяем нового администратора
    # Переключаем между SUPER_ADMIN_ID и ADMIN_ID_2 (если ADMIN_ID_2 существует), иначе между SUPER_ADMIN_ID и собой
    if len(ADMIN_IDS) > 1 and current_admin_id == SUPER_ADMIN_ID:
        # Пытаемся найти второго админа, отличного от главного
        other_admin_id = next((aid for aid in ADMIN_IDS if aid != SUPER_ADMIN_ID), SUPER_ADMIN_ID)
        new_admin_id = other_admin_id
    elif len(ADMIN_IDS) > 1 and current_admin_id != SUPER_ADMIN_ID:
        new_admin_id = SUPER_ADMIN_ID
    else: # Если только один админ
        new_admin_id = SUPER_ADMIN_ID
    
    await db_manager.set_system_setting(role_key, str(new_admin_id))
    
    await callback.answer("Ответственный изменен!")

    # --- ИСПРАВЛЕННАЯ ЛОГИКА ОБНОВЛЕНИЯ КЛАВИАТУРЫ ---
    category = "unknown"
    subcategory = None
    
    if "yandex_text" in role_key:
        category = "yandex"
        subcategory = "text"
    elif "yandex_no_text" in role_key:
        category = "yandex"
        subcategory = "no_text"
    elif "google" in role_key:
        category = "google"
    elif "gmail" in role_key:
        category = "gmail"
    elif "other" in role_key:
        category = "other"
    
    await callback.message.edit_reply_markup(
        reply_markup=await inline.get_task_switching_keyboard(bot, category, subcategory)
    )
    # --- КОНЕЦ ИСПРАВЛЕНИЙ ---
    
    # Отправляем уведомления
    task_description = admin_roles.ROLE_DESCRIPTIONS.get(role_key, "Неизвестная задача")
    new_admin_name = await admin_roles.get_admin_username(bot, new_admin_id)
    old_admin_name = await admin_roles.get_admin_username(bot, current_admin_id)

    notification_text = (
        f"🔄 <b>Смена ролей!</b>\n\n"
        f"Задача «<b>{task_description}</b>» была передана от {old_admin_name} к {new_admin_name}."
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notification_text)
        except Exception as e:
            logger.warning(f"Не удалось уведомить админа {admin_id} о смене роли: {e}")

@router.callback_query(F.data == "roles_show_current", IsSuperAdmin()) # Изменен фильтр
async def roles_show_current_settings(callback: CallbackQuery, bot: Bot):
    """Показывает отдельное сообщение с текущими настройками."""
    await callback.answer()
    settings_text = await admin_roles.get_all_roles_readable(bot)
    await callback.message.answer(
        settings_text,
        reply_markup=inline.get_current_settings_keyboard()
    )

@router.callback_query(F.data == "roles_delete_msg", IsSuperAdmin()) # Изменен фильтр
async def roles_delete_settings_msg(callback: CallbackQuery):
    """Удаляет сообщение с настройками."""
    try:
        await callback.message.delete()
        await callback.answer("Сообщение удалено.")
    except TelegramBadRequest:
        await callback.answer("Не удалось удалить сообщение.", show_alert=True)