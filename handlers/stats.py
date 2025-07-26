import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from states.user_states import UserState
from database import db_manager

router = Router()
logger = logging.getLogger(__name__)

# Словарь для хранения активных сообщений со статистикой {chat_id: message_id}
active_stats_messages = {}
# ID запущенной задачи в шедулере
scheduler_job_id = "live_stats_update"

def format_stats_text(top_users: list) -> str:
    """Форматирует текст для сообщения со статистикой."""
    if not top_users:
        return "📊 **Топ пользователей**\n\nПока в рейтинге никого нет."

    stats_text = "📊 **Топ-10 пользователей по балансу** 🏆 (обновляется раз в минуту)\n\n"
    place_emojis = {
        1: "🥇", 2: "🥈", 3: "🥉",
        4: "4️⃣", 5: "5️⃣", 6: "6️⃣",
        7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"
    }

    for i, (display_name, balance, review_count) in enumerate(top_users, 1):
        # Если юзернейм None (например, в старых записях), используем плейсхолдер
        user_display = display_name if display_name else "Скрытый пользователь"
        stats_text += (
            f"{place_emojis.get(i, '🔹')} **{user_display}**\n"
            f"   - Баланс: **{balance:.2f}** ⭐\n"
            f"   - Отзывов одобрено: **{review_count}**\n\n"
        )
    return stats_text

async def update_stats_messages(bot: Bot):
    """Задача, которая обновляет все активные сообщения со статистикой."""
    if not active_stats_messages:
        return # Нечего обновлять

    logger.info(f"Running stats update for {len(active_stats_messages)} users.")
    
    # Получаем свежие данные один раз для всех
    top_users = await db_manager.get_top_10_users()
    new_text = format_stats_text(top_users)
    
    # Копируем словарь, так как он может измениться во время итерации
    current_viewers = list(active_stats_messages.items())
    
    for chat_id, message_id in current_viewers:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_text
            )
        except TelegramBadRequest as e:
            # Если сообщение не изменено или удалено, просто удаляем его из списка
            if "message is not modified" in str(e) or "message to edit not found" in str(e):
                logger.warning(f"Message {message_id} in chat {chat_id} not found or not modified. Removing from live updates.")
                active_stats_messages.pop(chat_id, None)
            else:
                logger.error(f"Failed to edit stats message for chat {chat_id}: {e}")
                active_stats_messages.pop(chat_id, None)
        except Exception as e:
            logger.error(f"Unexpected error updating stats for chat {chat_id}: {e}")
            active_stats_messages.pop(chat_id, None)


@router.message(F.text == 'Статистика', UserState.MAIN_MENU)
async def stats_handler(message: Message, bot: Bot, scheduler: AsyncIOScheduler):
    """Обработчик для раздела 'Статистика', запускающий живое обновление."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    # Получаем начальные данные
    top_users = await db_manager.get_top_10_users()
    initial_text = format_stats_text(top_users)
    
    sent_message = await message.answer(initial_text)

    # Сохраняем сообщение для будущих обновлений
    active_stats_messages[message.chat.id] = sent_message.message_id
    
    # Запускаем задачу обновления, если она еще не запущена
    if not scheduler.get_job(scheduler_job_id):
        try:
            scheduler.add_job(
                update_stats_messages,
                'interval',
                minutes=1,
                id=scheduler_job_id,
                args=[bot]
            )
            logger.info("Live stats update job scheduled.")
        except Exception as e:
            logger.error(f"Could not schedule live stats job: {e}")