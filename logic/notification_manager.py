# file: logic/notification_manager.py

import logging
from typing import List, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from logic import admin_roles

logger = logging.getLogger(__name__)

async def send_notification_to_admins(
    bot: Bot,
    text: str,
    task_type: str,
    photo_id: Optional[str] = None,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    return_sent_messages: bool = False
) -> Optional[List[Message]]:
    """
    Отправляет уведомление ответственным администраторам, учитывая DND режим.
    """
    admin_ids = await admin_roles.get_admins_for_task(task_type)
    active_admins = await db_manager.get_active_admins(admin_ids)
    
    sent_messages = []

    if not active_admins:
        logger.warning(f"No active admins found for task type '{task_type}'. Notification not sent.")
        return None

    for admin_id in active_admins:
        try:
            if photo_id:
                sent_msg = await bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_id,
                    caption=text,
                    reply_markup=keyboard
                )
            else:
                sent_msg = await bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            if return_sent_messages:
                sent_messages.append(sent_msg)
        except TelegramBadRequest as e:
            logger.error(f"TelegramBadRequest when sending notification to admin {admin_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to send notification to admin {admin_id}: {e}")

    return sent_messages if return_sent_messages else None