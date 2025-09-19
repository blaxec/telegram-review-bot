# file: telegram-review-bot-main/handlers/earning.py

import datetime
import logging
import asyncio
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager
from references import reference_manager
from config import Durations, TESTER_IDS
from logic.user_notifications import (
    format_timedelta,
    send_liking_confirmation_button,
    send_yandex_liking_confirmation_button,
    handle_task_timeout,
    send_confirmation_button
)
from utils.tester_filter import IsTester
from logic import admin_roles

router = Router()
logger = logging.getLogger(__name__)


async def schedule_message_deletion(message: Message, delay: int):
    """Планирует удаление сообщения через заданную задержку."""
    async def delete_after_delay():
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    asyncio.create_task(delete_after_delay())

async def delete_user_and_prompt_messages(message: Message, state: FSMContext):
    """Удаляет сообщение пользователя и предыдущее сообщение-приглашение от бота."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_message_id)
        except TelegramBadRequest:
            pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


# --- Блок обработки /skip ---

SKIP_ALLOWED_STATES = {
    UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE,
    UserState.GOOGLE_REVIEW_TASK_ACTIVE,
    UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE,
    UserState.YANDEX_REVIEW_TASK_ACTIVE
}

@router.message(
    Command("skip"),
    IsTester(),
    F.state.in_(SKIP_ALLOWED_STATES)
)
async def skip_timer_command_successful(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    user_id = message.from_user.id
    current_state = await state.get_state()
    user_data = await state.get_data()
    
    confirm_job_id = user_data.get("confirm_job_id")
    timeout_job_id = user_data.get("timeout_job_id")
    if confirm_job_id:
        try: scheduler.remove_job(confirm_job_id)
        except Exception: pass
    if timeout_job_id:
        try: scheduler.remove_job(timeout_job_id)
        except Exception: pass

    response_msg = None
    if current_state == UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE:
        await send_liking_confirmation_button(bot, user_id)
        response_msg = await message.answer("✅ Таймер лайков пропущен.")
    elif current_state == UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE:
        await send_yandex_liking_confirmation_button(bot, user_id)
        response_msg = await message.answer("✅ Таймер прогрева пропущен.")
    elif current_state in [UserState.GOOGLE_REVIEW_TASK_ACTIVE, UserState.YANDEX_REVIEW_TASK_ACTIVE]:
        platform = user_data.get("platform_for_task")
        if platform:
            await send_confirmation_button(bot, user_id, platform)
            response_msg = await message.answer(f"✅ Таймер написания отзыва для {platform} пропущен.")
    
    asyncio.create_task(schedule_message_deletion(message, 5))
    if response_msg:
        asyncio.create_task(schedule_message_deletion(response_msg, 5))
    
    logger.info(f"Tester {user_id} successfully skipped timer for state {current_state}.")

@router.message(
    Command("skip"),
    IsTester()
)
async def skip_timer_command_failed(message: Message):
    logger.warning(f"Tester {message.from_user.id} tried to use /skip in a wrong state.")
    
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
        
    response_msg = await message.answer(
        "❌ Команда <code>/skip</code> работает только на этапах с активным таймером."
    )
    asyncio.create_task(schedule_message_deletion(response_msg, 5))

# --- Основное меню Заработка ---

@router.message(F.text == '💰 Заработок', UserState.MAIN_MENU)
async def earning_handler_message(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer("💰 Способы заработка:", reply_markup=inline.get_earning_keyboard())

async def earning_menu_logic(callback: CallbackQuery):
    if callback.message:
        try:
            await callback.message.edit_text("💰 Способы заработка:", reply_markup=inline.get_earning_keyboard())
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Error editing earning menu message: {e}")
            await callback.answer()

@router.callback_query(F.data == 'earning_menu')
async def earning_handler_callback(callback: CallbackQuery, state: FSMContext):
    await earning_menu_logic(callback)


@router.callback_query(F.data == 'earning_write_review')
async def initiate_write_review(callback: CallbackQuery, state: FSMContext):
    if callback.message:
        await callback.message.edit_text(
            "✍️ Выберите платформу для написания отзыва:",
            reply_markup=inline.get_write_review_platform_keyboard()
        )
    
@router.callback_query(F.data == 'earning_menu_back')
async def earning_menu_back(callback: CallbackQuery, state: FSMContext):
    await earning_menu_logic(callback)

# --- Логика для Google Карт ---

@router.callback_query(F.data == 'review_google_maps')
async def initiate_google_review(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cooldown = await db_manager.check_platform_cooldown(user_id, "google")
    if cooldown:
        await callback.answer(f"Вы сможете написать отзыв в Google через {format_timedelta(cooldown)}.", show_alert=True)
        return

    if not await reference_manager.has_available_references('google_maps'):
        await callback.answer("К сожалению, в данный момент задания для Google Карт закончились. Попробуйте позже.", show_alert=True)
        return
        
    await state.set_state(UserState.GOOGLE_REVIEW_INIT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "⭐ За отзыв в Google.Картах начисляется 15 звезд.\n\n"
            "💡 Для повышения проходимости вашего отзыва, пожалуйста, временно отключите "
            "<i>«Определение местоположения»</i> в настройках приложения на вашем телефоне.",
            reply_markup=inline.get_google_init_keyboard()
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.callback_query(F.data == 'google_review_done', UserState.GOOGLE_REVIEW_INIT)
async def process_google_review_done(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Отлично! Теперь, чтобы мы могли проверить, готовы ли вы писать отзыв, пожалуйста, "
            "пришлите <i>скриншот вашего профиля</i> в Google.Картах. "
            "Отзывы на новых аккаунтах не будут проходить проверку.\n\n"
            "Отправьте фото следующим сообщением.",
            reply_markup=inline.get_google_ask_profile_screenshot_keyboard()
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data == 'google_get_profile_screenshot', UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
async def show_google_profile_screenshot_instructions(callback: CallbackQuery):
    if callback.message:
        try:
            await callback.message.edit_text(
                "🤔 <b>Как сделать скриншот вашего профиля Google.Карты:</b>\n\n"
                "1. Перейдите по ссылке: <a href='https://www.google.com/maps/contrib/'>Профиль Google Maps</a>\n"
                "2. Вас переведет на профиль Google Карты.\n"
                "3. Сделайте скриншот вашего профиля (без замазывания и обрезания).",
                reply_markup=inline.get_google_back_from_instructions_keyboard(),
                disable_web_page_preview=True
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Error editing instructions message: {e}")
    await callback.answer()

@router.callback_query(F.data == 'google_back_to_profile_screenshot', UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
async def back_to_profile_screenshot(callback: CallbackQuery, state: FSMContext):
    if callback.message:
        await callback.message.edit_text(
            "Отлично! Теперь, чтобы мы могли проверить, готовы ли вы писать отзыв, пожалуйста, "
            "пришлите <i>скриншот вашего профиля</i> в Google.Картах. "
            "Отзывы на новых аккаунтах не будут проходить проверку.\n\n"
            "Отправьте фото следующим сообщением.",
            reply_markup=inline.get_google_ask_profile_screenshot_keyboard()
        )
    await callback.answer()


@router.message(F.photo, UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
async def process_google_profile_screenshot(message: Message, state: FSMContext, bot: Bot):
    await delete_user_and_prompt_messages(message, state)
    if not message.photo: return
    
    photo_file_id = message.photo[-1].file_id
    await state.update_data(profile_screenshot_id=photo_file_id)
    
    await message.answer("Ваш скриншот отправлен на проверку. Ожидайте...")
    await state.set_state(UserState.GOOGLE_REVIEW_PROFILE_CHECK_PENDING)
    
    user_info_text = f"Пользователь: @{message.from_user.username} (ID: <code>{message.from_user.id}</code>)"
    caption = f"Проверьте имя и фамилию в профиле пользователя.\n{user_info_text}"
    
    try:
        admin_id = await admin_roles.get_google_profile_admin()
        await bot.send_photo(
            chat_id=admin_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_verification_keyboard(message.from_user.id, "google_profile")
        )
    except Exception as e:
        logger.error(f"Ошибка отправки фото профиля админу: {e}")
        await message.answer("Не удалось отправить фото на проверку. Попробуйте позже.")
        await state.clear()

@router.callback_query(F.data == 'google_last_reviews_where', UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
async def show_google_last_reviews_instructions(callback: CallbackQuery):
    if callback.message:
        try:
            await callback.message.edit_text(
                "🤔 <b>Как найти последние отзывы:</b>\n\n"
                "1. Откройте ваш профиль в Google Картах.\n"
                "2. Перейдите во вкладку 'Отзывы'.\n"
                "3. Сделайте скриншот, на котором видны даты ваших последних отзывов.",
                reply_markup=inline.get_google_back_from_last_reviews_keyboard()
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Error editing last reviews instructions: {e}")
    await callback.answer()

@router.callback_query(F.data == 'google_back_to_last_reviews', UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
async def back_to_last_reviews_check(callback: CallbackQuery, state: FSMContext):
    if callback.message:
        await callback.message.edit_text(
            "Профиль прошел проверку. Пришлите скриншот последних отзывов.",
            reply_markup=inline.get_google_last_reviews_check_keyboard()
        )
    await callback.answer()


@router.message(F.photo, UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
async def process_google_last_reviews_screenshot(message: Message, state: FSMContext, bot: Bot):
    await delete_user_and_prompt_messages(message, state)
    if not message.photo: return

    photo_file_id = message.photo[-1].file_id
    
    await message.answer("Ваши последние отзывы отправлены на проверку. Ожидайте...")
    await state.set_state(UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK_PENDING)
    
    user_info_text = f"Пользователь: @{message.from_user.username} (ID: <code>{message.from_user.id}</code>)"
    caption = f"Проверьте последние отзывы пользователя. Интервал - 3 дня.\n{user_info_text}"

    try:
        admin_id = await admin_roles.get_google_reviews_admin()
        await bot.send_photo(
            chat_id=admin_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_verification_keyboard(
                user_id=message.from_user.id, 
                context="google_last_reviews"
            )
        )
    except Exception as e:
        logger.error(f"Ошибка отправки фото последних отзывов админу: {e}")
        await message.answer("Не удалось отправить фото на проверку. Попробуйте позже.")
        await state.clear()

async def start_google_liking_or_main_task(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, link):
    """Общая логика для начала этапа лайков или сразу основного задания (для быстрых ссылок)."""
    user_id = callback.from_user.id
    
    if link.is_fast_track:
        logger.info(f"Link {link.id} is a fast-track. Skipping liking step for user {user_id}.")
        await process_liking_completion(callback, state, bot, scheduler)
    else:
        task_text = (
            "<b>Отлично! Следующий шаг:</b>\n\n"
            f"🔗 <a href='{link.url}'>Перейти по ссылке</a>\n"
            "👀 Просмотрите страницу и поставьте лайки на положительные отзывы.\n\n"
            f"⏳ Для выполнения этого задания у вас есть <i>{Durations.TASK_GOOGLE_LIKING_TIMEOUT} минут</i>. Кнопка для подтверждения появится через {Durations.TASK_GOOGLE_LIKING_CONFIRM_APPEARS} минут."
        )
        if callback.message:
            await callback.message.edit_text(task_text, disable_web_page_preview=True)
        await state.set_state(UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE)
        await state.update_data(username=callback.from_user.username, active_link_id=link.id)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        confirm_job = scheduler.add_job(send_liking_confirmation_button, 'date', run_date=now + datetime.timedelta(minutes=Durations.TASK_GOOGLE_LIKING_CONFIRM_APPEARS), args=[bot, user_id])
        timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=now + datetime.timedelta(minutes=Durations.TASK_GOOGLE_LIKING_TIMEOUT), args=[bot, state.storage, user_id, 'google', 'этап лайков', scheduler])
        await state.update_data(confirm_job_id=confirm_job.id, timeout_job_id=timeout_job.id)

@router.callback_query(F.data == 'google_continue_writing_review', UserState.GOOGLE_REVIEW_READY_TO_CONTINUE)
async def start_liking_step(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    user_id = callback.from_user.id
    
    link = await reference_manager.assign_reference_to_user(user_id, 'google_maps')
    if not link:
        if callback.message:
            await callback.message.edit_text("К сожалению, в данный момент доступных ссылок для написания отзывов не осталось. Попробуйте позже.", reply_markup=inline.get_earning_keyboard())
        await state.clear()
        return

    await start_google_liking_or_main_task(callback, state, bot, scheduler, link)

@router.callback_query(F.data == 'google_confirm_liking_task', UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE)
async def process_liking_completion(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try:
            scheduler.remove_job(timeout_job_id)
        except Exception as e:
            logger.warning(f"Не удалось отменить задачу таймаута {timeout_job_id}: {e}")

    await state.set_state(UserState.GOOGLE_REVIEW_AWAITING_ADMIN_TEXT)
    if callback.message:
        try:
            response_msg = await callback.message.edit_text("✅ Отлично!\n\n⏳ Администратор уже придумывает для вас текст отзыва. Пожалуйста, ожидайте...")
            await schedule_message_deletion(response_msg, 25)
        except TelegramBadRequest: pass
            
    user_info = await bot.get_chat(callback.from_user.id)
    link_id = user_data.get('active_link_id')
    link = await db_manager.db_get_link_by_id(link_id)
    profile_screenshot_id = user_data.get("profile_screenshot_id")

    if not link:
        if callback.message:
            await callback.message.edit_text("Произошла критическая ошибка: не найдена ваша активная ссылка. Начните заново.", reply_markup=inline.get_earning_keyboard())
        await state.clear()
        return

    admin_notification_text = (
        f"Пользователь @{user_info.username} (ID: <code>{callback.from_user.id}</code>) ожидает текст для отзыва Google.\n\n"
        f"🔗 Ссылка для отзыва: <code>{link.url}</code>"
    )
    
    try:
        admin_id = await admin_roles.get_google_issue_admin()
        keyboard = inline.get_admin_provide_text_keyboard('google', callback.from_user.id, link.id)
        if profile_screenshot_id:
            await bot.send_photo(
                chat_id=admin_id,
                photo=profile_screenshot_id,
                caption=admin_notification_text,
                reply_markup=keyboard
            )
        else:
            await bot.send_message(admin_id, admin_notification_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Failed to send task to admin: {e}")

@router.callback_query(F.data == 'google_confirm_task', UserState.GOOGLE_REVIEW_TASK_ACTIVE)
async def process_google_task_completion(callback: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler):
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try:
            scheduler.remove_job(timeout_job_id)
        except Exception as e:
            logger.warning(f"Не удалось отменить задачу таймаута {timeout_job_id}: {e}")
    
    await state.set_state(UserState.GOOGLE_REVIEW_AWAITING_SCREENSHOT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Отлично! Теперь, пожалуйста, отправьте <i>скриншот вашего опубликованного отзыва</i>."
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(F.photo, UserState.GOOGLE_REVIEW_AWAITING_SCREENSHOT)
async def process_google_review_screenshot(message: Message, state: FSMContext, bot: Bot):
    await delete_user_and_prompt_messages(message, state)
    if not message.photo: return
    user_data = await state.get_data()
    user_id = message.from_user.id
    review_text = user_data.get('review_text', 'Текст не был сохранен.')
    photo_file_id = message.photo[-1].file_id
    
    active_link_id = await reference_manager.get_user_active_link_id(user_id)
    if not active_link_id:
        await message.answer("Произошла критическая ошибка: не найдена активная задача. Начните заново.")
        await state.clear()
        return
    
    link_object = await db_manager.db_get_link_by_id(active_link_id)
    link_url = link_object.url if link_object else "Ссылка не найдена"

    caption = (
        f"🚨 <b>Финальная проверка отзыва Google</b> 🚨\n\n"
        f"Пользователь: @{user_data.get('username')} (ID: <code>{user_id}</code>)\n"
        f"Ссылка: <code>{link_url}</code>\n\n"
        f"Текст отзыва: «<i>{review_text}</i>»\n\n"
        "Скриншот прикреплен. Проверьте отзыв и примите решение."
    )
    
    try:
        review_id = await db_manager.create_review_draft(
            user_id=user_id,
            link_id=active_link_id,
            platform='google',
            text=review_text,
            admin_message_id=0,
            screenshot_file_id=photo_file_id
        )

        if not review_id:
            raise Exception("Failed to create review draft in DB.")

        admin_id = await admin_roles.get_google_final_admin()
        sent_message = await bot.send_photo(
            chat_id=admin_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_final_verdict_keyboard(review_id)
        )
        
        await db_manager.db_update_review_admin_message_id(review_id, sent_message.message_id)

        response_msg = await message.answer("Ваш отзыв успешно отправлен на финальную проверку администратором.")
        await schedule_message_deletion(response_msg, 25)

    except Exception as e:
        logger.error(f"Не удалось отправить финальный отзыв админу: {e}", exc_info=True)
        await message.answer("Произошла ошибка при отправке отзыва на проверку. Пожалуйста, свяжитесь с поддержкой.")
    
    await state.clear()
    await state.set_state(UserState.MAIN_MENU)

# --- Логика для Yandex Карт ---

@router.callback_query(F.data == 'review_yandex_maps')
async def choose_yandex_review_type(callback: CallbackQuery, state: FSMContext):
    if callback.message:
        await callback.message.edit_text(
            "Выберите тип отзыва для Yandex.Карт:",
            reply_markup=inline.get_yandex_review_type_keyboard()
        )

@router.callback_query(F.data.startswith('yandex_review_type:'))
async def initiate_yandex_review(callback: CallbackQuery, state: FSMContext):
    review_type = callback.data.split(':')[1]
    user_id = callback.from_user.id
    
    platform = f"yandex_{review_type}"
    
    cooldown = await db_manager.check_platform_cooldown(user_id, platform)
    if cooldown:
        await callback.answer(f"Вы сможете написать отзыв в Yandex ({'с текстом' if review_type == 'with_text' else 'без текста'}) через {format_timedelta(cooldown)}.", show_alert=True)
        return
        
    if not await reference_manager.has_available_references(platform):
        await callback.answer(f"К сожалению, задания для 'Yandex ({'с текстом' if review_type == 'with_text' else 'без текста'})' закончились.", show_alert=True)
        return
    
    await state.update_data(yandex_review_type=review_type)
    await state.set_state(UserState.YANDEX_REVIEW_INIT)

    reward = 50 if review_type == "with_text" else 15
    
    if callback.message:
        await callback.message.edit_text(
            f"⭐ За отзыв в Yandex.Картах ({'с текстом' if review_type == 'with_text' else 'без текста'}) начисляется {reward} звезд.\n\n"
            "💡 Для проверки нам понадобится скриншот вашего профиля.\n"
            "💡 Также выключите <i>«Определение местоположения»</i> для приложения в настройках телефона.\n"
            "💡 Аккаунты принимаются не ниже <i>«Знатока города»</i> 3-го уровня.",
            reply_markup=inline.get_yandex_init_keyboard()
        )

@router.callback_query(F.data == 'yandex_how_to_be_expert', UserState.YANDEX_REVIEW_INIT)
async def show_yandex_instructions(callback: CallbackQuery):
    text = ("💡 Чтобы повысить уровень <i>«Знатока города»</i>, достаточно выполнять достижения.\n"
            "Где их взять? В вашем профиле, нажав на <i>«Знатока города»</i>.")
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_yandex_init_keyboard())

@router.callback_query(F.data == 'yandex_ready_to_screenshot', UserState.YANDEX_REVIEW_INIT)
async def ask_for_yandex_screenshot(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Хорошо. Пожалуйста, сделайте и пришлите <i>скриншот вашего профиля</i> в Яндекс.Картах.\n\n"
            "❗️<i>Требования к скриншоту:</i>\n"
            "1. Скриншот должен быть <i>полным</i>, без обрезаний и замазывания.\n"
            "2. На нем должен быть хорошо виден ваш уровень <i>«Знатока города»</i>.\n"
            "3. Должна быть видна <i>дата вашего последнего отзыва</i>.\n\n"
            "Отправьте фото следующим сообщением.",
            reply_markup=inline.get_yandex_ask_profile_screenshot_keyboard()
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(F.photo, UserState.YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT)
async def process_yandex_profile_screenshot(message: Message, state: FSMContext, bot: Bot):
    await delete_user_and_prompt_messages(message, state)
    if not message.photo: return
    
    photo_file_id = message.photo[-1].file_id
    await state.update_data(profile_screenshot_id=photo_file_id)
    
    await message.answer("Ваш скриншот отправлен на проверку. Ожидайте...")
    await state.set_state(UserState.YANDEX_REVIEW_PROFILE_SCREENSHOT_PENDING)
    
    user_info_text = f"Пользователь: @{message.from_user.username} (ID: <code>{message.from_user.id}</code>)"
    caption = (f"Проверьте скриншот профиля Yandex. Убедитесь, что уровень знатока не ниже 3 и видна дата последнего отзыва.\n"
               f"{user_info_text}")
    
    try:
        user_data = await state.get_data()
        review_type = user_data.get("yandex_review_type", "with_text")
        admin_id = await admin_roles.get_yandex_text_profile_admin() if review_type == "with_text" else await admin_roles.get_yandex_no_text_profile_admin()

        await bot.send_photo(
            chat_id=admin_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_verification_keyboard(
                user_id=message.from_user.id,
                context="yandex_profile_screenshot"
            )
        )
    except Exception as e:
        logger.error(f"Ошибка отправки скриншота Yandex админу: {e}")
        await message.answer("Не удалось отправить фото на проверку. Попробуйте позже.")
        await state.clear()

async def start_yandex_liking_or_main_task(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, link, platform: str):
    """Общая логика для начала этапа прогрева или сразу основного задания (для быстрых ссылок)."""
    user_id = callback.from_user.id

    if link.is_fast_track:
        logger.info(f"Link {link.id} is a fast-track. Skipping liking step for user {user_id}.")
        await process_yandex_liking_completion(callback, state, bot, scheduler)
    else:
        await state.set_state(UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE)
        await state.update_data(username=callback.from_user.username, active_link_id=link.id)
        
        task_text = (
            "<b>Отлично! Ваш профиль одобрен. Теперь следующий шаг:</b>\n\n"
            f"🔗 <a href='{link.url}'>Перейти по ссылке</a>\n"
            "👀 <i>Действия</i>: Проложите маршрут, полистайте фотографии, посмотрите похожие места. "
            "Это нужно для имитации активности перед написанием отзыва.\n\n"
            f"⏳ На это задание у вас есть <i>{Durations.TASK_YANDEX_LIKING_TIMEOUT} минут</i>. Кнопка для подтверждения появится через {Durations.TASK_YANDEX_LIKING_CONFIRM_APPEARS} минут."
        )
        if callback.message:
            await callback.message.edit_text(task_text, disable_web_page_preview=True)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        confirm_job = scheduler.add_job(send_yandex_liking_confirmation_button, 'date', run_date=now + datetime.timedelta(minutes=Durations.TASK_YANDEX_LIKING_CONFIRM_APPEARS), args=[bot, user_id])
        timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=now + datetime.timedelta(minutes=Durations.TASK_YANDEX_LIKING_TIMEOUT), args=[bot, state.storage, user_id, platform, 'этап прогрева', scheduler])
        await state.update_data(confirm_job_id=confirm_job.id, timeout_job_id=timeout_job.id)


@router.callback_query(F.data == 'yandex_continue_task', UserState.YANDEX_REVIEW_READY_TO_TASK)
async def start_yandex_liking_step(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    review_type = user_data.get("yandex_review_type", "with_text")
    platform = f"yandex_{review_type}"

    link = await reference_manager.assign_reference_to_user(user_id, platform)
    if not link:
        if callback.message:
            await callback.message.edit_text(f"К сожалению, в данный момент доступных ссылок для Yandex.Карт ({'с текстом' if review_type == 'with_text' else 'без текста'}) не осталось. Попробуйте позже.", reply_markup=inline.get_earning_keyboard())
        await state.clear()
        return

    await start_yandex_liking_or_main_task(callback, state, bot, scheduler, link, platform)


@router.callback_query(F.data == 'yandex_confirm_liking_task', UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE)
async def process_yandex_liking_completion(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try: scheduler.remove_job(timeout_job_id)
        except Exception as e: logger.warning(f"Не удалось отменить задачу таймаута {timeout_job_id}: {e}")

    review_type = user_data.get("yandex_review_type", "with_text")

    if review_type == "with_text":
        await state.set_state(UserState.YANDEX_REVIEW_AWAITING_ADMIN_TEXT)
        if callback.message:
            response_msg = await callback.message.edit_text("✅ Отлично!\n\n⏳ Администратор уже придумывает для вас текст отзыва. Пожалуйста, ожидайте...")
            await schedule_message_deletion(response_msg, 25)
        
        user_id = callback.from_user.id
        user_info = await bot.get_chat(user_id)
        link_id = user_data.get('active_link_id')
        link = await db_manager.db_get_link_by_id(link_id)
        profile_screenshot_id = user_data.get("profile_screenshot_id")

        if not link:
            if callback.message:
                await callback.message.edit_text("Произошла критическая ошибка: не найдена ваша активная ссылка. Начните заново.", reply_markup=inline.get_earning_keyboard())
            await state.clear()
            return

        admin_notification_text = (
            f"Пользователь @{user_info.username} (ID: <code>{user_id}</code>) ожидает текст для отзыва Yandex (С ТЕКСТОМ).\n\n"
            f"🔗 Ссылка для отзыва: <code>{link.url}</code>"
        )
        
        try:
            admin_id = await admin_roles.get_yandex_text_issue_admin()
            keyboard = inline.get_admin_provide_text_keyboard('yandex_with_text', user_id, link.id)
            if profile_screenshot_id:
                await bot.send_photo(chat_id=admin_id, photo=profile_screenshot_id, caption=admin_notification_text, reply_markup=keyboard)
            else:
                await bot.send_message(admin_id, admin_notification_text, reply_markup=keyboard, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Failed to send task to admin for Yandex: {e}")
    
    else: # review_type == "without_text"
        link_id = user_data.get('active_link_id')
        link = await db_manager.db_get_link_by_id(link_id)
        
        if not link:
            if callback.message:
                await callback.message.edit_text("Произошла критическая ошибка: не найдена ваша активная ссылка. Начните заново.", reply_markup=inline.get_earning_keyboard())
            await state.clear()
            return

        task_text = (
            "<b>ВАШЕ ЗАДАНИЕ ГОТОВО!</b>\n\n"
            f"1. Перейдите по <a href='{link.url}'>ССЫЛКЕ</a>.\n"
            "2. Поставьте <b>5 звезд</b>.\n"
            "3. <b>Текст писать НЕ НУЖНО.</b>\n\n"
            "После этого сделайте скриншот опубликованного отзыва и отправьте его сюда."
        )
        if callback.message:
            prompt_msg = await callback.message.edit_text(task_text, disable_web_page_preview=True)
            await state.update_data(prompt_message_id=prompt_msg.message_id)
        await state.set_state(UserState.YANDEX_REVIEW_AWAITING_SCREENSHOT)

@router.callback_query(F.data == 'yandex_with_text_confirm_task', UserState.YANDEX_REVIEW_TASK_ACTIVE)
async def process_yandex_review_task_completion(callback: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler):
    if callback.message:
        await callback.message.delete()
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try: 
            scheduler.remove_job(timeout_job_id)
        except Exception: 
            pass
    await state.set_state(UserState.YANDEX_REVIEW_AWAITING_SCREENSHOT)
    prompt_msg = await callback.message.answer(
        "Отлично! Теперь отправьте <i>скриншот опубликованного отзыва</i>."
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

    
@router.message(F.photo, UserState.YANDEX_REVIEW_AWAITING_SCREENSHOT)
async def process_yandex_review_screenshot(message: Message, state: FSMContext, bot: Bot):
    await delete_user_and_prompt_messages(message, state)
    if not message.photo: return
    user_data = await state.get_data()
    user_id = message.from_user.id
    review_type = user_data.get("yandex_review_type", "with_text")
    platform = f"yandex_{review_type}"
    photo_file_id = message.photo[-1].file_id

    review_text = user_data.get('review_text', '')
    
    active_link_id = await reference_manager.get_user_active_link_id(user_id)
    if not active_link_id:
        await message.answer("Произошла критическая ошибка: не найдена активная задача. Начните заново.")
        await state.clear()
        return
        
    link_object = await db_manager.db_get_link_by_id(active_link_id)
    link_url = link_object.url if link_object else "Ссылка не найдена"
    
    caption = (
        f"🚨 <b>Финальная проверка отзыва Yandex</b> ({'С ТЕКСТОМ' if review_type == 'with_text' else 'БЕЗ ТЕКСТА'}) 🚨\n\n"
        f"Пользователь: @{user_data.get('username')} (ID: <code>{user_id}</code>)\n"
        f"Ссылка: <code>{link_url}</code>\n\n"
    )
    if review_text:
        caption += f"Текст отзыва: «<i>{review_text}</i>»\n\n"
    else:
        caption += "Тип: Без текста (проверьте наличие 5 звезд).\n\n"
        
    caption += "Скриншот прикреплен. Проверьте отзыв и примите решение."
    
    try:
        review_id = await db_manager.create_review_draft(
            user_id=user_id,
            link_id=active_link_id,
            platform=platform,
            text=review_text,
            admin_message_id=0,
            screenshot_file_id=photo_file_id
        )

        if not review_id:
            raise Exception("Failed to create review draft in DB.")

        admin_id = await admin_roles.get_yandex_text_final_admin() if review_type == "with_text" else await admin_roles.get_yandex_no_text_final_admin()
        sent_message = await bot.send_photo(
            chat_id=admin_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_final_verdict_keyboard(review_id)
        )
        
        await db_manager.db_update_review_admin_message_id(review_id, sent_message.message_id)
        
        await message.answer("Ваш отзыв успешно отправлен на финальную проверку администратором.")

    except Exception as e:
        logger.error(f"Не удалось отправить финальный отзыв админу: {e}", exc_info=True)
        await message.answer("Произошла ошибка при отправке отзыва на проверку. Пожалуйста, свяжитесь с поддержкой.")
        await state.clear()
        return

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)

# --- НОВЫЙ ОБРАБОТЧИК ДЛЯ ПОДТВЕРЖДАЮЩЕГО СКРИНШОТА ---

@router.message(F.photo, UserState.AWAITING_CONFIRMATION_SCREENSHOT)
async def process_confirmation_screenshot(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    """
    Ловит подтверждающий скриншот от пользователя, формирует пакет для админа
    и отправляет на финальную верификацию.
    """
    if not message.photo:
        return

    data = await state.get_data()
    review_id = data.get('review_id_for_confirmation')

    if not review_id:
        await message.answer("Произошла ошибка, не удалось найти ID вашего отзыва. Пожалуйста, обратитесь в поддержку.")
        await state.clear()
        return

    review = await db_manager.get_review_by_id(review_id)
    if not review or not review.screenshot_file_id:
        await message.answer("Произошла критическая ошибка: не найден оригинальный скриншот вашего отзыва. Обратитесь в поддержку.")
        await state.clear()
        return
        
    # Отменяем таймаут на ожидание скриншота
    timeout_job_id = data.get('confirmation_timeout_job_id')
    if timeout_job_id:
        try:
            scheduler.remove_job(timeout_job_id)
        except Exception:
            pass


    try:
        await message.delete()
    except TelegramBadRequest:
        pass
        
    await message.answer("✅ Спасибо! Ваш скриншот отправлен на финальную проверку. Ожидайте решения.")
    
    new_screenshot_file_id = message.photo[-1].file_id
    await db_manager.save_confirmation_screenshot(review_id, new_screenshot_file_id)
    
    admin_text = (
        f"🚨 <b>Подтверждение отзыва</b> 🚨\n\n"
        f"<b>Пользователь:</b> @{message.from_user.username} (ID: <code>{message.from_user.id}</code>)\n"
        f"<b>Ссылка на место:</b> <a href='{review.link.url if review.link else ''}'>Перейти</a>\n\n"
        "Пожалуйста, сравните два скриншота (старый и новый) и примите решение."
    )

    media_group = [
        InputMediaPhoto(media=new_screenshot_file_id, caption=admin_text),
        InputMediaPhoto(media=review.screenshot_file_id)
    ]

    try:
        admin_id = await admin_roles.get_other_hold_admin()
        sent_messages = await bot.send_media_group(
            chat_id=admin_id,
            media=media_group
        )
        
        if sent_messages:
            # Оборачиваем в try-except для подавления ошибки "message is not modified"
            try:
                await bot.edit_message_reply_markup(
                    chat_id=admin_id,
                    message_id=sent_messages[0].message_id,
                    reply_markup=inline.get_admin_final_verification_keyboard(review_id)
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    raise e # Если ошибка другая, пробрасываем ее дальше
                else:
                    logger.warning("Ignored 'message is not modified' error when adding keyboard to media group.")

    except Exception as e:
        logger.error(f"Не удалось отправить файлы для финальной проверки отзыва {review_id} админу: {e}")
        admin_id = await admin_roles.get_other_hold_admin()
        await bot.send_message(admin_id, f"Ошибка при отправке файлов для проверки отзыва #{review_id}. Проверьте логи.")

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)


@router.callback_query(F.data.in_({'review_zoon', 'review_avito', 'review_yandex_services'}))
async def handle_unsupported_services(callback: CallbackQuery):
    platform_map = {
        'review_zoon': 'Zoon',
        'review_avito': 'Avito',
        'review_yandex_services': 'Yandex.Услуги'
    }
    platform_name = platform_map.get(callback.data)
    await callback.answer(f"К сожалению, в данный момент сервис {platform_name} не поддерживается.", show_alert=True)

@router.callback_query(F.data == 'cancel_to_earning')
async def cancel_to_earning_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Действие отменено")
    await earning_menu_logic(callback)