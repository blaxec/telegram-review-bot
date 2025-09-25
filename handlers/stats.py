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

async def format_stats_text(top_users: list) -> str:
    """Форматирует текст для сообщения со статистикой."""
    reward_settings = await db_manager.get_reward_settings()
    rewards_map = {setting.place: setting.reward_amount for setting in reward_settings if setting.reward_amount > 0}

    if not top_users:
        return "📊 <i>Топ пользователей</i>\n\nПока в рейтинге никого нет."

    stats_text = "📊 <i>Топ-10 пользователей по балансу</i> 🏆\n\n"
    place_emojis = {
        1: "🥇", 2: "🥈", 3: "🥉",
        4: "4️⃣", 5: "5️⃣", 6: "6️⃣",
        7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"
    }

    for i, (user_id, display_name, balance, review_count) in enumerate(top_users, 1):
        user_display = display_name if display_name else "Скрытый пользователь"
        reward_info = ""
        if i in rewards_map and rewards_map[i] > 0:
            reward_info = f" (🎁 Приз: {rewards_map[i]} ⭐)"
        
        stats_text += (
            f"{place_emojis.get(i, '🔹')} <i>{user_display}</i>{reward_info}\n"
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
            error_text = "Не удалось загрузить ваш профиль для отображения статистики."
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(error_text)
            else:
                await message_or_callback.answer(error_text, show_alert=True)
            return

        is_anonymous = user.is_anonymous_in_stats
        stats_text = await format_stats_text(top_users)
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

# --- ИЗМЕНЕННЫЙ ОБРАБОТЧИК ---
@router.message(F.text == '📊 Статистика', UserState.MAIN_MENU)
async def stats_handler_message(message: Message, state: FSMContext):
    """Обработчик нажатия на кнопку 'Статистика'."""
    await show_stats_menu(message)


@router.callback_query(F.data == 'profile_toggle_anonymity')
async def toggle_anonymity_handler(callback: CallbackQuery):
    """Обрабатывает переключение анонимности."""
    await callback.answer()
    new_status = await db_manager.toggle_anonymity(callback.from_user.id)
    # После переключения просто обновляем меню статистики
    await show_stats_menu(callback)