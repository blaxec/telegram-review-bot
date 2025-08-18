# file: logic/admin_logic.py

import logging
import datetime
# ИСПРАВЛЕНИЕ: Добавлены недостающие импорты
import asyncio
from aiogram.types import Message
# -----------------------------------------
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
from logic.user_notifications import notify_cooldown_expired, send_confirmation_button, handle_task_timeout

logger = logging.getLogger(__name__)


# --- ЛОГИКА: Добавление ссылок ---
async def process_add_links_logic(links_text: str, platform: str) -> str:
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
                if await db_manager.db_add_reference(stripped_link, platform):
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
        user_message_text = f"❌ Ваш запрос на создание аккаунта был отклонен.\n\n**Причина:** {reason}"
        await user_state.set_state(UserState.MAIN_MENU)
    elif context == "gmail_account":
        user_message_text = f"❌ Ваш созданный аккаунт Gmail был отклонен администратором.\n\n**Причина:** {reason}"
        await user_state.set_state(UserState.MAIN_MENU)
    else:
        user_message_text = f"❌ Ваша проверка была отклонена администратором.\n\n**Причина:** {reason}"
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
    user_message_text = f"⚠️ **Администратор выдал вам предупреждение.**\n\n**Причина:** {reason}\n"

    if warnings_count >= 3:
        user_message_text += f"\n❗️ **Это ваше 3-е предупреждение. Возможность выполнять задания для платформы {platform.capitalize()} заблокирована на 24 часа.**"
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

    if platform == "google":
        task_state = UserState.GOOGLE_REVIEW_TASK_ACTIVE
        task_message = (
            "<b>ВАШЕ ЗАДАНИЕ ГОТОВО!</b>\n\n"
            "1. Перепишите текст ниже. Вы должны опубликовать отзыв, который *В ТОЧНОСТИ* совпадает с этим текстом.\n"
            "2. Перейдите по ссылке и оставьте отзыв на 5 звезд, переписав текст.\n\n"
            "❗️❗️❗️ <b>ВНИМАНИЕ:</b> Не изменяйте текст, не добавляйте и не убирайте символы или эмодзи. Отзыв должен быть идентичным. КОПИРОВАТЬ И ВСТАВЛЯТЬ ТЕКСТ НЕЛЬЗЯ\n\n"
            "<b>Текст для отзыва:</b>\n"
            f"{review_text}\n\n"
            f"🔗 <b>[ПЕРЕЙТИ К ЗАДАНИЮ]({link.url})</b> \n\n"
            "⏳ На выполнение задания у вас есть <b>15 минут</b>. Кнопка для подтверждения появится через <b>7 минут</b>."
        )
        run_date_confirm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=7)
        run_date_timeout = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)

    elif platform == "yandex_with_text":
        task_state = UserState.YANDEX_REVIEW_TASK_ACTIVE
        task_message = (
            "<b>ВАШЕ ЗАДАНИЕ ГОТОВО!</b>\n\n"
            "1. Перепишите текст ниже. Вы должны опубликовать отзыв на <b>5 звезд</b>, который *В ТОЧНОСТИ* совпадает с этим текстом.\n\n"
            "❗️❗️❗️ <b>ВНИМАНИЕ:</b> Не изменяйте текст, не добавляйте и не убирайте символы или эмодзи. Отзыв должен быть идентичным. КОПИРОВАТЬ И ВСТАВЛЯТЬ ТЕКСТ НЕЛЬЗЯ\n\n"
            "<b>Текст для отзыва:</b>\n"
            f"{review_text}\n\n"
            f"🔗 <b>[ПЕРЕЙТИ К ЗАДАНИЮ]({link.url})</b> \n\n"
            "⏳ На выполнение задания у вас есть <b>25 минут</b>. Кнопка для подтверждения появится через <b>10 минут</b>."
        )
        run_date_confirm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
        run_date_timeout = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=25)
    
    if not task_state:
        return False, f"Неизвестная платформа: {platform}"

    try:
        # Редактируем последнее сообщение бота, чтобы не спамить
        last_message = (await user_state.get_data()).get('last_bot_message')
        if last_message:
            await bot.edit_message_text(task_message, user_id, last_message, parse_mode='HTML', disable_web_page_preview=True)
        else:
            sent_msg = await bot.send_message(user_id, task_message, parse_mode='HTML', disable_web_page_preview=True)
            await user_state.update_data(last_bot_message=sent_msg.message_id)
    except Exception as e:
        await reference_manager.release_reference_from_user(user_id, 'available')
        await user_state.clear()
        return False, f"Не удалось отправить задание пользователю {user_id}. Ошибка: {e}"

    await user_state.set_state(task_state)
    await user_state.update_data(username=user_info.username, review_text=review_text, platform_for_task=platform)

    scheduler.add_job(send_confirmation_button, 'date', run_date=run_date_confirm, args=[bot, user_id, platform])
    timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=run_date_timeout, args=[bot, dp.storage, user_id, platform, 'основное задание'])
    await user_state.update_data(timeout_job_id=timeout_job.id)
    
    return True, f"Текст успешно отправлен пользователю @{user_info.username} (ID: {user_id})."


