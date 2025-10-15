# file: handlers/admin_scenarios.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import db_manager
from keyboards import inline
from states.user_states import AdminState
from utils.access_filters import IsSuperAdmin
from config import AI_SCENARIO_CATEGORIES

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("scenarios"), IsSuperAdmin())
async def scenarios_main_menu(message: Message):
    """Главное меню управления банком сценариев."""
    await message.answer(
        "✍️ **Управление банком сценариев для AI**",
        reply_markup=inline.get_scenarios_main_menu_keyboard()
    )

@router.callback_query(F.data == "scenarios:back_to_main")
async def back_to_scenarios_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "✍️ **Управление банком сценариев для AI**",
        reply_markup=inline.get_scenarios_main_menu_keyboard()
    )

@router.callback_query(F.data == "scenarios:add")
async def add_scenario_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.SCENARIO_CHOOSING_CATEGORY)
    await callback.message.edit_text(
        "Выберите категорию для нового сценария:",
        reply_markup=inline.get_scenario_category_keyboard(AI_SCENARIO_CATEGORIES, "scenarios:set_category")
    )

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
    data = await state.get_data()
    category = data.get("scenario_category")
    text = message.text

    await db_manager.create_ai_scenario(category, text)
    await message.answer(f"✅ Сценарий для категории '{category}' успешно добавлен!")
    
    await state.clear()
    await scenarios_main_menu(message)

@router.callback_query(F.data == "scenarios:view")
async def view_scenarios_start(callback: CallbackQuery):
    categories = await db_manager.get_all_scenario_categories()
    if not categories:
        await callback.answer("Сценарии еще не добавлены.", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите категорию для просмотра сценариев:",
        reply_markup=inline.get_scenario_category_keyboard(categories, "scenarios:view_category")
    )

@router.callback_query(F.data.startswith("scenarios:view_category:"))
async def view_scenarios_by_category(callback: CallbackQuery):
    category = callback.data.split(":", 2)[2]
    scenarios = await db_manager.get_ai_scenarios_by_category(category)
    await callback.message.edit_text(
        f"Сценарии в категории **{category}**:",
        reply_markup=inline.get_scenario_list_keyboard(scenarios)
    )

@router.callback_query(F.data.startswith("scenarios:delete:"))
async def delete_scenario(callback: CallbackQuery):
    scenario_id = int(callback.data.split(":")[2])
    deleted = await db_manager.delete_ai_scenario(scenario_id)
    if deleted:
        await callback.answer("Сценарий удален.", show_alert=True)
        # Обновляем список
        await view_scenarios_start(callback)
    else:
        await callback.answer("Не удалось удалить сценарий.", show_alert=True)