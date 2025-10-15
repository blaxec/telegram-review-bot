# file: keyboards/games_inline.py

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_games_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪙 Орёл и Решка", callback_data="start_coinflip")
    builder.button(text="⬅️ Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_coinflip_bet_keyboard(play_again: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    bets = [1, 5, 10, 25]
    for bet in bets:
        builder.button(text=f"{bet} ⭐", callback_data=f"bet_{bet}")
    builder.button(text="Другая сумма", callback_data="custom_bet")
    
    back_text = "⬅️ Назад" if not play_again else "⏹️ Закончить игру"
    builder.button(text=back_text, callback_data="back_to_games_menu")
    builder.adjust(4, 1, 1)
    return builder.as_markup()

def get_coinflip_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🦅 Орёл", callback_data="choice_eagle")
    builder.button(text="🪙 Решка", callback_data="choice_tails")
    builder.adjust(2)
    return builder.as_markup()