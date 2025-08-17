# file: handlers/promo.py

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
import logging

from states.user_states import UserState
from keyboards import inline, reply
from logic.promo_logic import activate_promo_code_logic
from database import db_manager

router = Router()
logger = logging.getLogger(__name__)

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

@router.message(Command("promo"))
async def promo_start(message: Message, state: FSMContext):
    """Начало процесса ввода промокода."""
    try:
        await message.delete()
    except TelegramBadRequest: pass
    
    await state.set_state(UserState.PROMO_ENTER_CODE)
    prompt_msg = await message.answer(
        "Пожалуйста, введите ваш промокод:",
        reply_markup=inline.get_cancel_inline_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.PROMO_ENTER_CODE)
async def promo_entered(message: Message, state: FSMContext):
    """Обработка введенного промокода."""
    await delete_previous_messages(message, state)
    if not message.text:
        await message.answer("Пожалуйста, введите промокод текстом.")
        return
    
    promo_code_text = message.text.strip()
    user_id = message.from_user.id
    
    response_message, promo_object = await activate_promo_code_logic(user_id, promo_code_text)
    
    if promo_object and promo_object.condition != 'no_condition':
        # Если промокод с условием, показываем кнопки выбора
        await state.set_state(UserState.PROMO_AWAITING_CHOICE)
        await state.update_data(promo_code=promo_object.code)
        await message.answer(response_message, reply_markup=inline.get_promo_conditional_keyboard())
    else:
        # Если промокод без условия или произошла ошибка
        await message.answer(response_message)
        await state.clear()

@router.callback_query(F.data == "promo_start_task", UserState.PROMO_AWAITING_CHOICE)
async def promo_start_task(callback: CallbackQuery, state: FSMContext):
    """Пользователь согласился выполнить задание для промокода."""
    await callback.message.edit_text(
        "Отлично! Ваш промокод активен. Как только вы выполните необходимое задание и оно будет одобрено, награда зачислится на ваш баланс. "
        "Теперь вы можете перейти в раздел 'Заработок'.",
        reply_markup=inline.get_back_to_main_menu_keyboard()
    )
    await state.clear()
    await state.set_state(UserState.MAIN_MENU)

@router.callback_query(F.data == "promo_decline_task", UserState.PROMO_AWAITING_CHOICE)
async def promo_decline_task(callback: CallbackQuery, state: FSMContext):
    """Пользователь отказался от выполнения задания."""
    user_id = callback.from_user.id
    data = await state.get_data()
    promo_code = data.get("promo_code")

    if promo_code:
        # Находим активацию и удаляем ее
        activation = await db_manager.find_pending_promo_activation(user_id)
        if activation:
            await db_manager.delete_promo_activation(activation.id)
            logger.info(f"User {user_id} declined promo task. Activation for '{promo_code}' was deleted.")
    
    await callback.message.edit_text(
        "Вы отказались от задания. Активация промокода отменена. Вы можете использовать другие промокоды.",
        reply_markup=None
    )
    # Возвращаем в главное меню
    await state.clear()
    await callback.message.answer("Вы в главном меню.", reply_markup=reply.get_main_menu_keyboard())
    await state.set_state(UserState.MAIN_MENU)