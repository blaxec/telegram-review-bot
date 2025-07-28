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

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager
from references import reference_manager
from config import ADMIN_ID_1, FINAL_CHECK_ADMIN

router = Router()
logger = logging.getLogger(__name__)

TEXT_ADMIN = ADMIN_ID_1

# --- Вспомогательные функции ---

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
    except TelegramNetworkError as e:
        logger.error(f"Не удалось отправить кнопку подтверждения 'лайков' пользователю {user_id}: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки 'лайков' пользователю {user_id}: {e}")

async def send_confirmation_button(bot: Bot, user_id: int, platform: str):
    """Отправляет пользователю кнопку подтверждения основного задания."""
    try:
        await bot.send_message(
            user_id,
            "Кнопка для подтверждения выполнения задания теперь доступна.",
            reply_markup=inline.get_task_confirmation_keyboard(platform)
        )
    except TelegramNetworkError as e:
        logger.error(f"Не удалось отправить кнопку подтверждения пользователю {user_id} для платформы {platform}: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке кнопки подтверждения пользователю {user_id}: {e}")

async def handle_task_timeout(bot: Bot, dp: Dispatcher, user_id: int, platform: str, message_to_admins: str):
    """Обрабатывает истечение времени на любом из этапов задания."""
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    
    current_state_str = await state.get_state()
    if not current_state_str:
        return

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
        f"🔗 [Перейти по ссылке]({link.url})\n"
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
        f"🔗 Ссылка для отзыва: `{link.url}`"
    )
    
    try:
        if profile_screenshot_id:
            await bot.send_photo(
                chat_id=TEXT_ADMIN,
                photo=profile_screenshot_id,
                caption=admin_notification_text,
                reply_markup=inline.get_admin_provide_text_keyboard(callback.from_user.id, link.id)
            )
        else:
            await bot.send_message(TEXT_ADMIN, admin_notification_text, reply_markup=inline.get_admin_provide_text_keyboard(callback.from_user.id, link.id))
    except Exception as e:
        logger.error(f"Failed to send task to TEXT_ADMIN {TEXT_ADMIN}: {e}")
        await bot.send_message(TEXT_ADMIN, admin_notification_text, reply_markup=inline.get_admin_provide_text_keyboard(callback.from_user.id, link.id))


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
        f"Ссылка: `{link_url}`\n\n"
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
        "💡 Чтобы мы точно приняли отзыв, нам нужно проверить ваш профиль. Пожалуйста, скиньте ссылку на профиль.\n"
        "💡 Также выключите **\"Определение местоположения\"** для приложения в настройках телефона.\n"
        "💡 Аккаунты принимаются не ниже **\"Знатока города\"**.\n\n"
        "Отправьте ссылку на профиль или, если не получается, скриншот профиля.",
        reply_markup=inline.get_yandex_init_keyboard()
    )

@router.callback_query(F.data.in_({'yandex_get_profile_link', 'yandex_how_to_be_expert'}), UserState.YANDEX_REVIEW_INIT)
async def show_yandex_instructions(callback: CallbackQuery):
    if callback.data == 'yandex_get_profile_link':
        text = ("🤔 Как получить ссылку на ваш профиль Yandex.Карты:\n\n"
                "1. Зайдите в приложение Yandex.Карты.\n"
                "2. В левом верхнем углу нажмите на аватарку.\n"
                "3. Найдите кнопку **\"Поделиться\"**.\n"
                "4. Нажмите \"Скопировать\" (скопируйте только ссылку, текст не нужен).")
    else:
        text = ("💡 Чтобы повысить уровень \"Знатока города\", достаточно выполнять достижения.\n"
                "Где их взять? В вашем профиле, нажав на **\"Знатока города\"**.")
    await callback.message.edit_text(text, reply_markup=inline.get_yandex_init_keyboard())

