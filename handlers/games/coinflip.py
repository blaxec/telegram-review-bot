# handlers/games/coinflip.py
# (Новый файл)

import logging
import random
import asyncio
from aiogram import Router, F, Bot, bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import CoinflipStates
from keyboards import inline
from database import db_manager

router = Router()
logger = logging.getLogger(__name__)

# --- Обработчики игры "Орёл и Решка" ---

@router.message(F.text == '🎲 Игры')
async def games_menu(message: Message):
    await message.answer("Выберите игру:", reply_markup=inline.get_games_menu_keyboard())

@router.callback_query(F.data == "back_to_games_menu")
async def back_to_games_menu(callback: CallbackQuery):
    await callback.message.edit_text("Выберите игру:", reply_markup=inline.get_games_menu_keyboard())

@router.callback_query(F.data == "start_coinflip")
async def start_coinflip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CoinflipStates.waiting_for_bet)
    user = await db_manager.get_user(callback.from_user.id)
    win_streak_text = f"\n\n🔥 Ваша серия побед: {user.win_streak}" if user and user.win_streak > 0 else ""
    
    await callback.message.edit_text(
        "Добро пожаловать в 'Орёл и Решка'! Какую сумму вы хотите поставить? "
        "Учтите, что выигрыш облагается комиссией 5%." + win_streak_text,
        reply_markup=inline.get_coinflip_bet_keyboard()
    )

async def process_bet(callback: CallbackQuery, state: FSMContext, amount: float):
    user = await db_manager.get_user(callback.from_user.id)
    if not user or user.balance < amount:
        await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
        return

    await state.update_data(current_bet_amount=amount)
    await state.set_state(CoinflipStates.waiting_for_choice)
    await callback.message.edit_text(
        f"Ставка принята: {amount:.2f} ⭐. Выберите сторону:",
        reply_markup=inline.get_coinflip_choice_keyboard()
    )

@router.callback_query(F.data.startswith("bet_"), CoinflipStates.waiting_for_bet)
async def handle_fixed_bet(callback: CallbackQuery, state: FSMContext):
    amount = float(callback.data.split("_")[1])
    await process_bet(callback, state, amount)

@router.callback_query(F.data == "custom_bet", CoinflipStates.waiting_for_bet)
async def handle_custom_bet_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CoinflipStates.waiting_for_custom_bet)
    prompt_msg = await callback.message.edit_text("Введите желаемую сумму ставки (например, 50.5):", reply_markup=inline.get_cancel_inline_keyboard("start_coinflip"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(CoinflipStates.waiting_for_custom_bet)
async def handle_custom_bet_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Некорректная сумма. Пожалуйста, введите положительное число.")
        return

    user = await db_manager.get_user(message.from_user.id)
    if not user or user.balance < amount:
        await message.answer("❌ Недостаточно средств на балансе!")
        return

    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try: await bot.delete_message(message.chat.id, prompt_id)
        except: pass
    await message.delete()

    # Имитируем callback для передачи в общую логику
    dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=await message.answer("..."))
    await process_bet(dummy_callback, state, amount)
    await dummy_callback.message.delete()


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

    # Определяем шанс на победу
    if 1 <= bet_amount <= 50: win_chance = 50
    elif 51 <= bet_amount <= 500: win_chance = 30
    else: win_chance = 10

    # Определяем результат
    is_win = random.randint(1, 100) <= win_chance
    is_lucky_coin = random.randint(1, 100) <= 2

    # Определяем множитель комбо
    combo_multiplier = 1.0
    if win_streak >= 5: combo_multiplier = 1.10
    elif win_streak >= 3: combo_multiplier = 1.05

    # Анимация
    final_side = user_choice if is_win else ("Решка" if user_choice == "Орёл" else "Орёл")
    await callback.message.edit_text("Монетка в воздухе...")
    await asyncio.sleep(1.5)

    result_text = ""
    if is_win:
        new_win_streak = win_streak + 1
        base_win = bet_amount * 0.95
        combo_win = base_win * combo_multiplier
        final_win = combo_win * 2 if is_lucky_coin else combo_win
        total_change = final_win - bet_amount

        result_text = f"Выпал {final_side}! Вы победили!\n"
        if is_lucky_coin: result_text += "✨ **Счастливая монетка! Ваш выигрыш удвоен!**\n"
        if combo_multiplier > 1.0: result_text += f"🔥 **Комбо!** Ваша серия побед ({win_streak}) дает бонус +{int((combo_multiplier-1)*100)}%!\n"
        result_text += f"Итоговый выигрыш: **{final_win:.2f} ⭐**\nНовая серия побед: **{new_win_streak}**"
        
        await db_manager.update_user_balance_and_streak(user.id, total_change, new_win_streak)

    else:
        new_win_streak = 0
        total_change = -bet_amount
        result_text = f"Выпал {final_side}! Вы проиграли {bet_amount:.2f} ⭐...\nВаша серия побед сброшена."
        await db_manager.update_user_balance_and_streak(user.id, total_change, new_win_streak)

    await state.set_state(CoinflipStates.waiting_for_bet)
    await callback.message.edit_text(result_text, reply_markup=inline.get_coinflip_bet_keyboard(play_again=True))