# file: handlers/admin.py

from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_ID_1, ADMIN_IDS, FINAL_CHECK_ADMIN
from database import db_manager
from references import reference_manager
from handlers.earning import send_confirmation_button, handle_task_timeout, notify_cooldown_expired
import datetime

router = Router()
logger = logging.getLogger(__name__)

ADMINS = set(ADMIN_IDS)
TEXT_ADMIN = ADMIN_ID_1

router.message.filter(F.from_user.id.in_(ADMINS))
router.callback_query.filter(F.from_user.id.in_(ADMINS))


@router.message(Command("addstars"))
async def admin_add_stars(message: Message):
    admin_id = message.from_user.id
    await db_manager.update_balance(admin_id, 999.0)
    await message.answer("✅ На ваш баланс зачислено 999 ⭐.")


# --- БЛОК: УПРАВЛЕНИЕ ССЫЛКАМИ (Только для ADMIN_ID_1) ---
@router.message(Command("admin_refs"), F.from_user.id == ADMIN_ID_1)
async def admin_refs_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())


@router.callback_query(F.data == "back_to_refs_menu", F.from_user.id == ADMIN_ID_1)
async def back_to_refs_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    except TelegramBadRequest as e:
        logger.warning(f"Error editing message on back_to_refs_menu: {e}")


@router.callback_query(F.data.startswith("admin_refs:add:"), F.from_user.id == ADMIN_ID_1)
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
    platform = callback.data.split(':')[2]

    current_state = None
    if platform == "google_maps":
        current_state = AdminState.ADD_GOOGLE_REFERENCE
    elif platform == "yandex_maps":
        current_state = AdminState.ADD_YANDEX_REFERENCE

    if current_state:
        await state.set_state(current_state)
        await state.update_data(platform=platform)
        await callback.message.edit_text(
            f"Отправьте одну или несколько ссылок для **{platform}**, каждую с новой строки.",
            reply_markup=inline.get_back_to_admin_refs_keyboard()
        )


@router.message(AdminState.ADD_GOOGLE_REFERENCE, F.from_user.id == ADMIN_ID_1)
@router.message(AdminState.ADD_YANDEX_REFERENCE, F.from_user.id == ADMIN_ID_1)
async def admin_add_ref_process(message: Message, state: FSMContext):
    links = message.text.split('\n')
    added_count = 0
    skipped_count = 0
    data = await state.get_data()
    platform = data.get("platform")

    for link in links:
        link = link.strip()
        if not link or not link.startswith("http"):
            continue
        
        success = await reference_manager.add_reference(link, platform)
        if success:
            added_count += 1
        else:
            skipped_count += 1

    await message.answer(
        f"Готово!\n"
        f"✅ Успешно добавлено: {added_count}\n"
        f"⏭️ Пропущено (ошибки): {skipped_count}"
    )
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    await state.clear()


@router.callback_query(F.data.startswith("admin_refs:stats:"), F.from_user.id == ADMIN_ID_1)
async def admin_view_refs_stats(callback: CallbackQuery):
    try:
        await callback.answer("Загружаю статистику...", show_alert=False)
    except TelegramBadRequest:
        pass
    platform = callback.data.split(':')[2]

    all_links = await reference_manager.get_all_references(platform)

    total = len(all_links)
    available = len([link for link in all_links if link.status == 'available'])
    assigned = len([link for link in all_links if link.status == 'assigned'])
    used = len([link for link in all_links if link.status == 'used'])

    stats_text = (
        f"📊 Статистика по ссылкам для **{platform}**:\n\n"
        f"Всего ссылок: {total}\n"
        f"🟢 Доступно: {available}\n"
        f"🟡 В работе: {assigned}\n"
        f"🔴 Использовано: {used}"
    )
    await callback.message.edit_text(stats_text, reply_markup=inline.get_back_to_admin_refs_keyboard())


