import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from math import ceil

from config import ADMIN_ID_1, ADMIN_ID_2
from keyboards import inline
from database import db_manager
from logic import admin_roles
from utils.access_filters import IsSuperAdmin
from states.user_states import AdminState


router = Router()
logger = logging.getLogger(__name__)

# --- ИЗМЕНЕНИЕ: Импортируем функцию для обновления команд ---
from main import set_bot_commands


async def delete_and_clear_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_message_id)
        except TelegramBadRequest: pass
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.update_data(prompt_message_id=None)

# --- Команда /roles ---
@router.message(Command("roles"), IsSuperAdmin())
async def cmd_roles(message: Message):
    """Точка входа в управление ролями."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer(
        "🛠️ <b>Управление ролями администраторов</b>\n\n"
        "Выберите категорию для настройки ответственных.",
        reply_markup=await inline.get_roles_main_menu()
    )

# --- Навигация по меню ---

@router.callback_query(F.data == "roles_back:main")
async def roles_back_to_main(callback: CallbackQuery):
    """Возврат в главное меню ролей."""
    await callback.message.edit_text(
        "🛠️ <b>Управление ролями администраторов</b>\n\n"
        "Выберите категорию для настройки ответственных.",
        reply_markup=await inline.get_roles_main_menu()
    )

@router.callback_query(F.data.startswith("roles_cat:"))
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

@router.callback_query(F.data.startswith("roles_subcat:"))
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

@router.callback_query(F.data == "roles_back:yandex")
async def roles_back_to_yandex_cat(callback: CallbackQuery):
    """Возврат к выбору типа Яндекс задач."""
    await callback.message.edit_text(
        "<b>📍 Яндекс.Карты</b>\n\nВыберите тип задачи для настройки.",
        reply_markup=await inline.get_roles_yandex_menu()
    )
    
# --- Логика переключения и отображения ---

@router.callback_query(F.data.startswith("roles_switch:"))
async def roles_switch_admin_start(callback: CallbackQuery, bot: Bot):
    """Начинает процесс смены админа, показывая список доступных."""
    role_key = callback.data.split(":", 1)[1]
    
    all_admins = await db_manager.get_all_administrators_by_role()
    current_admin_id_str = await db_manager.get_system_setting(role_key)
    current_admin_id = int(current_admin_id_str) if current_admin_id_str else ADMIN_ID_1
    
    task_description = admin_roles.ROLE_DESCRIPTIONS.get(role_key, "Неизвестная задача")
    
    await callback.message.edit_text(
        f"Выберите нового ответственного для задачи:\n<b>«{task_description}»</b>",
        reply_markup=await inline.get_admin_selection_keyboard(all_admins, role_key, current_admin_id, bot)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("roles_set_admin:"))
async def roles_set_new_admin(callback: CallbackQuery, bot: Bot):
    """Устанавливает нового админа для роли."""
    _, role_key, new_admin_id_str = callback.data.split(":")
    new_admin_id = int(new_admin_id_str)
    
    current_admin_id_str = await db_manager.get_system_setting(role_key)
    current_admin_id = int(current_admin_id_str) if current_admin_id_str else ADMIN_ID_1
    
    if new_admin_id == current_admin_id:
        await callback.answer("Этот администратор уже назначен на эту роль.", show_alert=True)
        return

    await db_manager.set_system_setting(role_key, str(new_admin_id))
    
    await callback.answer("Ответственный изменен!")

    category, subcategory = admin_roles.get_category_from_role_key(role_key)

    new_admin_name = await admin_roles.get_admin_username(bot, new_admin_id)
    old_admin_name = await admin_roles.get_admin_username(bot, current_admin_id)
    task_description = admin_roles.ROLE_DESCRIPTIONS.get(role_key, "Неизвестная задача")

    notification_text = (
        f"🔄 <b>Смена ролей!</b>\n\n"
        f"Задача «<b>{task_description}</b>» была передана от {old_admin_name} к {new_admin_name}."
    )
    
    all_db_admins = await db_manager.get_all_administrators_by_role()
    for admin in all_db_admins:
        try:
            await bot.send_message(admin.user_id, notification_text, reply_markup=inline.get_close_post_keyboard())
        except Exception as e:
            logger.warning(f"Не удалось уведомить админа {admin.user_id} о смене роли: {e}")
    
    # Возвращаемся в меню выбора задач
    title_map = {"text": "📝 Яндекс (с текстом)", "no_text": "🚫 Яндекс (без текста)"}
    category_title_map = {"google": "🌍 Google Maps", "gmail": "📧 Gmail", "other": "📦 Другие задачи"}

    title = ""
    if category == "yandex":
        title = title_map.get(subcategory)
    else:
        title = category_title_map.get(category)
        
    await callback.message.edit_text(
        f"<b>{title}</b>\n\nНажмите на задачу, чтобы сменить ответственного.",
        reply_markup=await inline.get_task_switching_keyboard(bot, category, subcategory)
    )

@router.callback_query(F.data == "roles_show_current")
async def roles_show_current_settings(callback: CallbackQuery, bot: Bot):
    """Показывает отдельное сообщение с текущими настройками."""
    await callback.answer()
    settings_text = await admin_roles.get_all_roles_readable(bot)
    await callback.message.answer(
        settings_text,
        reply_markup=inline.get_current_settings_keyboard()
    )

@router.callback_query(F.data == "roles_delete_msg")
async def roles_delete_settings_msg(callback: CallbackQuery):
    """Удаляет сообщение с настройками."""
    try:
        await callback.message.delete()
        await callback.answer("Сообщение удалено.")
    except TelegramBadRequest:
        await callback.answer("Не удалось удалить сообщение.", show_alert=True)

# --- Блок для /roles_manage ---

@router.message(Command("roles_manage"), IsSuperAdmin())
async def cmd_roles_manage(message: Message):
    """Точка входа в управление списком администраторов."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer(
        "👥 <b>Управление администраторами</b>\n\n"
        "Здесь вы можете добавлять, удалять и просматривать администраторов и тестеров.",
        reply_markup=inline.get_roles_manage_menu()
    )

