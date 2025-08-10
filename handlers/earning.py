# file: handlers/earning.py

import datetime
import logging
from aiogram import Router, F, Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from database import db_manager
from references import reference_manager
from config import ADMIN_ID_1, FINAL_CHECK_ADMIN
# ИСПРАВЛЕНИЕ: Импортируем служебные функции из нового файла
from logic.user_notifications import (
    format_timedelta,
    send_liking_confirmation_button,
    send_yandex_liking_confirmation_button,
    handle_task_timeout
)

router = Router()
logger = logging.getLogger(__name__)

TEXT_ADMIN = ADMIN_ID_1

# --- Основное меню Заработка ---

@router.message(F.text == 'Заработок', UserState.MAIN_MENU)
async def earning_handler(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer("💰 Способы заработка:", reply_markup=inline.get_earning_keyboard())

@router.callback_query(F.data == 'earning_write_review')
async def initiate_write_review(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Выберите платформу для написания отзыва:",
        reply_markup=inline.get_write_review_platform_keyboard()
    )
    
@router.callback_query(F.data == 'earning_menu_back')
async def earning_menu_back(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💰 Способы заработка:", reply_markup=inline.get_earning_keyboard())

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
    await callback.message.edit_text(
        "⭐ За отзыв в Google.Картах начисляется 15 звезд.\n\n"
        "💡 Для повышения проходимости вашего отзыва, пожалуйста, временно отключите "
        "**\"Определение местоположения\"** в настройках приложения на вашем телефоне.",
        reply_markup=inline.get_google_init_keyboard()
    )

@router.callback_query(F.data == 'google_review_done', UserState.GOOGLE_REVIEW_INIT)
async def process_google_review_done(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
    await callback.message.edit_text(
        "Отлично! Теперь, чтобы мы могли проверить, готовы ли вы писать отзыв, пожалуйста, "
        "пришлите **скриншот вашего профиля** в Google.Картах. "
        "Отзывы на новых аккаунтах не будут проходить проверку.\n\n"
        "Отправьте фото следующим сообщением.",
        reply_markup=inline.get_google_ask_profile_screenshot_keyboard()
    )

@router.callback_query(F.data == 'google_get_profile_screenshot', UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
async def show_google_profile_screenshot_instructions(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤔 Как сделать скриншот вашего профиля Google.Карты:\n\n"
        "1. Перейдите по ссылке: [Профиль Google Maps](https://www.google.com/maps/contrib/)\n"
        "2. Вас переведет на профиль Google Карты.\n"
        "3. Сделайте скриншот вашего профиля (без замазывания и обрезания).",
        reply_markup=inline.get_google_ask_profile_screenshot_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@router.message(F.photo, UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT)
async def process_google_profile_screenshot(message: Message, state: FSMContext, bot: Bot):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(profile_screenshot_id=photo_file_id)
    
    await message.answer("Ваш скриншот отправлен на проверку. Ожидайте...")
    await state.set_state(UserState.GOOGLE_REVIEW_PROFILE_CHECK_PENDING)
    user_info_text = f"Пользователь: @{message.from_user.username} (ID: `{message.from_user.id}`)"
    caption = f"[Админ: @SHAD0W_F4]\nПроверьте имя и фамилию в профиле пользователя.\n{user_info_text}"
    try:
        await bot.send_photo(
            chat_id=FINAL_CHECK_ADMIN,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_verification_keyboard(message.from_user.id, "google_profile")
        )
    except Exception as e:
        print(f"Ошибка отправки фото профиля админу: {e}")
        await message.answer("Не удалось отправить фото на проверку. Попробуйте позже.")
        await state.clear()

@router.message(F.photo, UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
async def process_google_last_reviews_screenshot(message: Message, state: FSMContext, bot: Bot):
    await message.answer("Ваши последние отзывы отправлены на проверку. Ожидайте...")
    await state.set_state(UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK_PENDING)
    user_info_text = f"Пользователь: @{message.from_user.username} (ID: `{message.from_user.id}`)"
    caption = f"[Админ: @SHAD0W_F4]\nПроверьте последние отзывы пользователя. Интервал - 3 дня.\n{user_info_text}"
    try:
        await bot.send_photo(
            chat_id=FINAL_CHECK_ADMIN,
            photo=message.photo[-1].file_id,
            caption=caption,
            reply_markup=inline.get_admin_verification_keyboard(message.from_user.id, "google_last_reviews")
        )
    except Exception as e:
        print(f"Ошибка отправки фото последних отзывов админу: {e}")
        await message.answer("Не удалось отправить фото на проверку. Попробуйте позже.")
        await state.clear()

@router.callback_query(F.data == 'google_continue_writing_review', UserState.GOOGLE_REVIEW_READY_TO_CONTINUE)
async def start_liking_step(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, dp: Dispatcher):
    await callback.message.delete()
    user_id = callback.from_user.id
    
    link = await reference_manager.assign_reference_to_user(user_id, 'google_maps')
    if not link:
        await callback.message.answer("К сожалению, в данный момент доступных ссылок для написания отзывов не осталось. Попробуйте позже.")
        await state.clear()
        return

    task_text = (
        "Отлично! Следующий шаг:\n\n"
        f"🔗 [Перейти по ссылке]({link.url}) \n"
        "👀 Просмотрите страницу и поставьте лайки на положительные отзывы.\n\n"
        "⏳ Для выполнения этого задания у вас есть **10 минут**. Кнопка для подтверждения появится через 5 минут."
    )
    await callback.message.answer(task_text, parse_mode='Markdown', disable_web_page_preview=True)
    await state.set_state(UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE)
    await state.update_data(username=callback.from_user.username, active_link_id=link.id)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduler.add_job(send_liking_confirmation_button, 'date', run_date=now + datetime.timedelta(minutes=5), args=[bot, user_id])
    timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=now + datetime.timedelta(minutes=10), args=[bot, dp, user_id, 'google', 'этап лайков'])
    await state.update_data(timeout_job_id=timeout_job.id)

@router.callback_query(F.data == 'google_confirm_liking_task', UserState.GOOGLE_REVIEW_LIKING_TASK_ACTIVE)
async def process_liking_completion(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    await callback.message.delete()
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try:
            scheduler.remove_job(timeout_job_id)
        except Exception as e:
            print(f"Не удалось отменить задачу таймаута {timeout_job_id}: {e}")

    await state.set_state(UserState.GOOGLE_REVIEW_AWAITING_ADMIN_TEXT)
    await callback.message.answer("✅ Отлично!\n\n⏳ Администратор уже придумывает для вас текст отзыва. Пожалуйста, ожидайте...")
            
    user_info = await bot.get_chat(callback.from_user.id)
    link_id = user_data.get('active_link_id')
    link = await db_manager.db_get_link_by_id(link_id)
    profile_screenshot_id = user_data.get("profile_screenshot_id")

    if not link:
        await callback.message.answer("Произошла критическая ошибка: не найдена ваша активная ссылка. Начните заново.")
        await state.clear()
        return

    admin_notification_text = (
        f"Пользователь @{user_info.username} (ID: `{callback.from_user.id}`) прошел этап 'лайков' и ожидает текст для отзыва Google.\n\n"
        f"🔗 Ссылка для отзыва: `{link.url} `"
    )
    
    try:
        keyboard = inline.get_admin_provide_text_keyboard('google', callback.from_user.id, link.id)
        if profile_screenshot_id:
            await bot.send_photo(
                chat_id=TEXT_ADMIN,
                photo=profile_screenshot_id,
                caption=admin_notification_text,
                reply_markup=keyboard
            )
        else:
            await bot.send_message(TEXT_ADMIN, admin_notification_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Failed to send task to TEXT_ADMIN {TEXT_ADMIN}: {e}")
        keyboard = inline.get_admin_provide_text_keyboard('google', callback.from_user.id, link.id)
        await bot.send_message(TEXT_ADMIN, admin_notification_text, reply_markup=keyboard)


@router.callback_query(F.data == 'google_confirm_task', UserState.GOOGLE_REVIEW_TASK_ACTIVE)
async def process_google_task_completion(callback: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler):
    await callback.message.delete()
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try:
            scheduler.remove_job(timeout_job_id)
        except Exception as e:
            print(f"Не удалось отменить задачу таймаута {timeout_job_id}: {e}")
    
    await state.set_state(UserState.GOOGLE_REVIEW_AWAITING_SCREENSHOT)
    await callback.message.answer(
        "Отлично! Теперь, пожалуйста, отправьте **скриншот вашего опубликованного отзыва**."
    )

@router.message(F.photo, UserState.GOOGLE_REVIEW_AWAITING_SCREENSHOT)
async def process_google_review_screenshot(message: Message, state: FSMContext, bot: Bot):
    user_data = await state.get_data()
    user_id = message.from_user.id
    review_text = user_data.get('review_text', 'Текст не был сохранен.')
    
    active_link_id = await reference_manager.get_user_active_link_id(user_id)
    if not active_link_id:
        await message.answer("Произошла критическая ошибка: не найдена активная задача. Начните заново.")
        await state.clear()
        return
    
    link_object = await db_manager.db_get_link_by_id(active_link_id)
    link_url = link_object.url if link_object else "Ссылка не найдена"

    caption = (
        f"🚨 Финальная проверка отзыва Google 🚨\n\n"
        f"Пользователь: @{user_data.get('username')} (ID: `{user_id}`)\n"
        f"Ссылка: `{link_url} `\n\n"
        f"Текст отзыва: «_{review_text}_»\n\n"
        "Скриншот прикреплен. Проверьте отзыв и примите решение."
    )
    
    try:
        sent_message = await bot.send_photo(
            chat_id=FINAL_CHECK_ADMIN,
            photo=message.photo[-1].file_id,
            caption=caption,
            reply_markup=inline.get_admin_final_verdict_keyboard(0)
        )
        
        review_id = await db_manager.create_review_draft(
            user_id=user_id,
            link_id=active_link_id,
            platform='google',
            text=review_text,
            admin_message_id=sent_message.message_id
        )

        await bot.edit_message_reply_markup(
            chat_id=FINAL_CHECK_ADMIN,
            message_id=sent_message.message_id,
            reply_markup=inline.get_admin_final_verdict_keyboard(review_id)
        )

        await message.answer("Ваш отзыв успешно отправлен на финальную проверку администратором.")

    except Exception as e:
        print(f"Не удалось отправить финальный отзыв админу {FINAL_CHECK_ADMIN}: {e}")
        await message.answer("Произошла ошибка при отправке отзыва на проверку. Пожалуйста, свяжитесь с поддержкой.")
    
    await state.clear()
    await state.set_state(UserState.MAIN_MENU)

# --- Логика для Yandex Карт ---

@router.callback_query(F.data == 'review_yandex_maps')
async def initiate_yandex_review(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cooldown = await db_manager.check_platform_cooldown(user_id, "yandex")
    if cooldown:
        await callback.answer(f"Вы сможете написать отзыв в Yandex через {format_timedelta(cooldown)}.", show_alert=True)
        return
    if not await reference_manager.has_available_references('yandex_maps'):
        await callback.answer("К сожалению, в данный момент задания для Yandex.Карт закончились. Попробуйте позже.", show_alert=True)
        return
        
    await state.set_state(UserState.YANDEX_REVIEW_INIT)
    await callback.message.edit_text(
        "⭐ За отзыв в Yandex.Картах начисляется 50 звезд.\n\n"
        "💡 Для проверки нам понадобится скриншот вашего профиля.\n"
        "💡 Также выключите **\"Определение местоположения\"** для приложения в настройках телефона.\n"
        "💡 Аккаунты принимаются не ниже **\"Знатока города\"**.",
        reply_markup=inline.get_yandex_init_keyboard()
    )

@router.callback_query(F.data == 'yandex_how_to_be_expert', UserState.YANDEX_REVIEW_INIT)
async def show_yandex_instructions(callback: CallbackQuery):
    text = ("💡 Чтобы повысить уровень \"Знатока города\", достаточно выполнять достижения.\n"
            "Где их взять? В вашем профиле, нажав на **\"Знатока города\"**.")
    await callback.message.edit_text(text, reply_markup=inline.get_yandex_init_keyboard())

@router.callback_query(F.data == 'yandex_ready_to_screenshot', UserState.YANDEX_REVIEW_INIT)
async def ask_for_yandex_screenshot(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT)
    await callback.message.edit_text(
        "Хорошо. Пожалуйста, сделайте и пришлите **скриншот вашего профиля** в Яндекс.Картах.\n\n"
        "❗️**Требования к скриншоту:**\n"
        "1. Скриншот должен быть **полным**, без обрезаний и замазывания.\n"
        "2. На нем должен быть хорошо виден ваш уровень **\"Знатока города\"**.\n"
        "3. Должна быть видна **дата вашего последнего отзыва**.\n\n"
        "Отправьте фото следующим сообщением.",
        reply_markup=inline.get_yandex_ask_profile_screenshot_keyboard()
    )

@router.message(F.photo, UserState.YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT)
async def process_yandex_profile_screenshot(message: Message, state: FSMContext, bot: Bot):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(profile_screenshot_id=photo_file_id)
    
    await message.answer("Ваш скриншот отправлен на проверку. Ожидайте...")
    await state.set_state(UserState.YANDEX_REVIEW_PROFILE_SCREENSHOT_PENDING)
    
    user_info_text = f"Пользователь: @{message.from_user.username} (ID: `{message.from_user.id}`)"
    caption = (f"[Админ: @SHAD0W_F4]\n"
               f"Проверьте скриншот профиля Yandex. Убедитесь, что виден уровень знатока и дата последнего отзыва.\n"
               f"{user_info_text}")
    try:
        await bot.send_photo(
            chat_id=FINAL_CHECK_ADMIN,
            photo=photo_file_id,
            caption=caption,
            reply_markup=inline.get_admin_verification_keyboard(message.from_user.id, "yandex_profile_screenshot")
        )
    except Exception as e:
        logger.error(f"Ошибка отправки скриншота Yandex админу: {e}")
        await message.answer("Не удалось отправить фото на проверку. Попробуйте позже.")
        await state.clear()

@router.callback_query(F.data == 'yandex_continue_task', UserState.YANDEX_REVIEW_READY_TO_TASK)
async def start_yandex_liking_step(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, dp: Dispatcher):
    await callback.message.delete()
    user_id = callback.from_user.id
    link = await reference_manager.assign_reference_to_user(user_id, 'yandex_maps')
    if not link:
        await callback.message.answer("К сожалению, в данный момент доступных ссылок для Yandex.Карт не осталось. Попробуйте позже.")
        await state.clear()
        return

    await state.set_state(UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE)
    await state.update_data(username=callback.from_user.username, active_link_id=link.id)
    
    task_text = (
        "Отлично! Ваш профиль одобрен. Теперь следующий шаг:\n\n"
        f"🔗 [Перейти по ссылке]({link.url})\n"
        "👀 **Действия**: Проложите маршрут, полистайте фотографии, посмотрите похожие места. "
        "Это нужно для имитации активности перед написанием отзыва.\n\n"
        "⏳ На это задание у вас есть **10 минут**. Кнопка для подтверждения появится через 5 минут."
    )
    await callback.message.answer(task_text, parse_mode='Markdown', disable_web_page_preview=True)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduler.add_job(send_yandex_liking_confirmation_button, 'date', run_date=now + datetime.timedelta(minutes=5), args=[bot, user_id])
    timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=now + datetime.timedelta(minutes=10), args=[bot, dp, user_id, 'yandex', 'этап прогрева'])
    await state.update_data(timeout_job_id=timeout_job.id)


@router.callback_query(F.data == 'yandex_confirm_liking_task', UserState.YANDEX_REVIEW_LIKING_TASK_ACTIVE)
async def process_yandex_liking_completion(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    await callback.message.delete()
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try: scheduler.remove_job(timeout_job_id)
        except Exception as e: logger.warning(f"Не удалось отменить задачу таймаута {timeout_job_id}: {e}")

    await state.set_state(UserState.YANDEX_REVIEW_AWAITING_ADMIN_TEXT)
    await callback.message.answer("✅ Отлично!\n\n⏳ Администратор уже придумывает для вас текст отзыва. Пожалуйста, ожидайте...")
            
    user_id = callback.from_user.id
    user_info = await bot.get_chat(user_id)
    link_id = user_data.get('active_link_id')
    link = await db_manager.db_get_link_by_id(link_id)
    profile_screenshot_id = user_data.get("profile_screenshot_id")

    if not link:
        await callback.message.answer("Произошла критическая ошибка: не найдена ваша активная ссылка. Начните заново.")
        await state.clear()
        return

    admin_notification_text = (
        f"Пользователь @{user_info.username} (ID: `{user_id}`) прошел этап 'прогрева' и ожидает текст для отзыва Yandex.\n\n"
        f"🔗 Ссылка для отзыва: `{link.url}`"
    )

    try:
        keyboard = inline.get_admin_provide_text_keyboard('yandex', user_id, link.id)
        if profile_screenshot_id:
            await bot.send_photo(
                chat_id=TEXT_ADMIN,
                photo=profile_screenshot_id,
                caption=admin_notification_text,
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                TEXT_ADMIN, 
                admin_notification_text, 
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Failed to send task to TEXT_ADMIN {TEXT_ADMIN} for Yandex: {e}")
        keyboard = inline.get_admin_provide_text_keyboard('yandex', user_id, link.id)
        await bot.send_message(TEXT_ADMIN, admin_notification_text, reply_markup=keyboard)


@router.callback_query(F.data == 'yandex_confirm_task', UserState.YANDEX_REVIEW_TASK_ACTIVE)
async def process_yandex_review_task_completion(callback: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler):
    await callback.message.delete()
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try: 
            scheduler.remove_job(timeout_job_id)
        except Exception: 
            pass
    await state.set_state(UserState.YANDEX_REVIEW_AWAITING_SCREENSHOT)
    await callback.message.answer(
        "Отлично! Теперь отправьте **скриншот опубликованного отзыва**."
    )
    
@router.message(F.photo, UserState.YANDEX_REVIEW_AWAITING_SCREENSHOT)
async def process_yandex_review_screenshot(message: Message, state: FSMContext, bot: Bot):
    user_data = await state.get_data()
    user_id = message.from_user.id
    review_text = user_data.get('review_text', 'Текст не был сохранен.')
    
    active_link_id = await reference_manager.get_user_active_link_id(user_id)
    if not active_link_id:
        await message.answer("Произошла критическая ошибка: не найдена активная задача. Начните заново.")
        await state.clear()
        return
        
    link_object = await db_manager.db_get_link_by_id(active_link_id)
    link_url = link_object.url if link_object else "Ссылка не найдена"
    
    caption = (
        f"🚨 Финальная проверка отзыва Yandex 🚨\n\n"
        f"Пользователь: @{user_data.get('username')} (ID: `{user_id}`)\n"
        f"Ссылка: `{link_url} `\n\n"
        f"Текст отзыва: «_{review_text}_»\n\n"
        "Скриншот прикреплен. Проверьте отзыв и примите решение."
    )
    
    try:
        sent_message = await bot.send_photo(
            chat_id=FINAL_CHECK_ADMIN,
            photo=message.photo[-1].file_id,
            caption=caption,
            reply_markup=inline.get_admin_final_verdict_keyboard(0)
        )

        review_id = await db_manager.create_review_draft(
            user_id=user_id,
            link_id=active_link_id,
            platform='yandex',
            text=review_text,
            admin_message_id=sent_message.message_id
        )

        await bot.edit_message_reply_markup(
            chat_id=FINAL_CHECK_ADMIN,
            message_id=sent_message.message_id,
            reply_markup=inline.get_admin_final_verdict_keyboard(review_id)
        )

        await message.answer("Ваш отзыв успешно отправлен на финальную проверку администратором.")

    except Exception as e:
        print(f"Не удалось отправить финальный отзыв админу {FINAL_CHECK_ADMIN}: {e}")
        await message.answer("Произошла ошибка при отправке отзыва на проверку. Пожалуйста, свяжитесь с поддержкой.")
        await state.clear()
        return

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)


# --- Прочие хэндлеры ---
@router.callback_query(F.data == 'review_yandex_services')
async def handle_yandex_services(callback: CallbackQuery):
    await callback.answer("К сожалению, в данный момент сервис Yandex.Услуги не поддерживается.", show_alert=True)