
import re
import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from keyboards import reply, inline
from database import db_manager

router = Router()

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    await state.clear()
    
    referrer_id = None
    args = message.text.split()
    if len(args) > 1:
        if args[1].isdigit():
            ref_id = int(args[1])
            if ref_id != message.from_user.id:
                referrer_id = ref_id

    await db_manager.ensure_user_exists(
        user_id=message.from_user.id,
        username=message.from_user.username,
        referrer_id=referrer_id
    )

    welcome_text = (
        "Привет! Я помогу тебе зарабатывать звезды за твои отзывы.\n\n"
        "Прежде чем начать, ознакомься с нашим соглашением:\n\n"
        "✅ Мы запрашиваем разрешение на просмотр твоего личного профиля в Яндекс.Картах и Google.Картах для верификации твоих отзывов.\n"
        "✅ Твоя информация никогда не будет передана третьим лицам без твоего явного согласия. Все данные будут использоваться исключительно для функционирования нашего сервиса."
    )
    
    await message.answer(
        welcome_text,
        reply_markup=inline.get_agreement_keyboard()
    )


@router.callback_query(F.data == 'agree_agreement')
async def process_agreement(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'Согласен'."""
    try:
        await callback.answer("Добро пожаловать!")
    except TelegramBadRequest:
        pass # Игнорируем ошибку, если запрос устарел
        
    try:
        await callback.message.edit_text("Вы приняли соглашение.")
    except TelegramBadRequest:
        pass # Игнорируем, если сообщение не может быть изменено

    await state.set_state(UserState.MAIN_MENU)
    await callback.message.answer(
        "Добро пожаловать в главное меню!",
        reply_markup=reply.get_main_menu_keyboard()
    )


# --- Универсальные обработчики отмены и возврата ---

@router.message(F.text.lower() == 'отмена')
async def cancel_handler_reply(message: Message, state: FSMContext):
    """Обработчик кнопки 'Отмена', сбрасывает любое состояние."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять. Вы уже в главном меню.")
        return

    await state.clear()
    await message.answer(
        "Действие отменено. Возвращаю вас в главное меню.",
        reply_markup=reply.get_main_menu_keyboard()
    )
    await state.set_state(UserState.MAIN_MENU)


@router.callback_query(F.data == 'cancel_action')
async def cancel_handler_inline(callback: CallbackQuery, state: FSMContext):
    """Обработчик инлайн-кнопки отмены."""
    try:
        await callback.answer("Действие отменено")
    except TelegramBadRequest:
        pass
    
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        print(f"Error deleting message: {e}")

    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await callback.message.answer(
        "Действие отменено. Возвращаю вас в главное меню.",
        reply_markup=reply.get_main_menu_keyboard()
    )
    await state.set_state(UserState.MAIN_MENU)


@router.callback_query(F.data == 'go_main_menu')
async def go_main_menu_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик для кнопки 'Назад', ведущей в главное меню."""
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        print(f"Error deleting message on go_main_menu: {e}")
        
    await state.set_state(UserState.MAIN_MENU)
    await callback.message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=reply.get_main_menu_keyboard()
    )