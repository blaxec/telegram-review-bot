# file: handlers/admin_scenarios.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from keyboards import inline
from states.user_states import AdminState
from utils.access_filters import IsSuperAdmin

router = Router()
logger = logging.getLogger(__name__)

async def delete_and_clear_prompt(message: Message, state: FSMContext):
    """Удаляет сообщение пользователя и предыдущее сообщение-приглашение от бота."""
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
    await state.update_data(prompt_message_id=None)

@router.message(Command("scenarios"), IsSuperAdmin())
async def scenarios_main_menu(message: Message, state: FSMContext):
    """Главное меню управления банком сценариев."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await state.clear()
    await message.answer(
        "✍️ *Управление банком сценариев для AI*",
        reply_markup=inline.get_scenarios_main_menu_keyboard()
    )

@router.callback_query(F.data == "scenarios:back_to_main")
async def back_to_scenarios_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "✍️ *Управление банком сценариев для AI*",
        reply_markup=inline.get_scenarios_main_menu_keyboard()
    )

# --- Добавление сценария ---
@router.callback_query(F.data == "scenarios:add")
async def add_scenario_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.SCENARIO_CHOOSING_CATEGORY)
    existing_categories = await db_manager.get_all_scenario_categories()
    
    await callback.message.edit_text(
        "Выберите категорию для нового сценария или создайте новую:",
        reply_markup=inline.get_scenario_category_keyboard(sorted(existing_categories), "scenarios:set_category")
    )

@router.callback_query(F.data == "scenarios:add_new_category", AdminState.SCENARIO_CHOOSING_CATEGORY)
async def add_new_category_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.SCENARIO_AWAITING_NEW_CATEGORY)
    prompt_msg = await callback.message.edit_text(
        "Введите название для новой категории:",
        reply_markup=inline.get_cancel_inline_keyboard("scenarios:add")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.SCENARIO_AWAITING_NEW_CATEGORY, F.text)
async def process_new_category_name(message: Message, state: FSMContext):
    category_name = message.text.strip()
    await delete_and_clear_prompt(message, state)
    
    # Имитируем нажатие на кнопку с новой категорией
    dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=message, data=f"scenarios:set_category:{category_name}")
    await set_scenario_category(dummy_callback, state)


@router.callback_query(F.data.startswith("scenarios:set_category:"), AdminState.SCENARIO_CHOOSING_CATEGORY)
async def set_scenario_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 2)[2]
    await state.update_data(scenario_category=category)
    await state.set_state(AdminState.waiting_for_scenario_text)
    prompt_msg = await callback.message.edit_text(
        f"Категория: **{category}**\n\nВведите текст нового сценария:",
        reply_markup=inline.get_cancel_inline_keyboard("scenarios:back_to_main")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.waiting_for_scenario_text)
async def process_new_scenario_text(message: Message, state: FSMContext):
    await delete_and_clear_prompt(message, state)
    data = await state.get_data()
    category = data.get("scenario_category")
    text = message.text

    await db_manager.create_ai_scenario(category, text)
    await message.answer(f"✅ Сценарий для категории '{category}' успешно добавлен!")
    
    await state.clear()
    await scenarios_main_menu(message, state)

# --- Просмотр, редактирование, удаление ---
@router.callback_query(F.data == "scenarios:view")
async def view_scenarios_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    categories = await db_manager.get_all_scenario_categories()
    if not categories:
        await callback.answer("Сценарии еще не добавлены.", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите категорию для просмотра и редактирования сценариев:",
        reply_markup=inline.get_scenario_category_keyboard(sorted(categories), "scenarios:view_category", show_add_new=False)
    )

@router.callback_query(F.data.startswith("scenarios:view_category:"))
async def view_scenarios_by_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 2)[2]
    await state.update_data(current_view_category=category) 
    scenarios = await db_manager.get_ai_scenarios_by_category(category)
    
    if not scenarios:
        await callback.message.edit_text(
            f"В категории **{category}** нет сценариев.",
            reply_markup=inline.get_back_to_scenario_categories_keyboard()
        )
        return

    text = f"Сценарии в категории *{category}*:\n(нажмите на ID для управления)\n\n"
    for s in scenarios:
        text += f"• `{s.id}`: {s.text[:70]}...\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=inline.get_scenario_management_keyboard(category)
    )

@router.callback_query(F.data.startswith("scenarios:manage:"))
async def start_scenario_management(callback: CallbackQuery, state: FSMContext):
    _, action, category = callback.data.split(":")
    
    if action == "delete":
        state_to_set = AdminState.SCENARIO_AWAITING_ID_TO_DELETE
        prompt_text = "Введите ID сценария для *удаления*:"
    elif action == "edit":
        state_to_set = AdminState.SCENARIO_AWAITING_ID_TO_EDIT
        prompt_text = "Введите ID сценария для *редактирования*:"
    else:
        return
        
    await state.set_state(state_to_set)
    await state.update_data(current_view_category=category)
    prompt_msg = await callback.message.edit_text(
        prompt_text,
        reply_markup=inline.get_cancel_inline_keyboard(f"scenarios:view_category:{category}")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.SCENARIO_AWAITING_ID_TO_DELETE, F.text)
async def process_delete_scenario_by_id(message: Message, state: FSMContext):
    data = await state.get_data()
    await delete_and_clear_prompt(message, state)
    
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный числовой ID.")
        return

    scenario_id = int(message.text)
    deleted = await db_manager.delete_ai_scenario(scenario_id)
    
    await message.answer(f"✅ Сценарий #{scenario_id} удален." if deleted else f"❌ Сценарий #{scenario_id} не найден.")
    
    # Возвращаемся к списку
    category = data.get("current_view_category")
    dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=message, data=f"scenarios:view_category:{category}")
    await view_scenarios_by_category(dummy_callback, state)


@router.message(AdminState.SCENARIO_AWAITING_ID_TO_EDIT, F.text)
async def process_edit_scenario_by_id_start(message: Message, state: FSMContext):
    data = await state.get_data()
    await delete_and_clear_prompt(message, state)
    
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный числовой ID.")
        return
        
    scenario_id = int(message.text)
    scenario = await db_manager.get_ai_scenario_by_id(scenario_id)

    if not scenario:
        await message.answer(f"❌ Сценарий #{scenario_id} не найден.")
        return

    await state.set_state(AdminState.SCENARIO_AWAITING_EDITED_TEXT)
    await state.update_data(scenario_to_edit_id=scenario_id)
    
    prompt_msg = await message.answer(
        f"*Редактирование сценария #{scenario_id}*\n\n"
        f"Текущий текст:\n*«{scenario.text}»*\n\n"
        "Отправьте новый текст:",
        reply_markup=inline.get_cancel_inline_keyboard(f"scenarios:view_category:{scenario.category}")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.SCENARIO_AWAITING_EDITED_TEXT, F.text)
async def process_edit_scenario_text_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await delete_and_clear_prompt(message, state)
    
    scenario_id = data.get("scenario_to_edit_id")
    new_text = message.text
    
    updated = await db_manager.update_ai_scenario(scenario_id, new_text)

    await message.answer(f"✅ Сценарий #{scenario_id} обновлен." if updated else f"❌ Не удалось обновить сценарий #{scenario_id}.")
    
    category = data.get("current_view_category")
    dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=message, data=f"scenarios:view_category:{category}")
    await view_scenarios_by_category(dummy_callback, state)