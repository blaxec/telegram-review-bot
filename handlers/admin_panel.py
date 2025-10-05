# file: handlers/admin_panel.py

import asyncio
import logging
from math import ceil
from typing import Union

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message

from config import Durations, Limits
from database import db_manager
from keyboards import inline
# --- ИСПРАВЛЕНИЕ: Добавлены недостающие импорты ---
from logic.admin_logic import (apply_fine_to_user, format_banned_user_page,
                               format_complaints_page, format_promo_code_page,
                               get_unban_requests_page, get_user_hold_info_logic,
                               process_unban_request_logic)
from states.user_states import AdminState
from utils.access_filters import IsAdmin, IsSuperAdmin

router = Router()
logger = logging.getLogger(__name__)


async def schedule_message_deletion(message: Message, delay: int):
    """Вспомогательная функция для планирования удаления сообщения."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

async def delete_previous_messages(message: Message, state: FSMContext):
    """Вспомогательная функция для удаления старых сообщений."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_message_id)
        except TelegramBadRequest:
            pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


# --- ГЛОБАЛЬНЫЕ АДМИН КОМАНДЫ ---

@router.message(Command("dnd"), IsAdmin())
async def toggle_dnd_mode(message: Message, state: FSMContext):
    try: await message.delete()
    except TelegramBadRequest: pass
    
    new_dnd_status = await db_manager.toggle_dnd_status(message.from_user.id)
    
    if new_dnd_status:
        response_text = "🌙 Ночной режим включен. Вы больше не будете получать рабочие уведомления."
    else:
        response_text = "☀️ Ночной режим выключен. Вы снова получаете все рабочие уведомления."
    
    msg = await message.answer(response_text)
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
    await state.clear()

@router.message(Command("pending_tasks"), IsAdmin())
async def show_pending_tasks(message: Message, state: FSMContext):
    try: await message.delete()
    except TelegramBadRequest: pass
    
    tasks_count = await db_manager.get_pending_tasks_count()
    
    text = (
        "📥 <b>Задачи, ожидающие внимания:</b>\n\n"
        f"➡️ <b>Отзывы на проверку:</b> {tasks_count['reviews']} шт.\n"
        f"➡️ <b>Открытые тикеты поддержки:</b> {tasks_count['tickets']} шт.\n\n"
        "<i>Используйте соответствующие разделы для обработки.</i>"
    )
    
    msg = await message.answer(text)
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_INFO_MESSAGE_DELAY))
    await state.clear()
    
