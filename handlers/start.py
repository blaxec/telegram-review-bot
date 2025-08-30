# file: handlers/start.py

import re
import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from keyboards import reply, inline
from database import db_manager
from config import Durations, TESTER_IDS
from references import reference_manager

router = Router()

ACTIVE_TASK_STATES = [
    UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE,
    UserState.GOOGLE_REVIEW_AWAITING_ADMIN_TEXT,
    UserState.GOOGLE_REVIEW_TASK_ACTIVE,
    UserState.GOOGLE_REVIEW_AWAITING_SCREENSHOT,
    UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE,
    UserState.YANDEX_REVIEW_AWAITING_ADMIN_TEXT,
    UserState.YANDEX_REVIEW_TASK_ACTIVE,
    UserState.YANDEX_REVIEW_AWAITING_SCREENSHOT,
]

async def schedule_message_deletion(message: Message, delay: int):
    """Планирует удаление сообщения через заданную задержку."""
    async def delete_after_delay():
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    asyncio.create_task(delete_after_delay())

# --- НАЧАЛО ИЗМЕНЕНИЙ: Добавлена диагностическая команда /getstate ---
@router.message(Command("getstate"), F.from_user.id.in_(TESTER_IDS))
async def get_current_state(message: Message, state: FSMContext):
    """
    [ТЕСТОВАЯ КОМАНДА] Отправляет в чат текущее состояние FSM.
    """
    current_state = await state.get_state()
    await message.answer(f"Текущее состояние FSM: `{current_state}`")
# --- КОНЕЦ ИЗМЕНЕНИЙ ---


@router.message(CommandStart(), StateFilter(*ACTIVE_TASK_STATES))
async def start_while_busy_handler(message: Message):
    """Обрабатывает команду /start, когда пользователь выполняет задание."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    
    response_msg = await message.answer(
        "❗️ Вы сейчас выполняете задание. Пожалуйста, завершите его.\n\n"
        "Если вы хотите отменить задание, воспользуйтесь кнопкой «❌ Отмена»."
    )
    asyncio.create_task(schedule_message_deletion(response_msg, 10))


@router.message(CommandStart(), ~StateFilter(*ACTIVE_TASK_STATES))
async def start_handler(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    
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
        "👋 **Добро пожаловать!**\n\n"
        "Я бот, который поможет вам зарабатывать звезды за выполнение простых заданий.\n\n"
        "Прежде чем мы начнем, пожалуйста, ознакомьтесь с парой моментов о конфиденциальности:\n\n"
        "🔹 **Для проверки отзывов** нам понадобится скриншот вашего профиля в Google/Яндекс Картах.\n"
        "🔹 **При создании Gmail** мы попросим модель вашего устройства, чтобы избежать дубликатов.\n\n"
        "Ваши данные используются *только* для работы бота и никогда не передаются третьим лицам. "
        "Нажимая кнопку ниже, вы подтверждаете, что прочитали и согласны с этими условиями."
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
        pass
        
    try:
        if callback.message:
            await callback.message.edit_text("Вы приняли соглашение.")
            await schedule_message_deletion(callback.message, Durations.DELETE_WELCOME_MESSAGE_DELAY)
    except TelegramBadRequest:
        pass

    await state.set_state(UserState.MAIN_MENU)
    if callback.message:
        welcome_msg = await callback.message.answer(
            "Добро пожаловать в главное меню!",
            reply_markup=reply.get_main_menu_keyboard()
        )
        await schedule_message_deletion(welcome_msg, Durations.DELETE_WELCOME_MESSAGE_DELAY)


# --- Универсальные обработчики отмены и возврата ---

@router.message(F.text == '❌ Отмена')
async def cancel_handler_reply(message: Message, state: FSMContext):
    """Обработчик кнопки 'Отмена', сбрасывает любое состояние."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
        
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять. Вы уже в главном меню.")
        return

    await reference_manager.release_reference_from_user(message.from_user.id, 'available')

    await state.clear()
    await message.answer(
        "Действие отменено.",
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
        if callback.message:
            await callback.message.delete()
    except TelegramBadRequest as e:
        print(f"Error deleting message: {e}")

    current_state = await state.get_state()
    if current_state is None:
        return

    await reference_manager.release_reference_from_user(callback.from_user.id, 'available')

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)


@router.callback_query(F.data == 'go_main_menu')
async def go_main_menu_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик для кнопки 'Назад', ведущей в главное меню."""
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        if callback.message:
            await callback.message.delete()
    except TelegramBadRequest as e:
        print(f"Error deleting message on go_main_menu: {e}")
        
    await state.set_state(UserState.MAIN_MENU)
    if callback.message:
        menu_msg = await callback.message.answer(
            "Главное меню:",
            reply_markup=reply.get_main_menu_keyboard()
        )
        await schedule_message_deletion(menu_msg, Durations.DELETE_WELCOME_MESSAGE_DELAY)