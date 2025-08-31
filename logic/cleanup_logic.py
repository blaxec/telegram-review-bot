# file: logic/cleanup_logic.py

import logging
from aiogram import Bot
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from keyboards import reply

logger = logging.getLogger(__name__)

async def check_and_expire_links(bot: Bot, storage: BaseStorage):
    """
    Находит "зависшие" в работе ссылки, переводит их в статус 'expired'
    и уведомляет пользователей об отмене задания.
    Запускается по расписанию.
    """
    logger.info("Starting scheduled job: check_and_expire_links")
    try:
        # Находим и обновляем ссылки в одной транзакции, получаем список "пострадавших"
        expired_links = await db_manager.db_find_and_expire_old_assigned_links(hours_threshold=24)
        
        if not expired_links:
            logger.info("No expired links found to process.")
            return

        logger.warning(f"Found {len(expired_links)} links to mark as expired.")

        # Уведомляем каждого пользователя, чье задание было отменено
        for link in expired_links:
            user_id = link.assigned_to_user_id
            if not user_id:
                continue

            # Сбрасываем состояние пользователя (FSM)
            state = FSMContext(storage=storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
            await state.clear()

            # Отправляем уведомление
            try:
                await bot.send_message(
                    user_id,
                    "❗️ Ваше текущее задание было отменено из-за длительной неактивности. Ссылка возвращена в пул.",
                    reply_markup=reply.get_main_menu_keyboard()
                )
                logger.info(f"Notified user {user_id} about expired task for link {link.id}.")
            except TelegramBadRequest:
                logger.warning(f"Could not notify user {user_id} about expired task. Bot might be blocked.")
            except Exception as e:
                logger.error(f"Failed to process expired link notification for user {user_id}: {e}")

    except Exception as e:
        logger.exception("An error occurred during the check_and_expire_links job.")