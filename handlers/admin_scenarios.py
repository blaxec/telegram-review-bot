import logging
import random
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from keyboards import inline
from states.user_states import AdminState
from config import AI_SCENARIO_CATEGORIES
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
    await state.clear()
    await message.answer(
        "✍️ **Управление банком сценариев для AI**",
        reply_markup=inline.get_scenarios_main_menu_keyboard()
    )

@router.callback_query(F.data == "scenarios:back_to_main")
async def back_to_scenarios_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "✍️ **Управление банком сценариев для AI**",
        reply_markup=inline.get_scenarios_main_menu_keyboard()
    )

@router.callback_query(F.data == "scenarios:add")
async def add_scenario_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.SCENARIO_CHOOSING_CATEGORY)
    # Используем категории из конфига + те, что уже есть в базе
    existing_categories = await db_manager.get_all_scenario_categories()
    all_categories = sorted(list(set(AI_SCENARIO_CATEGORIES + existing_categories)))
    
    await callback.message.edit_text(
        "Выберите категорию для нового сценария:",
        reply_markup=inline.get_scenario_category_keyboard(all_categories, "scenarios:set_category")
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
    await delete_and_clear_prompt(message, state)
    data = await state.get_data()
    category = data.get("scenario_category")
    text = message.text

    await db_manager.create_ai_scenario(category, text)
    await message.answer(f"✅ Сценарий для категории '{category}' успешно добавлен!")
    
    await state.clear()
    # Возвращаемся в главное меню сценариев
    await scenarios_main_menu(message, state)

@router.callback_query(F.data == "scenarios:view")
async def view_scenarios_start(callback: CallbackQuery):
    categories = await db_manager.get_all_scenario_categories()
    if not categories:
        await callback.answer("Сценарии еще не добавлены.", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите категорию для просмотра сценариев:",
        reply_markup=inline.get_scenario_category_keyboard(sorted(categories), "scenarios:view_category")
    )

@router.callback_query(F.data.startswith("scenarios:view_category:"))
async def view_scenarios_by_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 2)[2]
    await state.update_data(current_view_category=category) # Сохраняем для возврата
    scenarios = await db_manager.get_ai_scenarios_by_category(category)
    
    if not scenarios:
        await callback.message.edit_text(
            f"В категории **{category}** нет сценариев.",
            reply_markup=inline.get_back_to_scenario_categories_keyboard()
        )
        return

    text = f"Сценарии в категории **{category}**:\n\n"
    
    # Создаем клавиатуру с кнопками удаления
    builder = inline.InlineKeyboardBuilder()
    for s in scenarios:
        text += f"• `{s.id}`: {s.text[:50]}...\n"
        builder.button(text=f"🗑️ Удалить #{s.id}", callback_data=f"scenarios:delete:{s.id}")
    
    builder.button(text="⬅️ К категориям", callback_data="scenarios:view")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "back_to_scenario_categories")
async def back_to_scenario_categories(callback: CallbackQuery):
    await view_scenarios_start(callback)

@router.callback_query(F.data.startswith("scenarios:delete:"))
async def delete_scenario(callback: CallbackQuery, state: FSMContext):
    scenario_id = int(callback.data.split(":")[2])
    deleted = await db_manager.delete_ai_scenario(scenario_id)
    if deleted:
        await callback.answer("Сценарий удален.", show_alert=True)
        data = await state.get_data()
        category = data.get("current_view_category")
        if category:
            callback.data = f"scenarios:view_category:{category}"
            await view_scenarios_by_category(callback, state)
        else:
            await back_to_scenarios_main_menu(callback, state)
    else:
        await callback.answer("Не удалось удалить сценарий.", show_alert=True)