@router.message(F.text, UserState.YANDEX_REVIEW_INIT)
async def process_yandex_profile_link(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.strip().startswith("https://yandex.ru/maps/user/"):
        await message.answer("Неверный формат. Пожалуйста, отправьте корректную ссылку на ваш профиль в Яндекс.Картах или используйте кнопку для отправки скриншота.",
                               reply_markup=inline.get_yandex_init_keyboard())
        return
    await message.answer("Ваша ссылка отправлена на проверку. Ожидайте...")
    await state.set_state(UserState.YANDEX_REVIEW_PROFILE_CHECK_PENDING)
    caption = (
        f"[Админ: @SHAD0W_F4]\n"
        f"Проверьте профиль Yandex пользователя @{message.from_user.username} (ID: `{message.from_user.id}`)\n"
        f"Ссылка: {message.text}"
    )
    try:
        await bot.send_message(
            chat_id=FINAL_CHECK_ADMIN,
            text=caption,
            reply_markup=inline.get_admin_verification_keyboard(message.from_user.id, "yandex_profile"),
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Ошибка отправки профиля Yandex админу: {e}")
        await message.answer("Не удалось отправить ссылку на проверку. Попробуйте позже.")
        await state.clear()

@router.callback_query(F.data == 'yandex_use_screenshot', UserState.YANDEX_REVIEW_INIT)
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
async def start_yandex_review_task(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, dp: Dispatcher):
    await callback.message.delete()
    user_id = callback.from_user.id
    link = await reference_manager.assign_reference_to_user(user_id, 'yandex_maps')
    if not link:
        await callback.message.answer("К сожалению, в данный момент доступных ссылок для Yandex.Карт не осталось. Попробуйте позже.")
        await state.clear()
        return
    task_text = (
        "Отлично! Выполните следующие действия:\n\n"
        "⏳ На данные действия дается **30 минут**.\n"
        f"🔗 [Перейти по ссылке]({link.url}) **Переходить по ней через Telegram нельзя!**\n"
        "👀 Просмотрите всю страницу.\n"
        "👍 Поставьте на положительные отзывы лайки.\n\n"
        "Через 10 минут появится кнопка \"Выполнено\"."
    )
    await callback.message.answer(task_text, parse_mode='Markdown', disable_web_page_preview=True)
    await state.set_state(UserState.YANDEX_REVIEW_TASK_ACTIVE)
    await state.update_data(username=callback.from_user.username)
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduler.add_job(send_confirmation_button, 'date', run_date=now + datetime.timedelta(minutes=10), args=[bot, user_id, 'yandex'])
    timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=now + datetime.timedelta(minutes=30), args=[bot, dp, user_id, 'yandex', 'основное задание'])
    await state.update_data(timeout_job_id=timeout_job.id)

@router.callback_query(F.data == 'yandex_confirm_task', UserState.YANDEX_REVIEW_TASK_ACTIVE)
async def process_yandex_review_task_completion(callback: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler):
    await callback.message.delete()
    user_data = await state.get_data()
    timeout_job_id = user_data.get('timeout_job_id')
    if timeout_job_id:
        try: scheduler.remove_job(timeout_job_id)
        except: pass
    await state.set_state(UserState.YANDEX_REVIEW_AWAITING_TEXT_PHOTO)
    await callback.message.answer(
        "Отлично! Теперь **отправьте текст вашего отзыва** (обязательно 5 звезд).\n\n"
        "💡 **Совет:** Системы Яндекса могут отфильтровывать отзывы, которые были скопированы и вставлены. "
        "Чтобы ваш отзыв с большей вероятностью прошел модерацию, рекомендуем набирать текст вручную."
    )
    
@router.message(F.text, UserState.YANDEX_REVIEW_AWAITING_TEXT_PHOTO)
async def process_yandex_review_text(message: Message, state: FSMContext):
    await state.update_data(review_text=message.text)
    await message.answer("Текст получен. Теперь отправьте **скриншот опубликованного отзыва**.")

@router.message(F.photo, UserState.YANDEX_REVIEW_AWAITING_TEXT_PHOTO)
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
        f"Ссылка: `{link_url}`\n\n"
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