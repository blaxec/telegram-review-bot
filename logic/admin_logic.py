# file: telegram-review-bot-main/logic/admin_logic.py

import logging
import datetime
import asyncio
from math import ceil

from aiogram.types import Message
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import db_manager
from states.user_states import UserState
from keyboards import inline, reply
from references import reference_manager
from logic.promo_logic import check_and_apply_promo_reward
from logic.user_notifications import send_confirmation_button, handle_task_timeout, send_cooldown_expired_notification
from config import Rewards, Durations, Limits, TESTER_IDS

logger = logging.getLogger(__name__)


# --- ЛОГИКА: Добавление ссылок ---
async def process_add_links_logic(links_text: str, platform: str, is_fast_track: bool = False, requires_photo: bool = False) -> str:
    """
    Обрабатывает текст со ссылками, добавляет их в базу данных
    и возвращает отформатированную строку с результатом.
    """
    if not links_text:
        return "Текст со ссылками не может быть пустым."

    links = links_text.strip().split('\n')
    added_count, skipped_count = 0, 0

    for link in links:
        stripped_link = link.strip()
        if stripped_link and (stripped_link.startswith("http://") or stripped_link.startswith("https://")):
            try:
                if await db_manager.db_add_reference(stripped_link, platform, is_fast_track=is_fast_track, requires_photo=requires_photo):
                    added_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                logger.error(f"!!! ОШИБКА ДОБАВЛЕНИЯ В БД: Не удалось добавить ссылку '{stripped_link}': {e}")
                skipped_count += 1
        elif stripped_link:
            logger.warning(f"Skipping invalid link format: {stripped_link}")
            skipped_count += 1

    return f"Готово!\n✅ Добавлено: {added_count}\n⏭️ Пропущено (дубликаты или неверный формат): {skipped_count}"


# --- ЛОГИКА ДЛЯ ПРЕДУПРЕЖДЕНИЙ И ОТКЛОНЕНИЙ ---

async def process_rejection_reason_logic(bot: Bot, user_id: int, reason: str, context: str, user_state: FSMContext):
    """Логика обработки причины отклонения и уведомления пользователя."""
    if context == "gmail_data_request" or context == "gmail_device_model":
        user_message_text = f"❌ Ваш запрос на создание аккаунта был отклонен.\n\n<b>Причина:</b> {reason}"
        await user_state.set_state(UserState.MAIN_MENU)
    elif context == "gmail_account":
        user_message_text = f"❌ Ваш созданный аккаунт Gmail был отклонен администратором.\n\n<b>Причина:</b> {reason}"
        await user_state.set_state(UserState.MAIN_MENU)
    else:
        user_message_text = f"❌ Ваша проверка была отклонена администратором.\n\n<b>Причина:</b> {reason}"
        await user_state.set_state(UserState.MAIN_MENU)
        
    try:
        await bot.send_message(user_id, user_message_text, reply_markup=inline.get_back_to_main_menu_keyboard())
        return f"Сообщение об отклонении отправлено пользователю {user_id}."
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об отклонении пользователю {user_id}. Ошибка: {e}")
        return f"Не удалось отправить сообщение пользователю {user_id}. Ошибка: {e}"


