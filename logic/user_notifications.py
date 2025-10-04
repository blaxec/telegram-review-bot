# file: logic/user_notifications.py

import datetime
import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from keyboards import inline, reply
from database import db_manager
from references import reference_manager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic.notification_manager import send_notification_to_admins
from states.user_states import UserState

logger = logging.getLogger(__name__)


async def send_cooldown_expired_notification(bot: Bot, user_id: int, platform: str):
    """Отправляет пользователю уведомление об истечении кулдауна."""
    platform_names = {
        'google': 'Google Карты',
        'yandex_with_text': 'Яндекс Карты (с текстом)',
        'yandex_without_text': 'Яндекс Карты (без текста)',
        'gmail': 'создание Gmail аккаунтов'
    }
    platform_name = platform_names.get(platform, platform)
    
    try:
        await bot.send_message(
            user_id,
            f"⏰ Ваш кулдаун для задания '<b>{platform_name}</b>' закончился! Вы снова можете выполнять эту задачу."
        )
        logger.info(f"Sent cooldown expiration notification to user {user_id} for platform {platform}.")
    except (TelegramNetworkError, TelegramBadRequest):
        logger.warning(f"Could not send cooldown notification to user {user_id} (bot might be blocked).")
    except Exception as e:
        logger.error(f"Unknown error sending cooldown notification to {user_id}: {e}")


def format_timedelta(td: datetime.timedelta) -> str:
    """Форматирует оставшееся время в ЧЧ:ММ:СС."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

async def send_liking_confirmation_button(bot: Bot, user_id: int, state: FSMContext):
    """Отправляет пользователю кнопку подтверждения после этапа 'лайков' и удаляет сообщение с таймером."""
    try:
        user_data = await state.get_data()
        timer_message_id = user_data.get('current_task_message_id')
        if timer_message_id:
            try:
                await bot.delete_message(user_id, timer_message_id)
            except TelegramBadRequest:
                pass
        
        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_liking_confirmation_keyboard()
        )
    except (TelegramNetworkError, TelegramBadRequest) as e:
        logger.error(f"Не удалось отправить кнопку подтверждения 'лайков' пользователю {user_id} (возможно, бот заблокирован): {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки 'лайков' пользователю {user_id}: {e}")

async def send_yandex_liking_confirmation_button(bot: Bot, user_id: int, state: FSMContext):
    """Отправляет пользователю кнопку подтверждения после этапа 'прогрева' Yandex и удаляет сообщение с таймером."""
    try:
        user_data = await state.get_data()
        timer_message_id = user_data.get('current_task_message_id')
        if timer_message_id:
            try:
                await bot.delete_message(user_id, timer_message_id)
            except TelegramBadRequest:
                pass
                
        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_yandex_liking_confirmation_keyboard()
        )
    except (TelegramNetworkError, TelegramBadRequest) as e:
        logger.error(f"Не удалось отправить кнопку подтверждения 'прогрева' Yandex пользователю {user_id} (возможно, бот заблокирован): {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки 'прогрева' Yandex пользователю {user_id}: {e}")

async def send_confirmation_button(bot: Bot, user_id: int, platform: str, state: FSMContext):
    """Отправляет пользователю кнопку подтверждения основного задания и удаляет сообщение с таймером."""
    try:
        user_data = await state.get_data()
        timer_message_id = user_data.get('current_task_message_id')
        if timer_message_id:
            try:
                await bot.delete_message(user_id, timer_message_id)
            except TelegramBadRequest:
                pass

        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_task_confirmation_keyboard(platform)
        )
    except (TelegramNetworkError, TelegramBadRequest) as e:
        logger.error(f"Не удалось отправить кнопку подтверждения пользователю {user_id} для платформы {platform} (возможно, бот заблокирован): {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки подтверждения пользователю {user_id}: {e}")

async def handle_task_timeout(bot: Bot, storage: BaseStorage, user_id: int, platform: str, message_to_admins: str, scheduler: AsyncIOScheduler):
    """Обрабатывает истечение времени на любом из этапов задания."""
    state = FSMContext(storage=storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    
    current_state_str = await state.get_state()
    allowed_states_for_timeout = [
        UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE,
        UserState.GOOGLE_REVIEW_TASK_ACTIVE,
        UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE,
        UserState.YANDEX_REVIEW_TASK_ACTIVE,
    ]
    if not current_state_str or current_state_str not in [s.state for s in allowed_states_for_timeout]:
        logger.info(f"Timeout handler for user {user_id} triggered, but state is '{current_state_str}'. Aborting.")
        return

    logger.info(f"Timeout for user {user_id} on platform {platform}. Current state: {current_state_str}. Releasing reference and setting cooldown.")
    
    user_data = await state.get_data()
    await reference_manager.release_reference_from_user(user_id, final_status='available')
    
    cooldown_hours = 72
    platform_for_cooldown = platform.replace('_maps', '')
    cooldown_end_time = await db_manager.set_platform_cooldown(user_id, platform_for_cooldown, cooldown_hours)
    if cooldown_end_time:
        scheduler.add_job(
            send_cooldown_expired_notification, 
            'date', 
            run_date=cooldown_end_time, 
            args=[bot, user_id, platform_for_cooldown]
        )

    await state.clear()
    
    timeout_message = "Время, выделенное на выполнение работы, истекло. Следующая возможность написать отзыв будет через три дня (72:00:00)."
    
    admin_notification = f"❗️ Пользователь @{user_data.get('username', '???')} (ID: {user_id}) не успел выполнить задание ({message_to_admins}) вовремя. Ссылка была возвращена в пул доступных."
    
    try:
        await bot.send_message(user_id, timeout_message, reply_markup=reply.get_main_menu_keyboard())
        
        task_type = None
        if 'google' in platform:
            task_type = "google_issue_text"
        elif 'yandex' in platform:
            task_type = "yandex_with_text_issue_text"

        if task_type:
            # Используем import здесь, чтобы избежать циклических зависимостей
            from logic.notification_manager import send_notification_to_admins
            await send_notification_to_admins(bot, text=admin_notification, task_type=task_type, scheduler=scheduler)

    except Exception as e:
        logger.error(f"Ошибка при обработке таймаута для {user_id}: {e}")