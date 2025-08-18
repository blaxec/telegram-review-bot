# file: logic/user_notifications.py

import datetime
import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
# ИСПРАВЛЕНИЕ: 'Storage' переименован в 'BaseStorage' в новых версиях aiogram
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest

from keyboards import inline, reply
from database import db_manager
from references import reference_manager
from config import FINAL_CHECK_ADMIN

logger = logging.getLogger(__name__)


def format_timedelta(td: datetime.timedelta) -> str:
    """Форматирует оставшееся время в ЧЧ:ММ:СС."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

async def send_liking_confirmation_button(bot: Bot, user_id: int):
    """Отправляет пользователю кнопку подтверждения после этапа 'лайков'."""
    try:
        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_liking_confirmation_keyboard()
        )
    except (TelegramNetworkError, TelegramBadRequest) as e:
        logger.error(f"Не удалось отправить кнопку подтверждения 'лайков' пользователю {user_id} (возможно, бот заблокирован): {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки 'лайков' пользователю {user_id}: {e}")

async def send_yandex_liking_confirmation_button(bot: Bot, user_id: int):
    """Отправляет пользователю кнопку подтверждения после этапа 'прогрева' Yandex."""
    try:
        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_yandex_liking_confirmation_keyboard()
        )
    except (TelegramNetworkError, TelegramBadRequest) as e:
        logger.error(f"Не удалось отправить кнопку подтверждения 'прогрева' Yandex пользователю {user_id} (возможно, бот заблокирован): {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки 'прогрева' Yandex пользователю {user_id}: {e}")

async def send_confirmation_button(bot: Bot, user_id: int, platform: str):
    """Отправляет пользователю кнопку подтверждения основного задания."""
    try:
        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_task_confirmation_keyboard(platform)
        )
    except (TelegramNetworkError, TelegramBadRequest) as e:
        logger.error(f"Не удалось отправить кнопку подтверждения пользователю {user_id} для платформы {platform} (возможно, бот заблокирован): {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки подтверждения пользователю {user_id}: {e}")

async def handle_task_timeout(bot: Bot, storage: BaseStorage, user_id: int, platform: str, message_to_admins: str):
    """Обрабатывает истечение времени на любом из этапов задания."""
    state = FSMContext(storage=storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    
    current_state_str = await state.get_state()
    if not current_state_str:
        logger.info(f"Timeout handler for user {user_id} triggered, but state is None. Aborting.")
        return

    logger.info(f"Timeout for user {user_id} on platform {platform}. Current state: {current_state_str}. Releasing reference and setting cooldown.")
    
    user_data = await state.get_data()
    await reference_manager.release_reference_from_user(user_id, final_status='available')
    await db_manager.set_platform_cooldown(user_id, platform, 72)
    await state.clear()
    
    timeout_message = "Время, выделенное на выполнение работы, истекло. Следующая возможность написать отзыв будет через три дня (72:00:00)."
    admin_notification = f"❗️ Пользователь @{user_data.get('username', '???')} (ID: {user_id}) не успел выполнить задание ({message_to_admins}) вовремя. Ссылка была возвращена в пул доступных."
    
    try:
        await bot.send_message(user_id, timeout_message, reply_markup=reply.get_main_menu_keyboard())
        await bot.send_message(FINAL_CHECK_ADMIN, admin_notification)
    except Exception as e:
        logger.error(f"Ошибка при обработке таймаута для {user_id}: {e}")

async def notify_cooldown_expired(bot: Bot, user_id: int, platform: str):
    """Уведомляет пользователя об окончании кулдауна."""
    platform_names = {
        "google": "Google Картам",
        "yandex": "Yandex Картам"
    }
    platform_name = platform_names.get(platform, platform)
    try:
        await bot.send_message(
            user_id,
            f"🎉 Кулдаун завершен! Теперь вы снова можете писать отзывы в **{platform_name}**."
        )
        logger.info(f"Уведомление об окончании кулдауна для {platform} отправлено пользователю {user_id}.")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление об окончании кулдауна пользователю {user_id}: {e}")