async def process_warning_reason_logic(bot: Bot, user_id: int, platform: str, reason: str, user_state: FSMContext, context: str):
    """Логика обработки причины предупреждения и уведомления пользователя."""
    warnings_count = await db_manager.add_user_warning(user_id, platform=platform)
    user_message_text = f"⚠️ <b>Администратор выдал вам предупреждение.</b>\n\n<b>Причина:</b> {reason}\n"

    if warnings_count >= Limits.WARNINGS_THRESHOLD_FOR_BAN:
        user_message_text += f"\n❗️ <b>Это ваше {Limits.WARNINGS_THRESHOLD_FOR_BAN}-е предупреждение. Возможность выполнять задания для платформы {platform.capitalize()} заблокирована на {Durations.COOLDOWN_WARNING_BLOCK_HOURS} часа.</b>"
        await user_state.clear()
        await user_state.set_state(UserState.MAIN_MENU)
    else:
        state_to_return_map = {
            "google_profile": UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT,
            "google_last_reviews": UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK,
            "yandex_profile": UserState.YANDEX_REVIEW_INIT,
            "yandex_profile_screenshot": UserState.YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT,
            "gmail_device_model": UserState.MAIN_MENU,
            "gmail_data_request": UserState.MAIN_MENU,
        }
        state_to_return = state_to_return_map.get(context)
        if state_to_return:
             await user_state.set_state(state_to_return)
        else: # На случай если контекст не найден
             await user_state.set_state(UserState.MAIN_MENU)
        user_message_text += "\nПожалуйста, исправьте ошибку и повторите попытку или вернитесь в главное меню."

    try:
        await bot.send_message(user_id, user_message_text, reply_markup=inline.get_back_to_main_menu_keyboard())
        return f"Предупреждение с причиной успешно отправлено пользователю {user_id}."
    except Exception as e:
        logger.error(f"Не удалось отправить предупреждение пользователю {user_id}. Ошибка: {e}")
        return f"Не удалось отправить предупреждение пользователю {user_id}. Ошибка: {e}"


# --- ЛОГИКА ДЛЯ ОТПРАВКИ ТЕКСТА ОТЗЫВА ---

async def send_review_text_to_user_logic(bot: Bot, dp: Dispatcher, scheduler: AsyncIOScheduler, user_id: int, link_id: int, platform: str, review_text: str):
    """Логика отправки текста отзыва пользователю и планирования задач."""
    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
            
    user_info = await bot.get_chat(user_id)
    link = await db_manager.db_get_link_by_id(link_id)

    if not link:
        await bot.send_message(user_id, "Произошла ошибка, ваша ссылка для задания не найдена. Начните заново.")
        await user_state.clear()
        return False, f"Не удалось найти ссылку с ID {link_id} для пользователя."

    task_state, task_message, run_date_confirm, run_date_timeout = None, None, None, None

    photo_instruction = "\n3. <b>Прикрепите к отзыву фотографию</b> (любую подходящую, например, из интерьера или связанную с тематикой места)." if link.requires_photo else ""

    base_task_text = (
        "📝 <b>ВАШЕ ЗАДАНИЕ ГОТОВО!</b>\n\n"
        "1. Внимательно перепишите текст ниже. Ваш отзыв должен быть <b>абсолютно идентичен</b> предоставленному тексту.\n"
        "2. Перейдите по ссылке и оставьте отзыв на <b>5 звезд</b>, точно следуя тексту."
        f"{photo_instruction}\n\n"
        "❗❗❗ <b>ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ:</b> Не изменяйте текст, не добавляйте и не убирайте символы, эмодзи или знаки препинания. Отзыв должен быть копией. <b>КОПИРОВАНИЕ И ВСТАВКА ТЕКСТА КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО</b>, пишите вручную.\n\n"
        "<b>Текст для отзыва:</b>\n"
        f"<i>{review_text}</i>\n\n"
        f"🔗 <b><a href='{link.url}'>ПЕРЕЙТИ К ЗАДАНИЮ</a></b> \n\n"
    )

    if platform == "google":
        task_state = UserState.GOOGLE_REVIEW_TASK_ACTIVE
        task_message = base_task_text + (
            f"⏳ На выполнение этого задания у вас есть <b>{Durations.TASK_GOOGLE_REVIEW_TIMEOUT} минут</b>. "
            f"Кнопка для подтверждения появится через <b>{Durations.TASK_GOOGLE_REVIEW_CONFIRM_APPEARS} минут</b>."
        )
        run_date_confirm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=Durations.TASK_GOOGLE_REVIEW_CONFIRM_APPEARS)
        run_date_timeout = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=Durations.TASK_GOOGLE_REVIEW_TIMEOUT)

    elif platform == "yandex_with_text":
        task_state = UserState.YANDEX_REVIEW_TASK_ACTIVE
        task_message = base_task_text + (
            f"⏳ На выполнение этого задания у вас есть <b>{Durations.TASK_YANDEX_REVIEW_TIMEOUT} минут</b>. "
            f"Кнопка для подтверждения появится через <b>{Durations.TASK_YANDEX_REVIEW_CONFIRM_APPEARS} минут</b>."
        )
        run_date_confirm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=Durations.TASK_YANDEX_REVIEW_CONFIRM_APPEARS)
        run_date_timeout = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=Durations.TASK_YANDEX_REVIEW_TIMEOUT)
    
    if not task_state:
        return False, f"Неизвестная платформа: {platform}"

    try:
        sent_message = await bot.send_message(user_id, task_message, parse_mode='HTML', disable_web_page_preview=True)
        user_data_prev = await user_state.get_data()
        prev_confirm_job_id = user_data_prev.get('confirm_job_id')
        prev_timeout_job_id = user_data_prev.get('timeout_job_id')
        
        if prev_confirm_job_id:
            try: scheduler.remove_job(prev_confirm_job_id)
            except Exception: pass
        if prev_timeout_job_id:
            try: scheduler.remove_job(prev_timeout_job_id)
            except Exception: pass
        
    except Exception as e:
        await reference_manager.release_reference_from_user(user_id, 'available')
        await user_state.clear()
        return False, f"Не удалось отправить задание пользователю {user_id}. Ошибка: {e}"

    await user_state.set_state(task_state)
    await user_state.update_data(
        username=user_info.username, 
        review_text=review_text, 
        platform_for_task=platform,
        current_task_message_id=sent_message.message_id
    )

    confirm_job = scheduler.add_job(send_confirmation_button, 'date', run_date=run_date_confirm, args=[bot, user_id, platform])
    timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=run_date_timeout, args=[bot, dp.storage, user_id, platform, 'основное задание', scheduler])
    await user_state.update_data(confirm_job_id=confirm_job.id, timeout_job_id=timeout_job.id)
    
    return True, f"Текст успешно отправлен пользователю @{user_info.username} (ID: {user_id})."