# --- ЛОГИКА ДЛЯ ШТРАФОВ ---

async def apply_fine_to_user(user_id: int, admin_id: int, amount: float, reason: str, bot: Bot) -> str:
    """Применяет штраф к пользователю, обновляет его баланс и уведомляет его."""
    user = await db_manager.get_user(user_id)
    if not user:
        return f"❌ Пользователь с ID `{user_id}` не найден."

    await db_manager.update_balance(user_id, -amount)
    
    user_notification_text = (
        f"❗️ **Вам был выдан штраф администратором.**\n\n"
        f"**Причина:** {reason}\n"
        f"**Списано:** {amount} ⭐"
    )

    try:
        await bot.send_message(user_id, user_notification_text, reply_markup=inline.get_back_to_main_menu_keyboard())
        logger.info(f"Admin {admin_id} fined user {user_id} for {amount} stars. Reason: {reason}")
        username = f"@{user.username}" if user.username else f"ID {user_id}"
        return f"✅ Штраф успешно применен к пользователю **{username}**."
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about the fine: {e}")
        await db_manager.update_balance(user_id, amount)
        return f"❌ Не удалось уведомить пользователя {user_id} о штрафе. Штраф был отменен. Ошибка: {e}"


# --- ЛОГИКА ДЛЯ МОДЕРАЦИИ ОТЗЫВОВ ---

async def approve_review_to_hold_logic(review_id: int, bot: Bot, scheduler: AsyncIOScheduler) -> tuple[bool, str]:
    """Логика для одобрения начального отзыва и перевода его в холд."""
    review = await db_manager.get_review_by_id(review_id)
    if not review or review.status != 'pending':
        return False, "Ошибка: отзыв не найден или уже обработан."

    amount_map = {'google': 15.0, 'yandex_with_text': 50.0, 'yandex_without_text': 15.0}
    hold_minutes_map = {'google': 5, 'yandex_with_text': 24 * 60, 'yandex_without_text': 72 * 60}
    
    amount = amount_map.get(review.platform, 0.0)
    hold_duration_minutes = hold_minutes_map.get(review.platform, 24 * 60)
    
    success = await db_manager.move_review_to_hold(review_id, amount, hold_minutes=hold_duration_minutes)
    if not success:
        return False, "Не удалось одобрить отзыв (ошибка БД)."

    cooldown_hours = 72
    platform_for_cooldown = review.platform
    await db_manager.set_platform_cooldown(review.user_id, platform_for_cooldown, cooldown_hours)
    
    cooldown_end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=cooldown_hours)
    scheduler.add_job(notify_cooldown_expired, 'date', run_date=cooldown_end_time, args=[bot, review.user_id, platform_for_cooldown], id=f"cooldown_notify_{review.user_id}_{platform_for_cooldown}")
    
    await reference_manager.release_reference_from_user(review.user_id, 'used')
    
    try:
        msg = await bot.send_message(review.user_id, f"✅ Ваш отзыв ({review.platform}) прошел проверку и отправлен в холд. +{amount} ⭐ в холд.")
        asyncio.create_task(schedule_message_deletion(msg, 25))
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {review.user_id} об одобрении в холд: {e}")
    
    hold_hours = hold_duration_minutes / 60
    return True, f"Одобрено. Отзыв отправлен в холд на {hold_hours:.0f} ч."

