# file: logic/cleanup_logic.py

import logging
import datetime
from aiogram import Bot
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler


from database import db_manager
from keyboards import reply, inline
from states.user_states import UserState
from config import Durations, FINAL_CHECK_ADMIN

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

# --- НОВАЯ ЛОГИКА ДЛЯ ВЕРИФИКАЦИИ ПОСЛЕ ХОЛДА ---

async def handle_confirmation_timeout(bot: Bot, user_id: int, review_id: int, state: FSMContext):
    """Срабатывает, если пользователь не прислал подтверждающий скриншот вовремя."""
    current_state = await state.get_state()
    if current_state != UserState.AWAITING_CONFIRMATION_SCREENSHOT:
        logger.info(f"Confirmation timeout for review {review_id} (user {user_id}) triggered, but user is in state {current_state}. Aborting.")
        return
        
    review = await db_manager.cancel_hold(review_id)
    await state.clear()
    await state.set_state(UserState.MAIN_MENU)
    
    if review:
        logger.warning(f"User {user_id} failed to confirm review {review_id} in time. Hold cancelled.")
        try:
            await bot.send_message(
                user_id,
                f"⏳ К сожалению, время на подтверждение отзыва истекло. Холд для отзыва #{review_id} был отменен."
            )
            await bot.send_message(
                FINAL_CHECK_ADMIN,
                f"⚠️ Пользователь @{review.user.username} (ID: `{user_id}`) не прислал подтверждающий скриншот для отзыва #{review_id} вовремя. Холд отменен автоматически."
            )
        except Exception as e:
            logger.error(f"Failed to notify about confirmation timeout for review {review_id}: {e}")

async def process_expired_holds(bot: Bot, storage: BaseStorage, scheduler: AsyncIOScheduler):
    """
    Основная функция, запускаемая по расписанию. Проверяет истекшие холды и запрашивает подтверждение.
    """
    logger.info("Scheduler: Running job 'process_expired_holds'.")
    reviews_to_process = await db_manager.get_reviews_past_hold()
    if not reviews_to_process:
        return
        
    logger.info(f"Scheduler: Found {len(reviews_to_process)} reviews past hold to process.")
    
    for review in reviews_to_process:
        user_id = review.user_id
        review_id = review.id
        
        await db_manager.update_review_status(review_id, 'awaiting_confirmation')
        
        user_state = FSMContext(storage=storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
        await user_state.set_state(UserState.AWAITING_CONFIRMATION_SCREENSHOT)
        await user_state.update_data(review_id_for_confirmation=review_id)
        
        run_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=Durations.CONFIRMATION_TIMEOUT_MINUTES)
        scheduler.add_job(handle_confirmation_timeout, 'date', run_date=run_date, args=[bot, user_id, review_id, user_state])
        
        try:
            await bot.send_message(
                user_id,
                f"🔔 Время холда для вашего отзыва #{review_id} истекло!\n\n"
                f"Для зачисления награды, пожалуйста, пришлите **новый скриншот**, подтверждающий, что ваш отзыв всё ещё опубликован.\n\n"
                f"⏳ У вас есть **{Durations.CONFIRMATION_TIMEOUT_MINUTES} минут** на отправку.",
                reply_markup=inline.get_cancel_inline_keyboard()
            )
            logger.info(f"Requested confirmation screenshot for review {review_id} from user {user_id}.")
        except Exception as e:
            logger.error(f"Failed to request confirmation from user {user_id} for review {review_id}: {e}")
            await db_manager.cancel_hold(review_id)
            await user_state.clear()