@router.callback_query(F.data.startswith("admin_refs:list:"), F.from_user.id == ADMIN_ID_1)
async def admin_view_refs_list(callback: CallbackQuery):
    try:
        await callback.answer("Загружаю список...")
    except TelegramBadRequest:
        pass
    platform = callback.data.split(':')[2]

    all_links = await reference_manager.get_all_references(platform)

    await callback.message.edit_text(f"Список ссылок для **{platform}**:", reply_markup=inline.get_back_to_admin_refs_keyboard())

    if not all_links:
        await callback.message.answer("В базе нет ссылок для этой платформы.")
        return

    for link in all_links:
        status_icon = {"available": "🟢", "assigned": "🟡", "used": "🔴", "expired": "⚫"}.get(link.status, "❓")
        user_info = f"-> ID: {link.assigned_to_user_id}" if link.assigned_to_user_id else ""
        link_text = (
            f"{status_icon} **ID: {link.id}** | Статус: `{link.status}` {user_info}\n"
            f"🔗 `{link.url}`"
        )
        await callback.message.answer(
            link_text,
            reply_markup=inline.get_delete_ref_keyboard(link.id),
            disable_web_page_preview=True
        )


@router.callback_query(F.data.startswith("admin_refs:delete:"), F.from_user.id == ADMIN_ID_1)
async def admin_delete_ref(callback: CallbackQuery, bot: Bot, dp: Dispatcher):
    link_id = int(callback.data.split(':')[2])

    success, assigned_user_id = await reference_manager.delete_reference(link_id)

    if not success:
        try:
            await callback.answer("Не удалось удалить ссылку. Возможно, она уже удалена.", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    await callback.message.delete()
    try:
        await callback.answer(f"Ссылка с ID {link_id} успешно удалена.", show_alert=True)
    except TelegramBadRequest:
        pass

    if assigned_user_id:
        try:
            user_state = FSMContext(
                storage=dp.storage,
                key=StorageKey(bot_id=bot.id, user_id=assigned_user_id, chat_id=assigned_user_id)
            )
            await user_state.clear()
            await bot.send_message(
                assigned_user_id,
                "❗️ Внимание! Ссылка, на которой вы выполняли задание, была удалена администратором. "
                "Ваш процесс остановлен. Пожалуйста, вернитесь в главное меню и начните заново.",
                reply_markup=reply.get_main_menu_keyboard()
            )
            await user_state.set_state(UserState.MAIN_MENU)
        except Exception as e:
            print(f"Не удалось уведомить пользователя {assigned_user_id} об удалении ссылки: {e}")


# --- БЛОК: МОДЕРАЦИЯ И ДРУГИЕ КОМАНДЫ (Доступны обоим админам) ---

@router.message(Command("viewhold"))
async def admin_view_user_hold(message: Message, bot: Bot):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /viewhold ID_пользователя_или_@username")
        return

    identifier = args[1]
    user_id = await db_manager.find_user_by_identifier(identifier)

    if not user_id:
        await message.answer(f"Пользователь `{identifier}` не найден в базе данных.")
        return

    user = await db_manager.get_user(user_id)
    reviews_in_hold = await db_manager.get_user_hold_reviews(user_id)

    if not reviews_in_hold:
        await message.answer(f"У пользователя @{user.username} (ID: `{user_id}`) нет отзывов в холде.")
        return

    total_hold_amount = sum(review.amount for review in reviews_in_hold)

    response_text = f"⏳ Отзывы в холде для пользователя @{user.username} (ID: `{user_id}`)\n"
    response_text += f"Общая сумма в холде: **{total_hold_amount}** ⭐\n\n"

    for review in reviews_in_hold:
        hold_until_str = review.hold_until.strftime('%d.%m.%Y %H:%M') if review.hold_until else 'N/A'
        response_text += (
            f"🔹 **{review.amount} ⭐** (платформа: {review.platform})\n"
            f"   - Срок холда: до {hold_until_str} UTC\n"
            f"   - ID отзыва: `{review.id}`\n\n"
        )

    await message.answer(response_text)


@router.callback_query(F.data.startswith('admin_verify:'))
async def admin_verification_handler(callback: CallbackQuery, state: FSMContext, bot: Bot, dp: Dispatcher):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    _, action, context, user_id_str = callback.data.split(':')
    user_id = int(user_id_str)
    admin_id = callback.from_user.id
    admin_username = callback.from_user.username
    admin_state = state
    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))

    original_text = callback.message.text if callback.message.text else callback.message.caption

    if action == "confirm":
        action_text = f"✅ ПОДТВЕРЖДЕНО (админ @{admin_username})"
        if context == "google_profile":
            await user_state.set_state(UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
            await bot.send_message(user_id, "Профиль прошел проверку. Теперь пришлите скриншот ваших последних отзывов.", reply_markup=inline.get_google_last_reviews_check_keyboard())
        elif context == "google_last_reviews":
            await user_state.set_state(UserState.GOOGLE_REVIEW_READY_TO_CONTINUE)
            await bot.send_message(user_id, "Ваши отзывы прошли проверку. Можете продолжить.", reply_markup=inline.get_google_continue_writing_keyboard())
        elif context == "yandex_profile" or context == "yandex_profile_screenshot":
            await user_state.set_state(UserState.YANDEX_REVIEW_READY_TO_TASK)
            await bot.send_message(user_id, "Ваш профиль Yandex прошел проверку. Можете продолжить.", reply_markup=inline.get_yandex_continue_writing_keyboard())
        elif context == "gmail_device_model":
            await state.set_state(AdminState.ENTER_GMAIL_DATA)
            await state.update_data(gmail_user_id=user_id)
            await callback.message.answer(
                "✅ Модель устройства подтверждена.\n"
                "Теперь введите данные для создания аккаунта в формате:\n"
                "Имя\nФамилия\nПароль\nПочта (без @gmail.com)"
            )

        try:
            if callback.message.photo:
                await callback.message.edit_caption(caption=f"{original_text}\n\n{action_text}", reply_markup=None)
            else:
                await callback.message.edit_text(f"{original_text}\n\n{action_text}", reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Не удалось отредактировать сообщение при подтверждении: {e}")


    elif action == "warn":
        action_text = f"⚠️ ПРЕДУПРЕЖДЕНИЕ ВЫДАНО (админ @{admin_username})"
        new_text = f"{original_text}\n\n{action_text}"

        try:
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Не удалось отредактировать сообщение при выдаче предупреждения: {e}")
        
        platform = context.split('_')[0]
        warnings_count = await db_manager.add_user_warning(user_id, platform=platform)
        user_message_text = "⚠️ Администратор выдал вам предупреждение за несоблюдение правил.\n"

        if warnings_count >= 3:
            user_message_text += f"\n❗️ **Это ваше 3-е предупреждение. Возможность выполнять задания для платформы {platform.capitalize()} заблокирована на 24 часа.**"
            await user_state.clear()
        else:
            state_to_return_map = {
                "google_profile": UserState.GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT,
                "google_last_reviews": UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK,
                "yandex_profile": UserState.YANDEX_REVIEW_INIT,
                "yandex_profile_screenshot": UserState.YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT
            }
            state_to_return = state_to_return_map.get(context)
            if state_to_return:
                await user_state.set_state(state_to_return)
                user_message_text += "\nПожалуйста, исправьте ошибку и повторите попытку."

        try:
            await bot.send_message(user_id, user_message_text, reply_markup=inline.get_back_to_main_menu_keyboard())
            await bot.send_message(admin_id, f"Предупреждение успешно отправлено пользователю {user_id}.")
        except Exception as e:
            await bot.send_message(admin_id, f"Не удалось отправить предупреждение пользователю {user_id}. Ошибка: {e}")

    elif action == "reject":
        action_text = "❌ ОТКЛОНЕН"
        new_text = f"{original_text}\n\n{action_text} (админ @{admin_username})"

        try:
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Не удалось отредактировать сообщение при отклонении: {e}")

        await bot.send_message(admin_id, f"Пожалуйста, отправьте следующим сообщением причину, по которой вы выбрали '{action_text}' для пользователя {user_id_str}.")

        reason_state_map = {
            "google_profile": AdminState.REJECT_REASON_GOOGLE_PROFILE,
            "google_last_reviews": AdminState.REJECT_REASON_GOOGLE_LAST_REVIEWS,
            "yandex_profile": AdminState.REJECT_REASON_YANDEX_PROFILE,
            "yandex_profile_screenshot": AdminState.REJECT_REASON_YANDEX_PROFILE,
            "gmail_device_model": AdminState.REJECT_REASON_GMAIL_DATA_REQUEST,
        }
        if context in reason_state_map:
            reason_state = reason_state_map[context]
            await admin_state.set_state(reason_state)
            await admin_state.update_data(target_user_id=user_id)
        else:
            await bot.send_message(admin_id, "Ошибка: неизвестный контекст для действия.")


@router.callback_query(F.data.startswith('admin_provide_text:'), F.from_user.id == TEXT_ADMIN)
async def admin_start_providing_text(callback: CallbackQuery, state: FSMContext):
    try:
        is_photo = bool(callback.message.photo)
        message_text = callback.message.caption if is_photo else callback.message.text

        _, platform, user_id_str, link_id_str = callback.data.split(':')
        user_id = int(user_id_str)
        link_id = int(link_id_str)
        
        current_state = AdminState.PROVIDE_GOOGLE_REVIEW_TEXT
        if platform == 'yandex':
            current_state = AdminState.PROVIDE_YANDEX_REVIEW_TEXT
        
        await state.set_state(current_state)
        await state.update_data(
            target_user_id=user_id,
            target_link_id=link_id,
            platform=platform
        )
        
        if is_photo:
            await callback.message.edit_caption(
                caption=f"{message_text}\n\n✍️ Введите текст отзыва для пользователя ID: {user_id}",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(f"Введите текст отзыва для пользователя ID: {user_id}", reply_markup=None)
    except (TelegramBadRequest, Exception) as e:
        logger.warning(f"Error editing message on admin_start_providing_text: {e}")


@router.message(F.text, F.state.in_({AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, AdminState.PROVIDE_YANDEX_REVIEW_TEXT}), F.from_user.id == TEXT_ADMIN)
async def admin_process_review_text(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, dp: Dispatcher):
    data = await state.get_data()
    user_id = data.get("target_user_id")
    link_id = data.get("target_link_id")
    platform = data.get("platform")
    review_text_from_admin = message.text

    if not all([user_id, link_id, platform]):
        await message.answer("Критическая ошибка: не найдены все необходимые данные (ID пользователя, ссылки или платформа). Процесс прерван.")
        await state.clear()
        return

    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    user_info = await bot.get_chat(user_id)
    link = await db_manager.db_get_link_by_id(link_id)

    if not link:
        await message.answer(f"Не удалось найти ссылку с ID {link_id} для пользователя.")
        await bot.send_message(user_id, "Произошла ошибка, ваша ссылка для задания не найдена. Начните заново.")
        await user_state.clear()
        await state.clear()
        return

    if platform == "google":
        task_state = UserState.GOOGLE_REVIEW_TASK_ACTIVE
        task_message = (
            "<b>ВАШЕ ЗАДАНИЕ ГОТОВО!</b>\n\n"
            "1. Перепишите текст ниже. Вы должны опубликовать отзыв, который *В ТОЧНОСТИ* совпадает с этим текстом.\n"
            "2. Перейдите по ссылке и оставьте отзыв на 5 звезд, переписав текст.\n\n"
            "❗️❗️❗️ <b>ВНИМАНИЕ:</b> Не изменяйте текст, не добавляйте и не убирайте символы или эмодзи. Отзыв должен быть идентичным. КОПИРОВАТЬ И ВСТАВЛЯТЬ ТЕКСТ НЕЛЬЗЯ\n\n"
            "<b>Текст для отзыва:</b>\n"
            f"{review_text_from_admin}\n\n"
            f"🔗 <b>[ПЕРЕЙТИ К ЗАДАНИЮ]({link.url})</b> \n\n"
            "⏳ На выполнение задания у вас есть <b>15 минут</b>. Кнопка для подтверждения появится через <b>7 минут</b>."
        )
        run_date_confirm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=7)
        run_date_timeout = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)

    elif platform == "yandex":
        task_state = UserState.YANDEX_REVIEW_TASK_ACTIVE
        task_message = (
            "<b>ВАШЕ ЗАДАНИЕ ГОТОВО!</b>\n\n"
            "1. Перепишите текст ниже. Вы должны опубликовать отзыв на <b>5 звезд</b>, который *В ТОЧНОСТИ* совпадает с этим текстом.\n\n"
            "❗️❗️❗️ <b>ВНИМАНИЕ:</b> Не изменяйте текст, не добавляйте и не убирайте символы или эмодзи. Отзыв должен быть идентичным. КОПИРОВАТЬ И ВСТАВЛЯТЬ ТЕКСТ НЕЛЬЗЯ\n\n"
            "<b>Текст для отзыва:</b>\n"
            f"{review_text_from_admin}\n\n"
            f"🔗 <b>[ПЕРЕЙТИ К ЗАДАНИЮ]({link.url})</b> \n\n"
            "⏳ На выполнение задания у вас есть <b>25 минут</b>. Кнопка для подтверждения появится через <b>10 минут</b>."
        )
        run_date_confirm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
        run_date_timeout = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=25)
    else:
        await message.answer(f"Неизвестная платформа: {platform}")
        await state.clear()
        return

    try:
        await bot.send_message(user_id, task_message, parse_mode='HTML', disable_web_page_preview=True)
        await message.answer(f"Текст успешно отправлен пользователю @{user_info.username} (ID: {user_id}).")
    except Exception as e:
        await message.answer(f"Не удалось отправить задание пользователю {user_id}. Ошибка: {e}")
        await reference_manager.release_reference_from_user(user_id, 'available')
        await user_state.clear()
        await state.clear()
        return

    await user_state.set_state(task_state)
    await user_state.update_data(username=user_info.username, review_text=review_text_from_admin)

    scheduler.add_job(send_confirmation_button, 'date', run_date=run_date_confirm, args=[bot, user_id, platform])
    timeout_job = scheduler.add_job(handle_task_timeout, 'date', run_date=run_date_timeout, args=[bot, dp, user_id, platform, 'основное задание'])
    await user_state.update_data(timeout_job_id=timeout_job.id)

    await state.clear()


