# file: handlers/promo.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
import logging

from states.user_states import UserState
from logic.promo_logic import activate_promo_code_logic

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("promo"))
async def promo_start(message: Message, state: FSMContext):
    """Начало процесса ввода промокода."""
    await state.set_state(UserState.PROMO_ENTER_CODE)
    await message.answer("Пожалуйста, введите ваш промокод:")

@router.message(UserState.PROMO_ENTER_CODE)
async def promo_entered(message: Message, state: FSMContext):
    """Обработка введенного промокода."""
    if not message.text:
        await message.answer("Пожалуйста, введите промокод текстом.")
        return
    
    promo_code_text = message.text.strip()
    user_id = message.from_user.id
    
    # Вызываем основную логику из отдельного файла
    response_message = await activate_promo_code_logic(user_id, promo_code_text)
    
    await message.answer(response_message)
    await state.clear()