async def reject_initial_review_logic(review_id: int, bot: Bot, scheduler: AsyncIOScheduler) -> tuple[bool, str]:
    """Логика для отклонения начального отзыва."""
    review = await db_manager.get_review_by_id(review_id)
    if not review:
        return False, "Ошибка: отзыв не найден."

    rejected_review = await db_manager.admin_reject_review(review_id)
    if not rejected_review:
        return False, "Не удалось отклонить отзыв (возможно, уже обработан)."

    cooldown_hours = 72
    platform_for_cooldown = rejected_review.platform
    await db_manager.set_platform_cooldown(rejected_review.user_id, platform_for_cooldown, cooldown_hours)
    cooldown_end_time = datetime.datetime.utcnow() + datetime.timedelta(hours=cooldown_hours)
    scheduler.add_job(notify_cooldown_expired, 'date', run_date=cooldown_end_time, args=[bot, rejected_review.user_id, platform_for_cooldown], id=f"cooldown_notify_{rejected_review.user_id}_{platform_for_cooldown}")
    await reference_manager.release_reference_from_user(rejected_review.user_id, 'available')
    
    try:
        user_message = f"❌ Ваш отзыв ({rejected_review.platform}) был отклонен. Кулдаун на 3 дня."
        await bot.send_message(rejected_review.user_id, user_message, reply_markup=inline.get_back_to_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {rejected_review.user_id} об отклонении: {e}")
    
    return True, "Отзыв отклонен. Пользователю выдан кулдаун."


async def approve_hold_review_logic(review_id: int, bot: Bot) -> tuple[bool, str]:
    """Логика для окончательного одобрения отзыва из холда."""
    approved_review = await db_manager.admin_approve_review(review_id)
    if not approved_review:
        return False, "❌ Ошибка: отзыв не найден или уже обработан."
    
    user_id = approved_review.user_id
    
    if approved_review.platform == 'google':
        user = await db_manager.get_user(user_id)
        if user and user.referrer_id:
            amount = 0.45
            await db_manager.add_referral_earning(user_id=user_id, amount=amount)
            try:
                await bot.send_message(user.referrer_id, f"🎉 Ваш реферал @{user.username} успешно написал отзыв! Вам начислено {amount} ⭐.")
            except Exception as e:
                logger.error(f"Не удалось уведомить реферера {user.referrer_id}: {e}")
    
    if approved_review.platform == 'google':
        await check_and_apply_promo_reward(user_id, "google_review", bot)
    elif 'yandex' in approved_review.platform:
        await check_and_apply_promo_reward(user_id, "yandex_review", bot)
    
    try:
        msg = await bot.send_message(user_id, f"✅ Ваш отзыв (ID: {review_id}) одобрен! +{approved_review.amount} ⭐ зачислены на баланс.")
        asyncio.create_task(schedule_message_deletion(msg, 25))
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id} об одобрении: {e}")
        
    return True, "✅ Отзыв одобрен!"


async def reject_hold_review_logic(review_id: int, bot: Bot) -> tuple[bool, str]:
    """Логика для отклонения отзыва из холда."""
    review_before = await db_manager.get_review_by_id(review_id)
    if not review_before or review_before.status != 'on_hold':
        return False, "❌ Ошибка: отзыв не найден или уже обработан."

    rejected_review = await db_manager.admin_reject_review(review_id)
    if not rejected_review:
        return False, "❌ Не удалось отклонить отзыв."
    
    try:
        user_message = f"❌ Ваш отзыв (ID: {review_id}) отклонен после проверки. Звезды списаны из холда."
        await bot.send_message(rejected_review.user_id, user_message, reply_markup=inline.get_back_to_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {rejected_review.user_id} об отклонении: {e}")

    return True, "❌ Отзыв отклонен!"


# --- ЛОГИКА ДЛЯ ВЫВОДА СРЕДСТВ ---

async def approve_withdrawal_logic(request_id: int, bot: Bot) -> tuple[bool, str, object]:
    """Логика одобрения вывода средств."""
    request = await db_manager.approve_withdrawal_request(request_id)
    if request is None:
        return False, "❌ Запрос уже обработан или не найден.", None
    
    try:
        await bot.send_message(request.user_id, f"✅ Ваш запрос на вывод {request.amount} ⭐ **подтвержден**.")
    except Exception as e:
        logger.error(f"Failed to notify user {request.user_id} about withdrawal approval: {e}")

    return True, "✅ Вывод подтвержден.", request


async def reject_withdrawal_logic(request_id: int, bot: Bot) -> tuple[bool, str, object]:
    """Логика отклонения вывода средств."""
    request = await db_manager.reject_withdrawal_request(request_id)
    if request is None:
        return False, "❌ Запрос уже обработан или не найден.", None

    try:
        await bot.send_message(request.user_id, f"❌ Ваш запрос на вывод {request.amount} ⭐ **отклонен**. Средства возвращены на баланс.")
    except Exception as e:
        logger.error(f"Failed to notify user {request.user_id} about withdrawal rejection: {e}")

    return True, "❌ Вывод отклонен. Средства возвращены.", request


# --- ЛОГИКА ДЛЯ ПРОСМОТРА ХОЛДА ПОЛЬЗОВАТЕЛЯ ---

async def get_user_hold_info_logic(identifier: str) -> str:
    """Возвращает отформатированную строку с информацией о холде пользователя."""
    user_id = await db_manager.find_user_by_identifier(identifier)
    if not user_id:
        return f"Пользователь `{identifier}` не найден в базе данных."

    user = await db_manager.get_user(user_id)
    reviews_in_hold = await db_manager.get_user_hold_reviews(user_id)

    if not reviews_in_hold:
        return f"У пользователя @{user.username} (ID: `{user_id}`) нет отзывов в холде."

    total_hold_amount = sum(review.amount for review in reviews_in_hold)

    response_text = f"⏳ Отзывы в холде для @{user.username} (ID: `{user_id}`)\n"
    response_text += f"Общая сумма в холде: **{total_hold_amount}** ⭐\n\n"

    for review in reviews_in_hold:
        hold_until_str = review.hold_until.strftime('%d.%m.%Y %H:%M') if review.hold_until else 'N/A'
        response_text += (
            f"🔹 **{review.amount} ⭐** ({review.platform})\n"
            f"   - До: {hold_until_str} UTC\n"
            f"   - ID отзыва: `{review.id}`\n\n"
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