@router.message(
    F.text,
    F.state.in_({
        AdminState.REJECT_REASON_GOOGLE_PROFILE,
        AdminState.REJECT_REASON_GOOGLE_LAST_REVIEWS,
        AdminState.REJECT_REASON_YANDEX_PROFILE,
        AdminState.REJECT_REASON_GOOGLE_REVIEW,
        AdminState.REJECT_REASON_YANDEX_REVIEW,
        AdminState.REJECT_REASON_GMAIL_ACCOUNT,
        AdminState.REJECT_REASON_GMAIL_DATA_REQUEST
    })
)
async def process_admin_reason(message: Message, state: FSMContext, bot: Bot):
    reason = message.text
    admin_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"Admin {admin_id} is providing a rejection reason. State: {current_state}, Reason: {reason}")
    
    admin_data = await state.get_data()
    user_id = admin_data.get("target_user_id")

    if not user_id:
        await message.answer("Критическая ошибка: не найден ID пользователя. Состояние будет сброшено.")
        await state.clear()
        return

    user_fsm_context = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    
    if current_state == AdminState.REJECT_REASON_GMAIL_DATA_REQUEST:
        user_message_text = f"❌ Ваш запрос на создание аккаунта с другого устройства был отклонен.\n\nПричина: «{reason}»"
        await user_fsm_context.set_state(UserState.GMAIL_ACCOUNT_INIT)
    else:
        user_message_text = f"❌ Ваша проверка была отклонена администратором.\n\nПричина: «{reason}»"
        await user_fsm_context.set_state(UserState.MAIN_MENU)
        
    try:
        await bot.send_message(user_id, user_message_text, reply_markup=inline.get_back_to_main_menu_keyboard())
        await message.answer(f"Сообщение об отклонении отправлено пользователю {user_id}.")
    except Exception as e:
        await message.answer(f"Не удалось отправить сообщение пользователю {user_id}. Ошибка: {e}")

    await state.clear()