@router.callback_query(F.data == "roles_manage:back_to_menu")
async def roles_manage_back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text(
         "👥 <b>Управление администраторами</b>\n\n"
        "Здесь вы можете добавлять, удалять и просматривать администраторов и тестеров.",
        reply_markup=inline.get_roles_manage_menu()
    )

@router.callback_query(F.data.startswith("roles_manage:list:"))
async def list_admins(callback: CallbackQuery, bot: Bot):
    page = int(callback.data.split(":")[-1])
    admins_per_page = 5
    
    all_admins = await db_manager.get_all_administrators_by_role()
    total_pages = ceil(len(all_admins) / admins_per_page)
    
    start_index = (page - 1) * admins_per_page
    end_index = start_index + admins_per_page
    admins_on_page = all_admins[start_index:end_index]
    
    text, keyboard = await inline.get_roles_list_keyboard(admins_on_page, page, total_pages, bot)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("roles_manage:view:"))
async def view_single_admin(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[-1])
    admin = await db_manager.get_administrator(user_id)
    if not admin:
        await callback.answer("Администратор не найден.", show_alert=True)
        return
    
    try:
        chat = await bot.get_chat(user_id)
        username = f"@{chat.username}" if chat.username else f"ID: {user_id}"
    except Exception:
        username = f"ID: {user_id}"

    role_text = "Главный админ" if admin.role == 'super_admin' else "Админ"
    tester_text = "Да" if admin.is_tester else "Нет"
    
    text = (f"<b>Управление: {username}</b>\n\n"
            f"<b>Роль:</b> {role_text}\n"
            f"<b>Тестер:</b> {tester_text}\n"
            f"<b>Добавил:</b> ID {admin.added_by}\n"
            f"<b>Можно удалить:</b> {'Да' if admin.is_removable else 'Нет'}")
            
    await callback.message.edit_text(text, reply_markup=inline.get_single_admin_manage_keyboard(admin))

