
# file: logic/notification_logic.py

import logging
from aiogram import Bot
from database import db_manager

logger = logging.getLogger(__name__)

async def notify_subscribers(platform: str, gender: str, bot: Bot):
    """
    Находит подписчиков на определенный тип заданий и уведомляет их.
    """
    try:
        subscribers = await db_manager.find_subscribers(platform, gender)
        if not subscribers:
            return

        gender_map = {'male': 'мужских', 'female': 'женских', 'any': 'любых'}
        platform_map = {'google_maps': 'Google', 'yandex_with_text': 'Yandex (с текстом)', 'yandex_without_text': 'Yandex (без текста)'}
        
        gender_text = gender_map.get(gender, 'неопределенных')
        platform_text = platform_map.get(platform, platform)

        message_text = (
            f"🎉 Появились новые задания для **{gender_text}** аккаунтов на платформе **{platform_text}**, на которые вы подписывались! "
            "Заходите в раздел 'Заработок', чтобы взять задание."
        )

        user_ids_to_notify = [sub.user_id for sub in subscribers]

        for user_id in user_ids_to_notify:
            try:
                await bot.send_message(user_id, message_text)
            except Exception as e:
                logger.warning(f"Failed to send task notification to subscriber {user_id}: {e}")
        
        # Удаляем подписки после уведомления
        await db_manager.delete_subscriptions(user_ids_to_notify, platform, gender)
        logger.info(f"Notified and unsubscribed {len(user_ids_to_notify)} users for {platform}/{gender} tasks.")

    except Exception as e:
        logger.exception(f"An error occurred in notify_subscribers for {platform}/{gender}: {e}")