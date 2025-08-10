# file: handlers/admin.py

import logging
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState, AdminState
from keyboards import inline
from config import ADMIN_IDS
from database import db_manager
from references import reference_manager
from logic.admin_logic import process_add_links_logic

router = Router()
logger = logging.getLogger(__name__)

ADMINS = set(ADMIN_IDS)

# --- БЛОК УПРАВЛЕНИЯ ССЫЛКАМИ (С ВОССТАНОВЛЕННЫМ FSM) ---

@router.message(Command("admin_refs"), F.from_user.id.in_(ADMINS))
async def admin_refs_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())

@router.callback_query(F.data.startswith("admin_refs:add:"), F.from_user.id.in_(ADMINS))
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(':')[2]
    state_map = {"google_maps": AdminState.ADD_GOOGLE_REFERENCE, "yandex_maps": AdminState.ADD_YANDEX_REFERENCE}
    current_state = state_map.get(platform)
    if current_state:
        await state.set_state(current_state) # <-- Возвращаем установку состояния
        await state.update_data(platform=platform)
        await callback.message.edit_text(f"Отправьте ссылки для **{platform}**, каждую с новой строки.", reply_markup=inline.get_back_to_admin_refs_keyboard())
    await callback.answer()

@router.message(
    F.from_user.id.in_(ADMINS),
    F.state.in_({AdminState.ADD_GOOGLE_REFERENCE, AdminState.ADD_YANDEX_REFERENCE}), # <-- Возвращаем фильтр по состоянию
    F.text.as_("text")
)
async def admin_add_ref_process(message: Message, state: FSMContext, text: str):
    data = await state.get_data()
    platform = data.get("platform")
    if not platform:
        await message.answer("❌ Произошла ошибка: не удалось определить платформу. Пожалуйста, начните заново.")
        await state.clear()
        return
        
    result_text = await process_add_links_logic(text, platform)
    
    await message.answer(result_text)
    await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())


# --- РАЗМОРАЖИВАЕМ ФУНКЦИЮ ПРОСМОТРА СПИСКА ---

@router.callback_query(F.data.startswith("admin_refs:list:"), F.from_user.id.in_(ADMINS))
async def admin_view_refs_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Загружаю список...")
    platform = callback.data.split(':')[2]
    all_links = await reference_manager.get_all_references(platform)
    await callback.message.edit_text(f"Список ссылок для **{platform}**:", reply_markup=inline.get_back_to_admin_refs_keyboard())
    if not all_links:
        await callback.message.answer("В базе нет ссылок для этой платформы.")
        return
    message_ids = []
    for link in all_links:
        icons = {"available": "🟢", "assigned": "🟡", "used": "🔴", "expired": "⚫"}
        user_info = f"-> ID: {link.assigned_to_user_id}" if link.assigned_to_user_id else ""
        text = f"{icons.get(link.status, '❓')} **ID:{link.id}** | `{link.status}` {user_info}\n🔗 `{link.url}`"
        msg = await callback.message.answer(text, reply_markup=inline.get_delete_ref_keyboard(link.id), disable_web_page_preview=True)
        message_ids.append(msg.message_id)
    await state.update_data(link_message_ids=message_ids)

# --- Остальные функции пока отключены ---
@router.callback_query(F.data.startswith("admin_refs:stats:"), F.from_user.id.in_(ADMINS))
async def admin_view_refs_stats(callback: CallbackQuery):
    await callback.answer("Функция статистики временно отключена для диагностики.", show_alert=True)

@router.callback_query(F.data.startswith("admin_refs:delete:"), F.from_user.id.in_(ADMINS))
async def admin_delete_ref(callback: CallbackQuery):
    await callback.answer("Функция удаления временно отключена для диагностики.", show_alert=True)