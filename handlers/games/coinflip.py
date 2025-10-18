# file: handlers/games/coinflip.py

import logging
import random
import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from typing import Union

from states.user_states import CoinflipStates
from keyboards import inline
from database import db_manager

router = Router()
logger = logging.getLogger(__name__)

# --- Обработчики игры "Орёл и Решка" ---

@router.message(F.text == '🎲 Игры')
async def games_menu(message: Message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer("Выберите игру:", reply_markup=inline.get_games_menu_keyboard())

@router.callback_query(F.data == "back_to_games_menu")
async def back_to_games_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите игру:", reply_markup=inline.get_games_menu_keyboard())

@router.callback_query(F.data == "start_coinflip")
async def start_coinflip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CoinflipStates.waiting_for_bet)
    user = await db_manager.get_user(callback.from_user.id)
    win_streak_text = f"\n\n🔥 Ваша серия побед: {user.win_streak}" if user and user.win_streak > 0 else ""
    
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    await callback.message.edit_text(
        f"Добро пожаловать в 'Орёл и Решка'!\nВаш баланс: **{balance:.2f} ⭐**\n\n"
        "Какую сумму вы хотите поставить? "
        "Учтите, что выигрыш удваивается." + win_streak_text,
        reply_markup=inline.get_coinflip_bet_keyboard(win_streak=user.win_streak if user else 0)
    )

async def process_bet(message: Message, state: FSMContext, amount: float):
    user_id = message.chat.id
    user = await db_manager.get_user(user_id)
    if not user or user.balance < amount:
        await message.answer("❌ Недостаточно средств на балансе!")
        # Имитируем callback, чтобы вернуться в меню ставок
        dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=message)
        await start_coinflip(dummy_callback, state)
        return

    await state.update_data(current_bet_amount=amount)
    await state.set_state(CoinflipStates.waiting_for_choice)
    
    await message.edit_text(
        f"Ставка принята: **{amount:.2f} ⭐**. Выберите сторону:",
        reply_markup=inline.get_coinflip_choice_keyboard()
    )

@router.callback_query(F.data.startswith("bet_"), CoinflipStates.waiting_for_bet)
async def handle_fixed_bet(callback: CallbackQuery, state: FSMContext):
    amount = float(callback.data.split("_")[1])
    await process_bet(callback.message, state, amount)

@router.callback_query(F.data == "custom_bet", CoinflipStates.waiting_for_bet)
async def handle_custom_bet_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CoinflipStates.waiting_for_custom_bet)
    prompt_msg = await callback.message.edit_text("Введите желаемую сумму ставки (например, 50.5):", reply_markup=inline.get_cancel_inline_keyboard("start_coinflip"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(CoinflipStates.waiting_for_custom_bet)
async def handle_custom_bet_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")

    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Некорректная сумма. Пожалуйста, введите положительное число.")
        await message.delete()
        return

    await message.delete()
    if prompt_id:
        try:
            # Превращаем сообщение с приглашением в игровое поле
            await bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_id, text="Обработка...")
            # Создаем новый объект Message на основе отредактированного
            editable_message = Message(message_id=prompt_id, chat=message.chat, bot=bot)
            await process_bet(editable_message, state, amount)
        except TelegramBadRequest:
            # Если не удалось отредактировать, отправляем новое
            new_msg = await message.answer("Обработка...")
            await process_bet(new_msg, state, amount)
    else:
        new_msg = await message.answer("Обработка...")
        await process_bet(new_msg, state, amount)


@router.callback_query(F.data.startswith("choice_"), CoinflipStates.waiting_for_choice)
async def handle_coinflip_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_choice = "Орёл" if callback.data == "choice_eagle" else "Решка"
    data = await state.get_data()
    bet_amount = data.get("current_bet_amount")

    if not bet_amount:
        await callback.answer("Ошибка: не найдена сумма ставки. Начните заново.", show_alert=True)
        await state.clear()
        await start_coinflip(callback, state)
        return

    user = await db_manager.get_user(callback.from_user.id)
    win_streak = user.win_streak if user else 0

    is_win = random.choice([True, False])
    
    final_side = user_choice if is_win else ("Решка" if user_choice == "Орёл" else "Орёл")
    await callback.message.edit_text("Монетка в воздухе...")
    await asyncio.sleep(1.5)

    result_text = ""
    if is_win:
        new_win_streak = win_streak + 1
        win_amount = bet_amount 
        
        await db_manager.update_user_balance_and_streak(user.id, win_amount, new_win_streak)
        new_balance = user.balance + win_amount

        result_text = f"Выпал **{final_side}**! Вы победили!\n"
        result_text += f"Ваш выигрыш: **{win_amount:.2f} ⭐**\nНовая серия побед: **{new_win_streak}**"

    else:
        new_win_streak = 0
        loss_amount = -bet_amount
        await db_manager.update_user_balance_and_streak(user.id, loss_amount, new_win_streak)
        new_balance = user.balance + loss_amount

        result_text = f"Выпал **{final_side}**! Вы проиграли **{bet_amount:.2f} ⭐**...\nВаша серия побед сброшена."

    await state.set_state(CoinflipStates.waiting_for_bet)
    
    win_streak_text = f"\n\n🔥 Ваша серия побед: **{new_win_streak}**" if new_win_streak > 0 else ""
    balance_text = f"\nВаш баланс: **{new_balance:.2f} ⭐**"
    
    result_text += balance_text + win_streak_text
    
    await callback.message.edit_text(
        result_text, 
        reply_markup=inline.get_coinflip_bet_keyboard(play_again=True, win_streak=new_win_streak)
    )