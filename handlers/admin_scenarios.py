# file: handlers/admin_scenarios.py

import logging
import random # Added: for random scenario selection
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
    await delete_and_clear_prompt(message, state) # Added: delete prompt and user message
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
        # Обновляем список, чтобы отразить удаление
        category = callback.data.split(":")[3] # Assuming category is part of callback data for a smooth return
        scenarios = await db_manager.get_ai_scenarios_by_category(category)
        if scenarios:
            await callback.message.edit_text(
                f"Сценарии в категории **{category}**:",
                reply_markup=inline.get_scenario_list_keyboard(scenarios)
            )
        else:
            await callback.message.edit_text(
                f"В категории **{category}** нет сценариев.",
                reply_markup=inline.get_scenario_category_keyboard(await db_manager.get_all_scenario_categories(), "scenarios:view_category")
            )
    else:
        await callback.answer("Не удалось удалить сценарий.", show_alert=True)

@router.callback_query(F.data.startswith("scenarios:use:"))
async def use_scenario_from_list(callback: CallbackQuery, state: FSMContext, bot: Bot):
    scenario_id = int(callback.data.split(":")[2])
    scenario_obj = await db_manager.get_ai_scenario_by_id(scenario_id)

    if not scenario_obj:
        await callback.answer("Сценарий не найден.", show_alert=True)
        return

    # Assuming `admin_moderation` will call this to set up the AI generation
    # We need to transfer necessary data from current state to the AI generation process
    # For now, we'll just put the scenario text into state.
    current_data = await state.get_data()
    # These should be present in state from the admin_provide_text menu
    platform = current_data.get('platform')
    user_id_str = current_data.get('target_user_id')
    link_id_str = current_data.get('target_link_id')
    photo_required = current_data.get('photo_required')

    if not all([platform, user_id_str, link_id_str]):
        await callback.answer("Ошибка: не удалось восстановить контекст задачи. Начните заново.", show_alert=True)
        return

    await state.update_data(
        ai_scenario=scenario_obj.text,
        scenario_id_from_template=scenario_obj.id # Store which template was used
    )
    
    # Simulate proceeding to AI generation with the selected scenario
    from handlers.admin_moderation import admin_process_ai_scenario # Lazy import to avoid circular dependency
    dummy_message = callback.message # Reuse callback.message as a dummy message
    dummy_message.text = scenario_obj.text # Set the text of the dummy message to the scenario text
    
    await callback.message.edit_text(f"Выбран сценарий:\n\n`{scenario_obj.text}`\n\nНажмите 'Сгенерировать' для использования или 'Редактировать' для изменения.",
                                     reply_markup=inline.get_ai_template_use_keyboard())
    await state.set_state(AdminState.AI_AWAITING_MODERATION) # Go to moderation state, but with scenario already set

@router.callback_query(F.data == "ai_template:confirm_use", AdminState.AI_AWAITING_MODERATION)
async def confirm_template_use(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    scenario = data.get('ai_scenario')
    platform = data.get('platform')
    user_id_str = data.get('target_user_id')
    link_id_str = data.get('target_link_id')
    photo_required = data.get('photo_required')

    if not scenario:
        await callback.answer("Сценарий для генерации не найден.", show_alert=True)
        return

    from handlers.admin_moderation import admin_process_ai_scenario_from_template # Lazy import
    # Simulate a message with the scenario text to trigger the AI generation logic
    dummy_message = callback.message
    dummy_message.text = scenario # This is the scenario text from the template
    
    await admin_process_ai_scenario_from_template(dummy_message, state, bot) # Use the specific function
    await callback.answer()

@router.callback_query(F.data == "ai_template:edit_text", AdminState.AI_AWAITING_MODERATION)
async def edit_template_text(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_scenario = data.get('ai_scenario', '')
    
    await state.set_state(AdminState.waiting_for_edited_scenario_text)
    prompt_msg = await callback.message.edit_text(
        f"Отредактируйте текст сценария:\n\n`{current_scenario}`",
        reply_markup=inline.get_cancel_inline_keyboard("ai_template:cancel_edit")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.waiting_for_edited_scenario_text)
async def process_edited_scenario_text(message: Message, state: FSMContext, bot: Bot):
    await delete_and_clear_prompt(message, state)
    edited_scenario = message.text

    if not edited_scenario:
        await message.answer("Сценарий не может быть пустым. Пожалуйста, введите текст.")
        return

    await state.update_data(ai_scenario=edited_scenario)
    
    # Simulate going to moderation with the newly edited scenario
    from handlers.admin_moderation import admin_process_ai_scenario_from_template
    await admin_process_ai_scenario_from_template(message, state, bot) # Reuse the logic that takes scenario from state
    
@router.callback_query(F.data == "ai_template:cancel_edit", AdminState.waiting_for_edited_scenario_text)
async def cancel_edit_scenario_text(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer("Редактирование отменено.")
    data = await state.get_data()
    scenario = data.get('ai_scenario', '') # The original scenario
    
    await state.set_state(AdminState.AI_AWAITING_MODERATION)
    await callback.message.edit_text(f"Выбран сценарий:\n\n`{scenario}`\n\nНажмите 'Сгенерировать' для использования или 'Редактировать' для изменения.",
                                     reply_markup=inline.get_ai_template_use_keyboard())