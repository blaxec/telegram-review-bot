    
# file: keyboards/games_inline.py

from aiogram.types import InlineKeyboardMarkup,  InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_games_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪙 Орёл и Решка", callback_data="start_coinflip")
    builder.button(text="⬅️ В профиль", callback_data="go_profile") # Изменено для возврата в профиль
    builder.adjust(1)
    return builder.as_markup()

def get_coinflip_bet_keyboard(play_again: bool = False, win_streak: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    bets = [1, 5, 10, 25]
    for bet in bets:
        builder.button(text=f"{bet} ⭐", callback_data=f"bet_{bet}")
    builder.button(text="Другая сумма", callback_data="custom_bet")
    
    back_text = "⬅️ Меню игр" if not play_again else "⏹️ Закончить"
    back_cb = "back_to_games_menu" if not play_again else "go_profile" # Изменено для возврата в профиль

    builder.button(text=back_text, callback_data=back_cb)
    builder.adjust(4, 1, 1)
    return builder.as_markup()

def get_coinflip_choice_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🦅 Орёл", callback_data="choice_eagle"),
         InlineKeyboardButton(text="🪙 Решка", callback_data="choice_tails")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)