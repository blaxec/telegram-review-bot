# file: handlers/stats.py
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from database import db_manager
from keyboards import inline

router = Router()
logger = logging.getLogger(__name__)

def format_stats_text(top_users: list) -> str:
    """Форматирует текст для сообщения со статистикой."""
    if not top_users:
        return "📊 <i>Топ пользователей</i>\n\nПока в рейтинге никого нет."

    stats_text = "📊 <i>Топ-10 пользователей по балансу</i> 🏆\n\n"
    place_emojis = {
        1: "🥇", 2: "🥈", 3: "🥉",
        4: "4️⃣", 5: "5️⃣", 6: "6️⃣",
        7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"
    }

    for i, (display_name, balance, review_count) in enumerate(top_users, 1):
        user_display = display_name if display_name else "Скрытый пользователь"
        stats_text += (
            f"{place_emojis.get(i, '🔹')} <i>{user_display}</i>\n"
            f"   - Баланс: <i>{balance:.2f}</i> ⭐\n"
            f"   - Отзывов одобрено: <i>{review_count}</i>\n\n"
        )
    return stats_text

async def show_stats_menu(message_or_callback: Message | CallbackQuery):
    """Отображает меню статистики с защитой от ошибок."""
    user_id = message_or_callback.from_user.id
    
    try:
        await db_manager.ensure_user_exists(user_id, message_or_callback.from_user.username)
        top_users = await db_manager.get_top_10_users()
        user = await db_manager.get_user(user_id)
        
        if not user:
            # Эта ситуация маловероятна после ensure_user_exists, но является защитой
            error_text = "Не удалось загрузить ваш профиль для отображения статистики."
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(error_text)
            else:
                await message_or_callback.answer(error_text, show_alert=True)
            return

        is_anonymous = user.is_anonymous_in_stats
        stats_text = format_stats_text(top_users)
        stats_text += f"\nВаш текущий статус в топе: <i>{'🙈 Анонимный' if is_anonymous else '🐵 Публичный'}</i>"
        keyboard = inline.get_stats_keyboard(is_anonymous=is_anonymous)

        if isinstance(message_or_callback, Message):
            try:
                await message_or_callback.delete()
            except TelegramBadRequest:
                pass
            await message_or_callback.answer(stats_text, reply_markup=keyboard)
        else:
            if message_or_callback.message:
                try:
                    await message_or_callback.message.edit_text(stats_text, reply_markup=keyboard)
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e):
                        logger.warning(f"Error editing stats message: {e}")
                    await message_or_callback.answer()
    
    except Exception as e:
        logger.exception(f"Критическая ошибка при отображении статистики для user {user_id}: {e}")
        error_text = "❌ Произошла ошибка при загрузке статистики. Пожалуйста, попробуйте позже."
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(error_text)
        else:
            await message_or_callback.answer(error_text, show_alert=True)


@router.message(F.text == 'Статистика', UserState.MAIN_MENU)
async def stats_handler(message: Message):
    """Обработчик для раздела 'Статистика'."""
    await show_stats_menu(message)

@router.callback_query(F.data == 'profile_toggle_anonymity')
async def toggle_anonymity_handler(callback: CallbackQuery):
    """Обрабатывает переключение анонимности из меню статистики."""
    new_status = await db_manager.toggle_anonymity(callback.from_user.id)
    status_text = "анонимным" if new_status else "публичным"
    await callback.answer(f"Ваш профиль в топе теперь {status_text}.", show_alert=True)
    await show_stats_menu(callback)