@router.callback_query(F.data.startswith('admin_final_approve:'))
async def admin_final_approve(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        review_id = int(callback.data.split(':')[1])
        review = await db_manager.get_review_by_id(review_id)
        if not review or review.status != 'pending':
            await callback.answer("Ошибка: отзыв не найден или уже обработан.", show_alert=True)
            return

        amount_map = {'google': 15.0, 'yandex': 50.0}
        amount = amount_map.get(review.platform, 0.0)

        hold_minutes_map = {'google': 5, 'yandex': 24 * 60}
        hold_duration_minutes = hold_minutes_map.get(review.platform, 24 * 60)
        cooldown_hours = 72

        success = await db_manager.move_review_to_hold(review_id, amount, hold_minutes=hold_duration_minutes)
        
        if success:
            hold_hours = hold_duration_minutes / 60
            await callback.answer(f"Одобрено. Отзыв отправлен в холд на {hold_hours:.2f} ч.", show_alert=True)
            
            await db_manager.set_platform_cooldown(review.user_id, review.platform, cooldown_hours)
            
            cooldown_end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=cooldown_hours)
            scheduler.add_job(notify_cooldown_expired, 'date', run_date=cooldown_end_time,
                              args=[bot, review.user_id, review.platform],
                              id=f"cooldown_notify_{review.user_id}_{review.platform}")
            
            await reference_manager.release_reference_from_user(review.user_id, 'used')
            
            try:
                await bot.send_message(review.user_id, f"✅ Ваш отзыв ({review.platform}) успешно прошел первичную проверку и отправлен в холд. +{amount} ⭐ добавлены в холд.")
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {review.user_id} об одобрении в холд: {e}")
            
            await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ ОТЗЫВ ОТПРАВЛЕН В ХОЛД (админом @{callback.from_user.username})", reply_markup=None)
        else:
            await callback.answer("Не удалось одобрить отзыв.", show_alert=True)
    except Exception as e:
        logger.error(f"Критическая ошибка в admin_final_approve: {e}")
        await callback.answer("Произошла внутренняя ошибка.", show_alert=True)