# --- ЛОГИКА ДЛЯ ШТРАФОВ ---

async def apply_fine_to_user(user_id: int, admin_id: int, amount: float, reason: str, bot: Bot) -> str:
    """Применяет штраф к пользователю, обновляет его баланс и уведомляет его."""
    user = await db_manager.get_user(user_id)
    if not user:
        return f"❌ Пользователь с ID <code>{user_id}</code> не найден."

    await db_manager.update_balance(user_id, -amount, op_type="FINE", description=f"Админ {admin_id}: {reason}")
    
    user_notification_text = (
        f"❗️ <b>Вам был выдан штраф администратором.</b>\n\n"
        f"<b>Причина:</b> {reason}\n"
        f"<b>Списано:</b> {amount:.2f} ⭐"
    )

    try:
        await bot.send_message(user_id, user_notification_text, reply_markup=inline.get_back_to_main_menu_keyboard())
        logger.info(f"Admin {admin_id} fined user {user_id} for {amount} stars. Reason: {reason}")
        username = f"@{user.username}" if user.username else f"ID {user_id}"
        return f"✅ Штраф успешно применен к пользователю <b>{username}</b>."
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about the fine: {e}")
        await db_manager.update_balance(user_id, amount) # Возвращаем деньги, если не удалось уведомить
        return f"❌ Не удалось уведомить пользователя {user_id} о штрафе. Штраф был отменен. Ошибка: {e}"


# --- ЛОГИКА ДЛЯ МОДЕРАЦИИ ОТЗЫВОВ ---