@router.callback_query(F.data.startswith("roles_manage:toggle_tester:"))
async def toggle_tester_status(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[-1])
    admin = await db_manager.get_administrator(user_id)
    if not admin: return
    
    new_status = not admin.is_tester
    await db_manager.update_administrator(user_id, is_tester=new_status)
    await callback.answer(f"Статус тестера изменен на: {new_status}")
    
    # --- ИЗМЕНЕНИЕ: Обновляем команды для пользователя ---
    await set_bot_commands(bot)
    
    # Обновляем сообщение
    await view_single_admin(callback, bot)
    
@router.callback_query(F.data.startswith("roles_manage:delete_confirm:"))
async def confirm_delete_admin(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[-1])
    try:
        chat = await bot.get_chat(user_id)
        username = f"@{chat.username}" if chat.username else f"ID {user_id}"
    except Exception:
        username = f"ID {user_id}"
    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить администратора {username}?",
        reply_markup=inline.get_delete_admin_confirm_keyboard(user_id)
    )

@router.callback_query(F.data.startswith("roles_manage:delete_execute:"))
async def execute_delete_admin(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[-1])
    success = await db_manager.delete_administrator(user_id)
    if success:
        await callback.answer("Администратор удален.", show_alert=True)
        # --- ИЗМЕНЕНИЕ: Обновляем команды для всех ---
        await set_bot_commands(bot)
        # --- ИСПРАВЛЕНИЕ: Вместо изменения callback.data, просто вызываем нужную функцию ---
        await list_admins(callback, bot)
    else:
        await callback.answer("Не удалось удалить этого администратора.", show_alert=True)

@router.callback_query(F.data == "roles_manage:add")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.ROLES_ADD_ADMIN_ID)
    prompt = await callback.message.edit_text(
        "Введите ID или @username нового администратора.",
        reply_markup=inline.get_cancel_inline_keyboard("roles_manage:back_to_menu")
    )
    await state.update_data(prompt_message_id=prompt.message_id)

@router.message(AdminState.ROLES_ADD_ADMIN_ID)
async def process_add_admin_id(message: Message, state: FSMContext):
    user_id = await db_manager.find_user_by_identifier(message.text)
    await delete_and_clear_prompt(message, state)
    
    if not user_id:
        await message.answer("Пользователь не найден. Попробуйте снова.", reply_markup=inline.get_roles_manage_menu())
        await state.clear()
        return
        
    if await db_manager.get_administrator(user_id):
        await message.answer("Этот пользователь уже является администратором.", reply_markup=inline.get_roles_manage_menu())
        await state.clear()
        return

    await state.update_data(new_admin_id=user_id)
    await state.set_state(AdminState.ROLES_ADD_ADMIN_ROLE)
    prompt = await message.answer("Выберите роль для нового администратора:", reply_markup=inline.get_role_selection_keyboard())
    await state.update_data(prompt_message_id=prompt.message_id)

@router.callback_query(F.data.startswith("roles_manage:set_role:"), AdminState.ROLES_ADD_ADMIN_ROLE)
async def process_add_admin_role(callback: CallbackQuery, state: FSMContext, bot: Bot):
    role = callback.data.split(":")[-1]
    data = await state.get_data()
    
    success = await db_manager.add_administrator(
        user_id=data['new_admin_id'],
        role=role,
        is_tester=False,
        added_by=callback.from_user.id
    )
    
    if success:
        await callback.answer("Администратор успешно добавлен!", show_alert=True)
        # --- ИЗМЕНЕНИЕ: Обновляем команды ---
        await set_bot_commands(bot)
    else:
        await callback.answer("Ошибка при добавлении администратора.", show_alert=True)
        
    await state.clear()
    await callback.message.delete()
    
    # --- ИСПРАВЛЕНИЕ: Вызываем list_admins с правильными аргументами ---
    await list_admins(callback, bot)