@router.callback_query(F.data.startswith('admin_final_reject:'))
async def admin_final_reject_request(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass

    try:
        review_id = int(callback.data.split(':')[1])
        review = await db_manager.get_review_by_id(review_id)
        if not review:
            await callback.message.edit_caption(caption=f"{callback.message.caption}\n\nОшибка: отзыв не найден.", reply_markup=None)
            return

        rejected_review = await db_manager.admin_reject_review(review_id)
        if rejected_review:
            cooldown_hours = 72
            await db_manager.set_platform_cooldown(rejected_review.user_id, rejected_review.platform, cooldown_hours)

            cooldown_end_time = datetime.datetime.utcnow() + datetime.timedelta(hours=cooldown_hours)
            scheduler.add_job(notify_cooldown_expired, 'date', run_date=cooldown_end_time,
                              args=[bot, rejected_review.user_id, rejected_review.platform],
                              id=f"cooldown_notify_{rejected_review.user_id}_{rejected_review.platform}")
                              
            await reference_manager.release_reference_from_user(rejected_review.user_id, 'available')
            try:
                user_message = f"❌ Ваш отзыв (платформа: {rejected_review.platform}) был отклонен администратором. Вы не сможете писать отзывы на этой платформе в течение 3 дней."
                await callback.bot.send_message(rejected_review.user_id, user_message, reply_markup=inline.get_back_to_main_menu_keyboard())
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {rejected_review.user_id} об отклонении: {e}")

            await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ ОТЗЫВ ОТКЛОНЕН (админом @{callback.from_user.username}). Пользователю выдан кулдаун.", reply_markup=None)
        else:
            await callback.answer("Не удалось отклонить отзыв.", show_alert=True)
    except Exception as e:
        logger.error(f"Критическая ошибка в admin_final_reject_request: {e}")
        await callback.answer("Произошла внутренняя ошибка.", show_alert=True)


@router.message(Command("reviewhold"))
async def admin_review_hold(message: Message, bot: Bot):
    await message.answer("⏳ Загружаю список отзывов в холде...")
    hold_reviews = await db_manager.get_all_hold_reviews()

    if not hold_reviews:
        await message.answer("В холде нет отзывов для проверки.")
        return

    await message.answer(f"Найдено отзывов в холде: {len(hold_reviews)}")
    for review in hold_reviews:
        link_url = review.link.url if review.link else "Ссылка удалена"
        
        info_text = (
            f"Отзыв ID: `{review.id}`\n"
            f"Пользователь ID: `{review.user_id}`\n"
            f"Платформа: `{review.platform}`\n"
            f"Сумма: `{review.amount}` ⭐\n"
            f"Ссылка: `{link_url} `\n\n"
            f"Текст: «_{review.review_text}_»"
        )
        
        try:
            if review.admin_message_id:
                await bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=FINAL_CHECK_ADMIN,
                    message_id=review.admin_message_id,
                    caption=info_text,
                    reply_markup=inline.get_admin_hold_review_keyboard(review.id)
                )
            else:
                await message.answer(info_text, reply_markup=inline.get_admin_hold_review_keyboard(review.id))
        except Exception as e:
            await message.answer(f"Не удалось обработать отзыв {review.id}. Возможно, сообщение со скриншотом было удалено. Ошибка: {e}\n\n{info_text}",
                                 reply_markup=inline.get_admin_hold_review_keyboard(review.id))