# --- ПАНЕЛЬ УПРАВЛЛЕНИЯ /panel ---
@router.message(Command("panel"), IsSuperAdmin())
async def show_admin_panel(message: Message, state: FSMContext):
    """Отображает главную панель управления для SuperAdmin."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await state.clear()
    await message.answer(
        "🛠️ <b>Панель управления утилитами</b>\n\n"
        "Выберите действие:",
        reply_markup=inline.get_admin_panel_keyboard()
    )

@router.callback_query(F.data == "panel:back_to_panel")
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext):
    """Возвращает к главной панели управления."""
    await state.clear()
    await callback.message.edit_text(
        "🛠️ <b>Панель управления утилитами</b>\n\n"
        "Выберите действие:",
        reply_markup=inline.get_admin_panel_keyboard()
    )

# --- ПОДМЕНЮ В ПАНЕЛИ УПРАВЛЕНИЯ ---
@router.callback_query(F.data.startswith("panel:"))
async def panel_actions(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    
    # Меню управления блокировками
    if action == "manage_bans":
        await callback.message.edit_text("<b>Меню управления блокировками</b>\n\nВыберите действие:", reply_markup=inline.get_ban_management_keyboard())
    elif action == "ban_user":
        await state.set_state(AdminState.BAN_USER_IDENTIFIER)
        prompt = await callback.message.edit_text("Введите ID или @username пользователя для бана.", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_bans"))
        await state.update_data(prompt_message_id=prompt.message_id)
    elif action == "ban_list":
        await state.set_state(AdminState.BAN_LIST_VIEW)
        await show_banned_users_page(callback, state, 1)
    
    # Меню амнистии (внутри меню банов)
    elif action == "manage_amnesty":
        await state.set_state(AdminState.AMNESTY_LIST_VIEW)
        await show_amnesty_page(callback, state, 1)

    # Меню управления промокодами
    elif action == "manage_promos":
        await callback.message.edit_text("<b>Меню управления промокодами</b>\n\nВыберите действие:", reply_markup=inline.get_promo_management_keyboard())
    elif action == "create_promo":
        await state.set_state(AdminState.PROMO_CODE_NAME)
        prompt = await callback.message.edit_text("Введите уникальное название для нового промокода (например, NEWYEAR2025).", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
        await state.update_data(prompt_message_id=prompt.message_id)
    elif action == "promo_list":
        await state.set_state(AdminState.PROMO_LIST_VIEW)
        await show_promo_codes_page(callback, state, 1)

    # Меню жалоб (внутри штрафов)
    elif action == "view_complaints":
        await state.set_state(AdminState.COMPLAINTS_LIST_VIEW)
        await show_complaints_page(callback, state, 1)

    # Другие утилиты из главного меню
    elif action == "issue_fine":
        await state.set_state(AdminState.FINE_USER_ID)
        prompt = await callback.message.edit_text("Введите ID или @username пользователя для штрафа.", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
        await state.update_data(prompt_message_id=prompt.message_id)
    elif action == "reset_cooldown":
        await state.set_state(AdminState.RESET_COOLDOWN_USER_ID)
        prompt = await callback.message.edit_text("Введите ID или @username пользователя для сброса кулдаунов.", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
        await state.update_data(prompt_message_id=prompt.message_id)
    elif action == "view_hold":
        await state.set_state(AdminState.VIEWHOLD_USER_ID)
        prompt = await callback.message.edit_text("Введите ID или @username пользователя для просмотра его холда.", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
        await state.update_data(prompt_message_id=prompt.message_id)
    
    await callback.answer()

async def show_banned_users_page(callback_or_message: Union[CallbackQuery, Message], state: FSMContext, page: int):
    users, total = await db_manager.get_banned_users(page=page), await db_manager.get_banned_users_count()
    total_pages = ceil(total / 6) if total > 0 else 1
    text = await format_banned_user_page(users, page, total_pages)
    markup = inline.get_pagination_keyboard("banlist:page", page, total_pages, back_callback="panel:manage_bans")

    if isinstance(callback_or_message, CallbackQuery):
        await callback_or_message.message.edit_text(text, reply_markup=markup)
    else:
        await callback_or_message.answer(text, reply_markup=markup)


async def show_promo_codes_page(callback_or_message: Union[CallbackQuery, Message], state: FSMContext, page: int):
    promos, total = await db_manager.get_all_promo_codes(page=page), await db_manager.get_promo_codes_count()
    total_pages = ceil(total / 6) if total > 0 else 1
    text = await format_promo_code_page(promos, page, total_pages)
    markup = inline.get_promo_list_keyboard(page, total_pages)
    
    if isinstance(callback_or_message, CallbackQuery):
        await callback_or_message.message.edit_text(text, reply_markup=markup)
    else:
        await callback_or_message.answer(text, reply_markup=markup)

async def show_amnesty_page(callback: CallbackQuery, state: FSMContext, page: int):
    requests, total = await db_manager.get_pending_unban_requests(page=page), await db_manager.get_pending_unban_requests_count()
    total_pages = ceil(total / 5) if total > 0 else 1
    text = await get_unban_requests_page(requests, page, total_pages)
    await callback.message.edit_text(text, reply_markup=inline.get_amnesty_keyboard(requests, page, total_pages))

# --- ИСПРАВЛЕНИЕ: Теперь функция использует правильную таблицу ---
async def show_complaints_page(callback: CallbackQuery, state: FSMContext, page: int):
    # Важно: таблица transfer_complaints должна быть создана миграцией
    complaints, total = await db_manager.get_transfer_complaints(page=page)
    total_pages = ceil(total / 5) if total > 0 else 1
    text = await format_complaints_page(complaints, page, total_pages)
    await callback.message.edit_text(text, reply_markup=inline.get_complaints_keyboard(complaints, page, total_pages))

# --- ПРОЧИЕ АДМИН-КОМАНДЫ (из панели) ---

@router.message(Command("reset_cooldown"), IsAdmin())
@router.message(AdminState.RESET_COOLDOWN_USER_ID, IsAdmin())
async def reset_cooldown_handler(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    
    current_state = await state.get_state()
    if current_state == AdminState.RESET_COOLDOWN_USER_ID:
        await delete_previous_messages(message, state)

    identifier = None
    if message.text.startswith('/reset_cooldown'):
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Используйте: <code>/reset_cooldown ID_или_@username</code>"); return
        identifier = args[1]
    else:
        identifier = message.text

    user_id = await db_manager.find_user_by_identifier(identifier)
    if not user_id:
        await message.answer(f"❌ Пользователь <code>{identifier}</code> не найден."); return

    if await db_manager.reset_user_cooldowns(user_id):
        user = await db_manager.get_user(user_id)
        username = f"@{user.username}" if user.username else f"ID: {user_id}"
        msg = await message.answer(f"✅ Кулдауны для <i>{username}</i> сброшены.")
    else: 
        msg = await message.answer(f"❌ Ошибка при сбросе кулдаунов для <code>{identifier}</code>.")

    await state.clear()
    await schedule_message_deletion(msg, 7)
    await show_admin_panel(message, state)


@router.message(Command("viewhold"), IsAdmin())
@router.message(AdminState.VIEWHOLD_USER_ID, IsAdmin())
async def viewhold_handler(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    
    current_state = await state.get_state()
    if current_state == AdminState.VIEWHOLD_USER_ID:
        await delete_previous_messages(message, state)
    
    identifier = None
    if message.text.startswith('/viewhold'):
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /viewhold ID_пользователя_или_@username")
            return
        identifier = args[1]
    else:
        identifier = message.text

    response_text = await get_user_hold_info_logic(identifier)
    msg = await message.answer(response_text)
    await state.clear()
    await schedule_message_deletion(msg, 15)
    await show_admin_panel(message, state)

@router.message(AdminState.FINE_USER_ID, IsAdmin())
async def fine_user_get_id(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    user_id = await db_manager.find_user_by_identifier(message.text)
    if not user_id:
        prompt_msg = await message.answer(f"❌ Пользователь <code>{message.text}</code> не найден.", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(target_user_id=user_id)
    prompt_msg = await message.answer(f"Введите сумму штрафа (например, 10).", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
    await state.set_state(AdminState.FINE_AMOUNT)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.FINE_AMOUNT, IsAdmin())
async def fine_user_get_amount(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
    except (ValueError, TypeError):
        prompt_msg = await message.answer("❌ Введите положительное число.", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(fine_amount=amount)
    prompt_msg = await message.answer("Введите причину штрафа.", reply_markup=inline.get_cancel_inline_keyboard("panel:back_to_panel"))
    await state.set_state(AdminState.FINE_REASON)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.FINE_REASON, IsAdmin())
async def fine_user_get_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text: return
    await delete_previous_messages(message, state)
    data = await state.get_data()
    result_text = await apply_fine_to_user(data.get("target_user_id"), message.from_user.id, data.get("fine_amount"), message.text, bot)
    msg = await message.answer(result_text)
    await state.clear()
    await asyncio.sleep(5)
    await show_admin_panel(msg, state)

@router.message(AdminState.PROMO_CODE_NAME, IsSuperAdmin())
async def promo_name_entered(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    promo_name = message.text.strip().upper()
    existing_promo = await db_manager.get_promo_by_code(promo_name)
    if existing_promo:
        prompt_msg = await message.answer("❌ Промокод с таким названием уже существует. Пожалуйста, придумайте другое название.", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(promo_name=promo_name)
    prompt_msg = await message.answer("Отлично. Теперь введите количество активаций.", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
    await state.set_state(AdminState.PROMO_USES)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.PROMO_USES, IsSuperAdmin())
async def promo_uses_entered(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    if not message.text.isdigit():
        prompt_msg = await message.answer("❌ Пожалуйста, введите целое число.", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    uses = int(message.text)
    if uses <= 0:
        prompt_msg = await message.answer("❌ Количество активаций должно быть больше нуля.", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(promo_uses=uses)
    prompt_msg = await message.answer(f"Принято. Количество активаций: {uses}.\n\nТеперь введите сумму вознаграждения в звездах (например, <code>25</code>).", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
    await state.set_state(AdminState.PROMO_REWARD)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.PROMO_REWARD, IsSuperAdmin())
async def promo_reward_entered(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    try:
        reward = float(message.text.replace(',', '.'))
        if reward <= 0: raise ValueError
    except (ValueError, TypeError):
        prompt_msg = await message.answer("❌ Пожалуйста, введите положительное число (можно дробное, например <code>10.5</code>).", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(promo_reward=reward)
    await message.answer(f"Принято. Награда: {reward} ⭐.\n\nТеперь выберите обязательное условие для получения награды.", reply_markup=inline.get_promo_condition_keyboard())
    await state.set_state(AdminState.PROMO_CONDITION)

@router.callback_query(F.data.startswith("promo_cond:"), AdminState.PROMO_CONDITION, IsSuperAdmin())
async def promo_condition_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    condition = callback.data.split(":")[1]
    data = await state.get_data()
    new_promo = await db_manager.create_promo_code(
        code=data['promo_name'], total_uses=data['promo_uses'],
        reward=data['promo_reward'], condition=condition
    )
    if new_promo and callback.message:
        await callback.message.edit_text(f"✅ Промокод <code>{new_promo.code}</code> успешно создан!", reply_markup=inline.get_back_to_panel_keyboard("panel:manage_promos"))
    elif callback.message:
        await callback.message.edit_text("❌ Произошла ошибка при создании промокода.", reply_markup=inline.get_back_to_panel_keyboard("panel:manage_promos"))
    await state.clear()
    
@router.message(AdminState.BAN_USER_IDENTIFIER, IsSuperAdmin())
async def ban_user_get_identifier(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    
    identifier = message.text.strip()
    user_id_to_ban = await db_manager.find_user_by_identifier(identifier)

    if not user_id_to_ban:
        prompt_msg = await message.answer(f"❌ Пользователь <code>{identifier}</code> не найден.", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_bans"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
        
    user_to_ban = await db_manager.get_user(user_id_to_ban)
    if user_to_ban.is_banned:
        msg = await message.answer(f"Пользователь @{user_to_ban.username} (<code>{user_id_to_ban}</code>) уже забанен.", reply_markup=inline.get_back_to_panel_keyboard("panel:manage_bans"))
        await state.clear()
        return

    await state.set_state(AdminState.BAN_REASON)
    await state.update_data(user_id_to_ban=user_id_to_ban)
    
    prompt_msg = await message.answer(f"Введите причину бана для пользователя @{user_to_ban.username} (<code>{user_id_to_ban}</code>).", reply_markup=inline.get_cancel_inline_keyboard("panel:manage_bans"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AdminState.BAN_REASON, IsSuperAdmin())
async def ban_user_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Причина не может быть пустой. Введите причину текстом.")
        return
        
    await delete_previous_messages(message, state)
    data = await state.get_data()
    user_id_to_ban = data.get("user_id_to_ban")
    ban_reason = message.text

    success = await db_manager.ban_user(user_id_to_ban, ban_reason)
    if not success:
        await message.answer("❌ Произошла ошибка при бане пользователя.")
        await state.clear()
        return

    try:
        user_notification = (
            f"❗️ <b>Ваш аккаунт был заблокирован администратором.</b>\n\n"
            f"<b>Причина:</b> {ban_reason}\n\n"
            "Вам закрыт доступ ко всем функциям бота. "
            "Если вы считаете, что это ошибка, вы можете подать запрос на амнистию командой /unban_request."
        )
        await bot.send_message(user_id_to_ban, user_notification)
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id_to_ban} о бане: {e}")

    msg = await message.answer(f"✅ Пользователь <code>{user_id_to_ban}</code> успешно забанен.", reply_markup=inline.get_back_to_panel_keyboard("panel:manage_bans"))
    await state.clear()


# --- БЛОК: СПИСКИ ЗАБАНЕННЫХ И ПРОМОКОДОВ ---

@router.callback_query(F.data.startswith("banlist:page:"), AdminState.BAN_LIST_VIEW, IsSuperAdmin())
async def banlist_pagination_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[2])
    await show_banned_users_page(callback, state, page)

@router.callback_query(F.data.startswith("promolist:page:"), AdminState.PROMO_LIST_VIEW, IsSuperAdmin())
async def promolist_pagination_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[2])
    await show_promo_codes_page(callback, state, page)

@router.callback_query(F.data == "promolist:delete_start", AdminState.PROMO_LIST_VIEW, IsSuperAdmin())
async def promo_delete_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminState.PROMO_DELETE_CONFIRM)
    prompt_msg = await callback.message.answer(
        "Введите ID или название промокода, который хотите удалить.",
        reply_markup=inline.get_cancel_inline_keyboard("panel:manage_promos")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AdminState.PROMO_DELETE_CONFIRM, IsSuperAdmin())
async def process_delete_promo_id(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    
    identifier = message.text.strip()
    promo_to_delete = None
    
    if identifier.isdigit():
        promo_id = int(identifier)
        promo_to_delete = await db_manager.get_promo_by_id(promo_id) 
    else:
        promo_to_delete = await db_manager.get_promo_by_code(identifier)

    if not promo_to_delete:
        await message.answer(f"❌ Промокод '{identifier}' не найден.")
        await state.set_state(AdminState.PROMO_LIST_VIEW)
        await show_promo_codes_page(message, state, 1)
        return

    success = await db_manager.delete_promo_code(promo_to_delete.id)
    if success:
        await message.answer(f"✅ Промокод `{promo_to_delete.code}` и все его активации были успешно удалены.")
    else:
        await message.answer(f"❌ Произошла ошибка при удалении промокода `{promo_to_delete.code}`.")
        
    await state.set_state(AdminState.PROMO_LIST_VIEW)
    await show_promo_codes_page(message, state, 1)

# --- БЛОК: УПРАВЛЕНИЕ АМНИСТИЯМИ ---

@router.callback_query(F.data.startswith("amnesty:page:"), AdminState.AMNESTY_LIST_VIEW, IsSuperAdmin())
async def amnesty_pagination_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[2])
    await show_amnesty_page(callback, state, page)

@router.callback_query(F.data.startswith("amnesty:action:"), AdminState.AMNESTY_LIST_VIEW, IsSuperAdmin())
async def amnesty_action_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, action, request_id_str = callback.data.split(":")
    request_id = int(request_id_str)
    admin_id = callback.from_user.id

    success, message_text = await process_unban_request_logic(bot, request_id, action, admin_id)
    
    await callback.answer(message_text, show_alert=True)
    
    await show_amnesty_page(callback, state, 1)