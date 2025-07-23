from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from states.user_states import UserState
from keyboards.inline import get_back_to_main_menu_keyboard
from config import ADMIN_ID_1, ADMIN_ID_2

router = Router()

@router.message(F.text == 'Поддержка', UserState.MAIN_MENU)
async def support_handler(message: Message):
    """Обработчик для раздела 'Поддержка'."""
    support_text = (
        "❓ Нужна помощь?\n\n"
        "Если у вас возникли вопросы или проблемы, свяжитесь с нашей службой поддержки:\n\n"
        f"👤 Администратор по отзывам и ссылкам: @kotenokangel\n"
        f"👤 Главный администратор: @SHAD0W_F4"
    )
    await message.answer(support_text)