from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру главного меню."""
    kb = [
        [KeyboardButton(text='Профиль'), KeyboardButton(text='Заработок')],
        [KeyboardButton(text='Статистика'), KeyboardButton(text='Поддержка')] # <-- ИЗМЕНЕНО
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    return keyboard

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой 'Отмена'."""
    kb = [
        [KeyboardButton(text='Отмена')]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    return keyboard