async def approve_review_to_hold_logic(review_id: int, bot: Bot, scheduler: AsyncIOScheduler) -> tuple[bool, str]:
    """Логика для одобрения начального отзыва и перевода его в холд."""
    review = await db_manager.get_review_by_id(review_id)
    if not review or review.status != 'pending':
        logger.error(f"Attempted to approve review {review_id}, but it was not found or status was not 'pending'.")
        return False, "Ошибка: отзыв не найден или уже обработан."

    user = await db_manager.get_user(review.user_id)
    is_tester = user and user.id in TESTER_IDS

    amount_map = {
        'google': Rewards.GOOGLE_REVIEW,
        'yandex_with_text': Rewards.YANDEX_WITH_TEXT,
        'yandex_without_text': Rewards.YANDEX_WITHOUT_TEXT
    }
    hold_minutes_map = {
        'google': Durations.HOLD_GOOGLE_MINUTES,
        'yandex_with_text': Durations.HOLD_YANDEX_WITH_TEXT_MINUTES,
        'yandex_without_text': Durations.HOLD_YANDEX_WITHOUT_TEXT_MINUTES
    }
    
    amount = amount_map.get(review.platform, 0.0)
    
    if is_tester:
        hold_duration_minutes = Durations.HOLD_TESTER_MINUTES
        logger.info(f"User {user.id} is a tester. Setting hold duration to {hold_duration_minutes} minutes for review {review_id}.")
    else:
        hold_duration_minutes = hold_minutes_map.get(review.platform, 24 * 60)
    
    success = await db_manager.move_review_to_hold(review_id, amount, hold_minutes=hold_duration_minutes)
    if not success:
        return False, "Не удалось одобрить отзыв (ошибка БД)."

    cooldown_hours_map = {
        'google': Durations.COOLDOWN_GOOGLE_REVIEW_HOURS,
        'yandex_with_text': Durations.COOLDOWN_YANDEX_WITH_TEXT_HOURS,
        'yandex_without_text': Durations.COOLDOWN_YANDEX_WITHOUT_TEXT_HOURS
    }
    cooldown_hours = cooldown_hours_map.get(review.platform)
    platform_for_cooldown = review.platform
    
    cooldown_end_time = await db_manager.set_platform_cooldown(review.user_id, platform_for_cooldown, cooldown_hours)
    if cooldown_end_time:
        scheduler.add_job(
            send_cooldown_expired_notification, 
            'date', 
            run_date=cooldown_end_time, 
            args=[bot, review.user_id, platform_for_cooldown]
        )
    
    await reference_manager.release_reference_from_user(review.user_id, 'used')
    
    try:
        msg = await bot.send_message(review.user_id, f"✅ Ваш отзыв ({review.platform}) прошел проверку и отправлен в холд. +{amount:.2f} ⭐ в холд.")
        await schedule_message_deletion(msg, Durations.DELETE_INFO_MESSAGE_DELAY)
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {review.user_id} об одобрении в холд: {e}")
    
    hold_hours = hold_duration_minutes / 60
    return True, f"Одобрено. Отзыв отправлен в холд на {hold_hours:.2f} ч."