@router.callback_query(F.data.startswith('admin_hold_approve:'))
async def admin_hold_approve_handler(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        review_id = int(callback.data.split(':')[1])
        
        approved_review = await db_manager.admin_approve_review(review_id)
        if not approved_review:
            await callback.answer("❌ Ошибка: отзыв не найден или уже обработан.", show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=None)
            return

        if approved_review.platform == 'google':
            user = await db_manager.get_user(approved_review.user_id)
            if user and user.referrer_id:
                amount = 0.45
                await db_manager.add_referral_earning(user_id=approved_review.user_id, amount=amount)
                try:
                    await bot.send_message(
                        user.referrer_id,
                        f"🎉 Ваш реферал @{user.username} успешно написал отзыв! Вам начислено {amount} ⭐."
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить реферера {user.referrer_id}: {e}")
        
        await callback.answer("✅ Отзыв одобрен!", show_alert=True)
        new_caption = (callback.message.caption or "") + f"\n\n✅ ОДОБРЕН @{callback.from_user.username}"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)
        try:
            await bot.send_message(approved_review.user_id, f"✅ Ваш отзыв (ID: {review_id}) был одобрен администратором! +{approved_review.amount} ⭐ зачислены на ваш основной баланс.")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {approved_review.user_id} об одобрении: {e}")
    except Exception as e:
        logger.error(f"Ошибка в admin_hold_approve_handler: {e}")
        await callback.answer("Произошла ошибка при одобрении.", show_alert=True)


@router.callback_query(F.data.startswith('admin_hold_reject:'))
async def admin_hold_reject_handler(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        review_id = int(callback.data.split(':')[1])

        review_before_rejection = await db_manager.get_review_by_id(review_id)
        if not review_before_rejection or review_before_rejection.status != 'on_hold':
            await callback.answer("❌ Ошибка: отзыв не найден или уже обработан.", show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=None)
            return

        rejected_review = await db_manager.admin_reject_review(review_id)
        if rejected_review:
            await callback.answer("❌ Отзыв отклонен!", show_alert=True)
            new_caption = (callback.message.caption or "") + f"\n\n❌ ОТКЛОНЕН @{callback.from_user.username}"
            await callback.message.edit_caption(caption=new_caption, reply_markup=None)
            try:
                user_message = f"❌ Ваш отзыв (ID: {review_id}) был отклонен администратором после проверки. Звезды списаны из холда."
                await bot.send_message(rejected_review.user_id, user_message, reply_markup=inline.get_back_to_main_menu_keyboard())
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {rejected_review.user_id} об отклонении: {e}")
        else:
            await callback.answer("❌ Не удалось отклонить отзыв.", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в admin_hold_reject_handler: {e}")
        await callback.answer("Произошла ошибка при отклонении.", show_alert=True)


@router.callback_query(F.data.startswith("admin_withdraw_approve:"))
async def admin_approve_withdrawal(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        request_id = int(callback.data.split(":")[1])
        
        request = await db_manager.approve_withdrawal_request(request_id)
        
        if request is None:
            await callback.answer("❌ Запрос уже обработан или не найден.", show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=None)
            return

        await callback.answer("✅ Вывод подтвержден.", show_alert=True)
        
        new_text = callback.message.text + f"\n\n**[ ✅ ПОДТВЕРЖДЕНО администратором @{callback.from_user.username} ]**"
        await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)
        
        try:
            await bot.send_message(
                request.user_id,
                f"✅ Ваш запрос на вывод {request.amount} ⭐ был **подтвержден** администратором."
            )
        except Exception as e:
            logger.error(f"Failed to notify user {request.user_id} about withdrawal approval: {e}")
    except Exception as e:
        logger.error(f"Ошибка в admin_approve_withdrawal: {e}")


@router.callback_query(F.data.startswith("admin_withdraw_reject:"))
async def admin_reject_withdrawal(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    try:
        request_id = int(callback.data.split(":")[1])
        
        request = await db_manager.reject_withdrawal_request(request_id)
        
        if request is None:
            await callback.answer("❌ Запрос уже обработан или не найден.", show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=None)
            return

        await callback.answer("❌ Вывод отклонен. Средства возвращены пользователю.", show_alert=True)
        
        new_text = callback.message.text + f"\n\n**[ ❌ ОТКЛОНЕНО администратором @{callback.from_user.username} ]**"
        await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)
        
        try:
            await bot.send_message(
                request.user_id,
                f"❌ Ваш запрос на вывод {request.amount} ⭐ был **отклонен** администратором. "
                "Средства возвращены на ваш основной баланс."
            )
        except Exception as e:
            logger.error(f"Failed to notify user {request.user_id} about withdrawal rejection: {e}")
    except Exception as e:
        logger.error(f"Ошибка в admin_reject_withdrawal: {e}")


@router.message(Command("reset_cooldown"), F.from_user.id == ADMIN_ID_1)
async def reset_cooldown_handler(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ **Ошибка!**\nИспользуйте команду так: `/reset_cooldown ID_пользователя_или_@username`")
        return
    
    identifier = args[1]
    user_id = await db_manager.find_user_by_identifier(identifier)

    if not user_id:
        await message.answer(f"❌ Пользователь `{identifier}` не найден в базе данных.")
        return

    success = await db_manager.reset_user_cooldowns(user_id)
    
    if success:
        user = await db_manager.get_user(user_id)
        username = f"@{user.username}" if user.username else f"ID: {user_id}"
        await message.answer(
            f"✅ Все кулдауны и предупреждения для пользователя **{username}** были успешно сброшены.",
            reply_markup=inline.get_back_to_main_menu_keyboard()
        )
    else:
        await message.answer(f"❌ Произошла неизвестная ошибка при сбросе кулдаунов для пользователя `{identifier}`.")