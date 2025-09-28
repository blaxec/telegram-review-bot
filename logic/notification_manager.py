# file: logic/notification_manager.py

import logging
import re
from typing import List, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler


from database import db_manager
from logic import admin_roles 
from keyboards import inline 
from config import Durations, SUPER_ADMIN_ID

logger = logging.getLogger(__name__)

async def send_notification_to_admins(
    bot: Bot,
    text: str,
    task_type: str,
    scheduler: AsyncIOScheduler,
    photo_id: Optional[str] = None,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    return_sent_messages: bool = False,
    original_user_id: Optional[int] = None # ID пользователя, который отправил задачу
) -> Optional[List[Message]]:
    """
    Отправляет уведомление ответственным администраторам или свободному стажеру, учитывая DND режим.
    """
    
    # 1. Попытка найти свободного стажера для подходящих задач
    intern_routable_tasks = [
        "yandex_with_text_profile_screenshot", "yandex_without_text_profile_screenshot",
        "google_profile", "google_last_reviews", "gmail_device_model"
    ]
    
    if task_type in intern_routable_tasks:
        platform_map = {
            "google": "google",
            "yandex": "yandex",
            "gmail": "gmail"
        }
        task_platform_family = next((v for k, v in platform_map.items() if k in task_type), None)

        if task_platform_family:
            intern = await db_manager.find_available_intern(task_platform_family)
            if intern and original_user_id:
                logger.info(f"Task '{task_type}' is being routed to available intern ID: {intern.id}")
                
                await db_manager.set_intern_busy_status(intern.id, is_busy=True)
                
                context_map = {
                    "yandex_with_text_profile_screenshot": "yandex_profile_check",
                    "yandex_without_text_profile_screenshot": "yandex_profile_check",
                    "google_profile": "google_profile_check",
                    "google_last_reviews": "google_reviews_check",
                    "gmail_device_model": "gmail_registration"
                }
                intern_task_context = context_map.get(task_type, "unknown")

                # Создаем клавиатуру для стажера (без AI кнопок)
                intern_keyboard = inline.get_intern_verification_keyboard(original_user_id, intern_task_context)
                
                try:
                    if photo_id:
                        sent_msg = await bot.send_photo(chat_id=intern.id, photo=photo_id, caption=text, reply_markup=intern_keyboard)
                    else:
                        sent_msg = await bot.send_message(chat_id=intern.id, text=text, reply_markup=intern_keyboard)

                    return [sent_msg] if return_sent_messages else None
                except Exception as e:
                    logger.error(f"Failed to send task to intern {intern.id}, rerouting to admins. Error: {e}")
                    await db_manager.set_intern_busy_status(intern.id, is_busy=False)

    # 2. Если стажер не найден или задача не для него, отправляем админам
    admin_ids = await admin_roles.get_admins_for_task(task_type)
    active_admins = await db_manager.get_active_admins(admin_ids)
    
    sent_messages = []

    if not active_admins:
        logger.warning(f"No active admins found for task type '{task_type}'. Notification not sent.")
        try:
            await bot.send_message(SUPER_ADMIN_ID, f"⚠️ Внимание! Не найдено активных администраторов для задачи типа '{task_type}'. Задача не была доставлена.")
        except: pass
        return None

    for admin_id in active_admins:
        try:
            if photo_id:
                sent_msg = await bot.send_photo(chat_id=admin_id, photo=photo_id, caption=text, reply_markup=keyboard)
            else:
                sent_msg = await bot.send_message(chat_id=admin_id, text=text, reply_markup=keyboard, disable_web_page_preview=True)
            if return_sent_messages:
                sent_messages.append(sent_msg)
        except TelegramBadRequest as e:
            logger.error(f"TelegramBadRequest when sending notification to admin {admin_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to send notification to admin {admin_id}: {e}")

    return sent_messages if return_sent_messages else None