async def reject_initial_review_logic(review_id: int, bot: Bot, scheduler: AsyncIOScheduler, reason: str = None) -> tuple[bool, str]:
    """Логика для отклонения начального отзыва."""
    review = await db_manager.get_review_by_id(review_id)
    if not review:
        return False, "Ошибка: отзыв не найден."

    rejected_review = await db_manager.admin_reject_review(review_id)
    if not rejected_review:
        return False, "Не удалось отклонить отзыв (возможно, уже обработан)."

    cooldown_hours_map = {
        'google': Durations.COOLDOWN_GOOGLE_REVIEW_HOURS,
        'yandex_with_text': Durations.COOLDOWN_YANDEX_WITH_TEXT_HOURS,
        'yandex_without_text': Durations.COOLDOWN_YANDEX_WITHOUT_TEXT_HOURS
    }
    cooldown_hours = cooldown_hours_map.get(rejected_review.platform, 24)
    platform_for_cooldown = rejected_review.platform

    cooldown_end_time = await db_manager.set_platform_cooldown(rejected_review.user_id, platform_for_cooldown, cooldown_hours)
    if cooldown_end_time:
        scheduler.add_job(
            send_cooldown_expired_notification, 
            'date', 
            run_date=cooldown_end_time, 
            args=[bot, rejected_review.user_id, platform_for_cooldown]
        )
    
    await reference_manager.release_reference_from_user(rejected_review.user_id, 'available')
    
    try:
        user_message = f"❌ Ваш отзыв ({rejected_review.platform}) был отклонен."
        if reason:
            user_message += f"\n\n<b>Причина:</b> {reason}"
        user_message += "\n\nВы сможете попробовать снова после окончания кулдауна."
        
        await bot.send_message(rejected_review.user_id, user_message, reply_markup=inline.get_back_to_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {rejected_review.user_id} об отклонении: {e}")
    
    return True, "Отзыв отклонен. Пользователю выдан кулдаун."


async def approve_final_review_logic(review_id: int, bot: Bot) -> tuple[bool, str]:
    """Логика для окончательного одобрения отзыва ПОСЛЕ ХОЛДА и начисления реферальных наград."""
    approved_review = await db_manager.admin_approve_review(review_id)
    if not approved_review:
        return False, "❌ Ошибка: отзыв не найден или уже обработан."
    
    user_id = approved_review.user_id
    user = await db_manager.get_user(user_id)
    
    if user and user.referrer_id:
        referrer = await db_manager.get_user(user.referrer_id)
        if referrer and referrer.referral_path:
            referral_reward = 0
            
            if referrer.referral_path == 'google' and approved_review.platform == 'google':
                referral_reward = Rewards.REFERRAL_GOOGLE_REVIEW
            
            elif referrer.referral_path == 'yandex':
                if referrer.referral_subpath == 'with_text' and approved_review.platform == 'yandex_with_text':
                    referral_reward = Rewards.REFERRAL_YANDEX_WITH_TEXT
                elif referrer.referral_subpath == 'without_text' and approved_review.platform == 'yandex_without_text':
                    referral_reward = Rewards.REFERRAL_YANDEX_WITHOUT_TEXT
            
            if referral_reward > 0:
                await db_manager.add_referral_earning(user_id, referral_reward)
                try:
                    await bot.send_message(
                        referrer.id,
                        f"🎉 Ваш реферал @{user.username} успешно завершил отзыв! "
                        f"Вам начислено {referral_reward:.2f} ⭐ в копилку."
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить реферера {referrer.id}: {e}")

    if approved_review.platform == 'google':
        await check_and_apply_promo_reward(user_id, "google_review", bot)
    elif 'yandex' in approved_review.platform:
        await check_and_apply_promo_reward(user_id, "yandex_review", bot)
    
    try:
        await bot.send_message(user_id, f"✅ Ваш подтверждающий скриншот одобрен! Награда за отзыв #{review_id} ({approved_review.amount:.2f} ⭐) зачислена на основной баланс.")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id} об окончательном одобрении: {e}")
        
    return True, "✅ Отзыв одобрен и выплачен!"

async def reject_final_review_logic(review_id: int, bot: Bot) -> tuple[bool, str]:
    """Логика для отклонения отзыва на финальном этапе проверки."""
    rejected_review = await db_manager.admin_reject_final_confirmation(review_id)
    if not rejected_review:
        return False, "❌ Ошибка: отзыв не найден или уже обработан."

    try:
        await bot.send_message(
            rejected_review.user_id,
            f"❌ Ваш подтверждающий скриншот для отзыва #{review_id} был отклонен. Награда списана из холда."
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {rejected_review.user_id} об отклонении на финальном этапе: {e}")

    return True, "❌ Отзыв отклонен, холд списан."


# --- ЛОГИКА ДЛЯ ВЫВОДА СРЕДСТВ ---

async def approve_withdrawal_logic(request_id: int, bot: Bot) -> tuple[bool, str, object]:
    """Логика одобрения вывода средств."""
    request = await db_manager.approve_withdrawal_request(request_id)
    if request is None:
        return False, "❌ Запрос уже обработан или не найден.", None
    
    try:
        await bot.send_message(request.user_id, f"✅ Ваш запрос на вывод {request.amount:.2f} ⭐ <b>подтвержден</b>.")
    except Exception as e:
        logger.error(f"Failed to notify user {request.user_id} about withdrawal approval: {e}")

    return True, "✅ Вывод подтвержден.", request


async def reject_withdrawal_logic(request_id: int, bot: Bot) -> tuple[bool, str, object]:
    """Логика отклонения вывода средств."""
    request = await db_manager.reject_withdrawal_request(request_id)
    if request is None:
        return False, "❌ Запрос уже обработан или не найден.", None

    try:
        await bot.send_message(request.user_id, f"❌ Ваш запрос на вывод {request.amount:.2f} ⭐ <b>отклонен</b>. Средства возвращены на баланс.")
    except Exception as e:
        logger.error(f"Failed to notify user {request.user_id} about withdrawal rejection: {e}")

    return True, "❌ Вывод отклонен. Средства возвращены.", request


# --- ЛОГИКА ДЛЯ ПРОСМОТРА ХОЛДА ПОЛЬЗОВАТЕЛЯ ---

async def get_user_hold_info_logic(identifier: str) -> str:
    """Возвращает отформатированную строку с информацией о холде пользователя."""
    user_id = await db_manager.find_user_by_identifier(identifier)
    if not user_id:
        return f"Пользователь <code>{identifier}</code> не найден в базе данных."

    user = await db_manager.get_user(user_id)
    reviews_in_hold = await db_manager.get_user_hold_reviews(user_id)

    if not reviews_in_hold:
        return f"У пользователя @{user.username} (ID: <code>{user_id}</code>) нет отзывов в холде."

    total_hold_amount = sum(review.amount for review in reviews_in_hold)

    response_text = f"⏳ Отзывы в холде для @{user.username} (ID: <code>{user_id}</code>)\n"
    response_text += f"Общая сумма в холде: <b>{total_hold_amount:.2f}</b> ⭐\n\n"

    for review in reviews_in_hold:
        hold_until_str = review.hold_until.strftime('%d.%m.%Y %H:%M') if review.hold_until else 'N/A'
        response_text += (
            f"🔹 <b>{review.amount:.2f} ⭐</b> ({review.platform})\n"
            f"   - До: {hold_until_str} UTC\n"
            f"   - ID отзыва: <code>{review.id}</code>\n\n"
        )
    return response_text

async def schedule_message_deletion(message: Message, delay: int):
    """Вспомогательная функция для планирования удаления сообщения."""
    async def delete_after_delay():
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    asyncio.create_task(delete_after_delay())

# --- НОВАЯ ЛОГИКА ДЛЯ СПИСКА ЗАБАНЕННЫХ ---
async def format_banned_user_page(users: list, current_page: int, total_pages: int) -> str:
    if not users:
        return "📜 <b>Список забаненных пользователей:</b>\n\nПока никого нет в бане.\n\n" \
               f"Страница {current_page}/{total_pages}"
    
    text = "📜 <b>Список забаненных пользователей:</b>\n\n"
    for user in users:
        username = f"@{user.username}" if user.username else f"ID: {user.id}"
        ban_date = user.banned_at.strftime('%d.%m.%Y %H:%M') if user.banned_at else 'N/A'
        text += (
            f"🚫 {username} (ID: <code>{user.id}</code>)\n"
            f"   - <b>Причина:</b> {user.ban_reason or 'Не указана'}\n"
            f"   - <b>Дата бана:</b> {ban_date} UTC\n\n"
        )
    text += f"Страница {current_page}/{total_pages}"
    return text

# --- НОВАЯ ЛОГИКА ДЛЯ СПИСКА ПРОМОКОДОВ ---
async def format_promo_code_page(promos: list, current_page: int, total_pages: int) -> str:
    if not promos:
        return "📝 <b>Список промокодов:</b>\n\nПромокодов не найдено.\n\n" \
               f"Страница {current_page}/{total_pages}"
    
    text = "📝 <b>Список промокодов:</b>\n\n"
    for promo in promos:
        condition_map = {
            'no_condition': 'Без условия',
            'google_review': 'Отзыв Google',
            'yandex_review': 'Отзыв Yandex',
            'gmail_account': 'Создание Gmail'
        }
        condition_text = condition_map.get(promo.condition, 'Неизвестно')
        created_at = promo.created_at.strftime('%d.%m.%Y %H:%M') if promo.created_at else 'N/A'
        
        text += (
            f"🎁 <b>Код:</b> <code>{promo.code}</code>\n"
            f"   - <b>Награда:</b> {promo.reward:.2f} ⭐\n"
            f"   - <b>Использований:</b> {promo.current_uses}/{promo.total_uses}\n"
            f"   - <b>Условие:</b> {condition_text}\n"
            f"   - <b>Создан:</b> {created_at} UTC\n\n"
        )
    text += f"Страница {current_page}/{total_pages}"
    return text