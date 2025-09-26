# file: telegram-review-bot-main/handlers/admin.py


import datetime
import logging
import asyncio
from math import ceil

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import SUPER_ADMIN_ID, ADMIN_IDS, Durations, Limits
from database import db_manager
from references import reference_manager
from logic.admin_logic import (
    process_add_links_logic,
    process_rejection_reason_logic,
    process_warning_reason_logic,
    send_review_text_to_user_logic,
    approve_review_to_hold_logic,
    reject_initial_review_logic,
    get_user_hold_info_logic,
    approve_withdrawal_logic,
    reject_withdrawal_logic,
    apply_fine_to_user,
    approve_final_review_logic,
    reject_final_review_logic,
    format_banned_user_page,
    format_promo_code_page,
    get_paginated_links_text, # НОВЫЙ ИМПОРТ
    get_unban_requests_page, # НОВЫЙ ИМПОРТ
    process_unban_request_logic # НОВЫЙ ИМПОРТ
)
from logic.ai_helper import generate_review_text
from logic.ocr_helper import analyze_screenshot
from logic.cleanup_logic import check_and_expire_links
from logic import admin_roles
from logic.notification_manager import send_notification_to_admins # ИЗМЕНЕНИЕ
from utils.access_filters import IsAdmin, IsSuperAdmin

router = Router()
logger = logging.getLogger(__name__)

async def schedule_message_deletion(message: Message, delay: int):
    """Вспомогательная функция для планирования удаления сообщения."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

async def delete_previous_messages(message: Message, state: FSMContext):
    """Вспомогательная функция для удаления старых сообщений."""
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

# --- ГЛОБАЛЬНЫЕ АДМИН КОМАНДЫ ---

@router.message(Command("addstars"), IsSuperAdmin())
async def admin_add_stars(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    await db_manager.update_balance(message.from_user.id, 999.0, op_type="TOP_REWARD", description="Начисление через команду /addstars")
    msg = await message.answer(f"✅ На ваш баланс зачислено 999.0 ⭐.")
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))

# --- НОВЫЕ КОМАНДЫ ДЛЯ DND и PENDING_TASKS ---

@router.message(Command("dnd"), IsAdmin())
async def toggle_dnd_mode(message: Message, state: FSMContext):
    try: await message.delete()
    except TelegramBadRequest: pass
    
    new_dnd_status = await db_manager.toggle_dnd_status(message.from_user.id)
    
    if new_dnd_status:
        response_text = "🌙 Ночной режим включен. Вы больше не будете получать рабочие уведомления."
    else:
        response_text = "☀️ Ночной режим выключен. Вы снова получаете все рабочие уведомления."
    
    msg = await message.answer(response_text)
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
    await state.clear()

@router.message(Command("pending_tasks"), IsAdmin())
async def show_pending_tasks(message: Message, state: FSMContext):
    try: await message.delete()
    except TelegramBadRequest: pass
    
    tasks_count = await db_manager.get_pending_tasks_count()
    
    text = (
        "📥 <b>Задачи, ожидающие внимания:</b>\n\n"
        f"➡️ <b>Отзывы на проверку:</b> {tasks_count['reviews']} шт.\n"
        f"➡️ <b>Открытые тикеты поддержки:</b> {tasks_count['tickets']} шт.\n\n"
        "<i>Используйте соответствующие разделы для обработки.</i>"
    )
    
    msg = await message.answer(text)
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_INFO_MESSAGE_DELAY))
    await state.clear()

# --- БЛОК: УПРАВЛЕНИЕ ССЫЛКАМИ ---

@router.message(Command("admin_refs"), IsSuperAdmin())
async def admin_refs_menu(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())

@router.callback_query(F.data.startswith("admin_refs:select_platform:"), IsSuperAdmin())
async def admin_select_ref_platform(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    platform = callback.data.split(':')[2]
    await state.update_data(current_platform=platform)

    platform_names = {
        "google_maps": "Google Карты",
        "yandex_with_text": "Яндекс (с текстом)",
        "yandex_without_text": "Яндекс (без текста)"
    }
    platform_name = platform_names.get(platform, platform)
    
    if callback.message:
        await callback.message.edit_text(
            f"Управление ссылками для платформы: <b>{platform_name}</b>",
            reply_markup=inline.get_admin_platform_refs_keyboard(platform)
        )


@router.callback_query(F.data == "admin_refs:back_to_selection", IsSuperAdmin())
async def admin_back_to_platform_selection(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())


@router.callback_query(F.data.startswith("admin_refs:add:"), IsSuperAdmin())
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    try:
        _, _, link_type, photo_req, platform = callback.data.split(':')
    except ValueError:
        await callback.answer("Ошибка в данных кнопки.", show_alert=True)
        return
        
    is_fast = (link_type == 'fast')
    requires_photo = (photo_req == 'photo')

    type_text = []
    if is_fast: type_text.append("быстрые 🚀")
    if requires_photo: type_text.append("с фото 📸")
    if not type_text: type_text.append("обычные")
    
    final_type_text = " и ".join(type_text)

    await state.set_state(AdminState.ADD_LINKS)
    await state.update_data(
        platform_for_links=platform,
        is_fast_track_for_links=is_fast,
        requires_photo_for_links=requires_photo
    )
    
    if callback.message:
        # ИЗМЕНЕНИЕ: Добавляем платформу в callback_data для корректного возврата
        cancel_button = inline.get_cancel_inline_keyboard(f"admin_refs:select_platform:{platform}")
        prompt_msg = await callback.message.edit_text(
            f"Выбрана платформа: <i>{platform}</i>.\n"
            f"Тип добавляемых ссылок: <b>{final_type_text}</b>.\n\n"
            f"Отправьте ссылки следующим сообщением. Каждая ссылка с новой строки.",
            reply_markup=cancel_button
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()

@router.message(AdminState.ADD_LINKS, F.text, IsSuperAdmin())
async def admin_add_links_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    # ИЗМЕНЕНИЕ: Удаляем предыдущее сообщение с инпутом и промпт
    await delete_previous_messages(message, state)

    platform = data.get("platform_for_links")
    is_fast = data.get("is_fast_track_for_links")
    requires_photo = data.get("requires_photo_for_links")
    
    try:
        result_text = await process_add_links_logic(message.text, platform, is_fast_track=is_fast, requires_photo=requires_photo)
        await message.answer(result_text, reply_markup=inline.get_back_to_platform_refs_keyboard(platform))
    except Exception as e:
        logger.exception(f"Критическая ошибка (FSM) при добавлении ссылок: {e}")
        await message.answer("❌ Произошла критическая ошибка. Обратитесь к логам.", reply_markup=inline.get_back_to_platform_refs_keyboard(platform))
    finally:
        await state.clear()

@router.callback_query(F.data.startswith("admin_refs:stats:"), IsSuperAdmin())
async def admin_view_refs_stats(callback: CallbackQuery):
    await callback.answer("Загружаю...", show_alert=False)
    platform = callback.data.split(':')[2]
    stats = await db_manager.db_get_link_stats(platform)
    
    text = (f"📊 Статистика по <i>{platform}</i>:\n\n"
            f"Всего: {stats.get('total', 0)}\n"
            f"🟢 Доступно: {stats.get('available', 0)}\n"
            f"🟡 В работе: {stats.get('assigned', 0)}\n"
            f"🔴 Использовано: {stats.get('used', 0)}\n"
            f"⚫ Просрочено: {stats.get('expired', 0)}")
            
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_back_to_platform_refs_keyboard(platform))


# --- ОБНОВЛЕННЫЙ БЛОК ПРОСМОТРА СПИСКА ССЫЛОК ---

@router.callback_query(F.data.startswith("admin_refs:list"), IsSuperAdmin())
async def admin_view_refs_list(callback: CallbackQuery, state: FSMContext):
    """Отображает первую страницу списка ссылок с фильтрами."""
    await callback.answer()
    
    parts = callback.data.split(':')
    platform = parts[2]
    # Устанавливаем фильтр по умолчанию "all"
    filter_type = parts[3] if len(parts) > 3 else "all"
    
    await state.update_data(link_list_filter=filter_type)
    
    await show_links_page(callback, state, platform, filter_type, page=1)

async def show_links_page(callback: CallbackQuery, state: FSMContext, platform: str, filter_type: str, page: int):
    """Отображает конкретную страницу списка ссылок."""
    total_links, links_on_page = await db_manager.db_get_paginated_references(platform, page, Limits.LINKS_PER_PAGE, filter_type)
    total_pages = ceil(total_links / Limits.LINKS_PER_PAGE) if total_links > 0 else 1
    
    page_text = get_paginated_links_text(links_on_page, page, total_pages, platform, filter_type)
    keyboard = inline.get_link_list_control_keyboard(platform, page, total_pages, filter_type)
    
    if callback.message:
        await callback.message.edit_text(page_text, reply_markup=keyboard, disable_web_page_preview=True)

@router.callback_query(F.data.startswith("links_page:"), IsSuperAdmin())
async def link_list_paginator(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает пагинацию и смену фильтров."""
    await callback.answer()
    
    _, platform, page_str = callback.data.split(":")
    page = int(page_str)
    
    data = await state.get_data()
    filter_type = data.get("link_list_filter", "all")
    
    await show_links_page(callback, state, platform, filter_type, page)

@router.callback_query(F.data.startswith("admin_refs:delete_start:"), IsSuperAdmin())
async def admin_delete_ref_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    platform = callback.data.split(':')[2]
    await state.set_state(AdminState.DELETE_LINK_ID)
    await state.update_data(platform_for_deletion=platform)
    if callback.message:
        # ИЗМЕНЕНИЕ: Добавляем платформу в callback_data для корректного возврата
        cancel_button = inline.get_cancel_inline_keyboard(f"admin_refs:select_platform:{platform}")
        prompt_msg = await callback.message.edit_text(
            "Введите ID ссылок, которые хотите удалить.\n"
            "Можно ввести несколько ID через пробел или запятую.", 
            reply_markup=cancel_button
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.DELETE_LINK_ID, IsSuperAdmin())
async def admin_process_delete_ref_id(message: Message, state: FSMContext, bot: Bot):
    # Удаляем сообщение с ID и промпт
    await delete_previous_messages(message, state)
    data = await state.get_data()
    platform = data.get("platform_for_deletion")

    if not message.text:
        msg = await message.answer("❌ Пожалуйста, введите один или несколько ID.")
        asyncio.create_task(schedule_message_deletion(msg, 5))
        return

    link_ids_str = message.text.replace(',', ' ').split()
    deleted_ids, not_found_ids = [], []
    
    for link_id_str in link_ids_str:
        if not link_id_str.strip().isdigit():
            continue
        link_id = int(link_id_str.strip())
        success, assigned_user_id = await reference_manager.delete_reference(link_id)
        
        if success:
            deleted_ids.append(str(link_id))
            if assigned_user_id:
                try:
                    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=assigned_user_id, chat_id=assigned_user_id))
                    await user_state.clear()
                    await bot.send_message(assigned_user_id, "❗️ Ссылка для вашего задания была удалена администратором. Процесс остановлен.", reply_markup=reply.get_main_menu_keyboard())
                    await user_state.set_state(UserState.MAIN_MENU)
                except Exception as e: 
                    logger.warning(f"Не удалось уведомить {assigned_user_id} об удалении ссылки: {e}")
        else:
            not_found_ids.append(str(link_id))

    summary_text = ""
    if deleted_ids:
        summary_text += f"✅ Удалены ID: <code>{', '.join(deleted_ids)}</code>\n"
    if not_found_ids:
        summary_text += f"❌ Не найдены ID: <code>{', '.join(not_found_ids)}</code>"
    if not summary_text:
         summary_text = "Не найдено корректных ID для удаления."
    
    # Отправляем временное сообщение и сразу же "нажимаем" на кнопку, чтобы обновить список
    temp_message = await message.answer(summary_text)
    await state.clear()
    
    # Имитируем нажатие на кнопку для возврата к списку
    dummy_callback_query = CallbackQuery(
        id=str(message.message_id), from_user=message.from_user, chat_instance="dummy", 
        message=temp_message, 
        data=f"admin_refs:list:{platform}:all"
    )
    await admin_view_refs_list(callback=dummy_callback_query, state=state)

@router.callback_query(F.data.startswith("admin_refs:return_start:"), IsSuperAdmin())
async def admin_return_ref_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса возврата ссылки в 'available'."""
    await callback.answer()
    platform = callback.data.split(':')[2]
    await state.set_state(AdminState.RETURN_LINK_ID)
    await state.update_data(platform_for_return=platform)
    if callback.message:
        # ИЗМЕНЕНИЕ: Добавляем платформу в callback_data для корректного возврата
        cancel_button = inline.get_cancel_inline_keyboard(f"admin_refs:select_platform:{platform}")
        prompt_msg = await callback.message.edit_text(
            "Введите ID 'зависшей' ссылки (в статусе 'assigned'), которую хотите вернуть в доступные:", 
            reply_markup=cancel_button
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.RETURN_LINK_ID, IsSuperAdmin())
async def admin_process_return_ref_id(message: Message, state: FSMContext, bot: Bot):
    """Обработка ID ссылки для возврата."""
    await delete_previous_messages(message, state)
    data = await state.get_data()
    platform = data.get("platform_for_return")

    if not message.text or not message.text.isdigit():
        msg = await message.answer("❌ Пожалуйста, введите корректный числовой ID.")
        asyncio.create_task(schedule_message_deletion(msg, 5))
        return
    
    link_id = int(message.text)
    success, assigned_user_id = await reference_manager.force_release_reference(link_id)
    
    result_text = ""
    if not success:
        result_text = f"❌ Не удалось вернуть ссылку с ID {link_id}. Возможно, она не в статусе 'assigned' или не найдена."
    else:
        result_text = f"✅ Ссылка ID {link_id} возвращена в статус 'available'."

    if assigned_user_id:
        try:
            user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=assigned_user_id, chat_id=assigned_user_id))
            await user_state.clear()
            await bot.send_message(assigned_user_id, "❗️ Администратор прервал ваше задание. Ссылка была возвращена в пул. Процесс остановлен.", reply_markup=reply.get_main_menu_keyboard())
            await user_state.set_state(UserState.MAIN_MENU)
        except Exception as e: 
            logger.warning(f"Не удалось уведомить {assigned_user_id} о возврате ссылки: {e}")

    await state.clear()
    
    temp_message = await message.answer(result_text)
    dummy_callback_query = CallbackQuery(
        id=str(message.message_id), from_user=message.from_user, chat_instance="dummy", 
        message=temp_message,
        data=f"admin_refs:list:{platform}:all"
    )
    await admin_view_refs_list(callback=dummy_callback_query, state=state)

# --- БЛОК ПРОВЕРКИ И ВЕРИФИКАЦИИ ---
@router.callback_query(F.data.startswith("admin_ocr:"), IsAdmin())
async def admin_ocr_check(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Администратор нажимает кнопку для AI-проверки скриншота."""
    try:
        _, context, user_id_str = callback.data.split(":")
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        await callback.answer("Ошибка в данных кнопки.", show_alert=True)
        return

    if not (callback.message and callback.message.photo):
        await callback.answer("Не удалось найти фото для анализа.", show_alert=True)
        return
    file_id = callback.message.photo[-1].file_id
    original_caption = callback.message.caption or ""

    await callback.answer("🤖 Запускаю проверку с помощью ИИ...", show_alert=False)

    try:
        await callback.message.edit_caption(
            caption=f"{original_caption}\n\n🤖 <b>Запущена проверка с помощью ИИ...</b>",
            reply_markup=None 
        )
    except TelegramBadRequest:
        pass

    task_map = {
        'yandex_profile_screenshot': 'yandex_profile_check',
        'google_last_reviews': 'google_reviews_check',
        'google_profile': 'google_profile_check'
    }
    task = task_map.get(context)

    if not task:
        try:
            await callback.message.answer("Неизвестная задача для OCR.")
            await callback.message.edit_reply_markup(reply_markup=inline.get_admin_verification_keyboard(user_id, context))
        except TelegramBadRequest: pass
        return

    ocr_result = await analyze_screenshot(bot, file_id, task)
    
    ai_summary_text = ""
    if ocr_result.get('status') == 'success':
        summary = ocr_result.get('analysis_summary', 'Анализ завершен.')
        reasoning = ocr_result.get('reasoning', 'Без дополнительных комментариев.')
        ai_summary_text = f"🤖 <b>Вердикт ИИ:</b>\n- {summary}\n- <b>Обоснование:</b> {reasoning}"
    else: 
        reason = ocr_result.get('message') or ocr_result.get('reason', 'Неизвестная ошибка')
        ai_summary_text = (f"⚠️ <b>AI не уверен или произошла ошибка.</b>\n"
                         f"Причина: {reason}\n"
                         f"Требуется ручная проверка.")

    new_caption = f"{original_caption}\n\n{ai_summary_text}"
    manual_verification_keyboard = inline.get_admin_verification_keyboard(user_id, context)
    
    try:
        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=manual_verification_keyboard
        )
    except TelegramBadRequest: pass


@router.callback_query(F.data.startswith('admin_verify:'), IsAdmin())
async def admin_verification_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    
    try:
        _, action, context, user_id_str = callback.data.split(':')
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        logger.error(f"Error parsing callback data: {callback.data}")
        await callback.message.answer("Ошибка в данных кнопки.")
        return
        
    admin_state = state
    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    original_text = ""
    if callback.message:
        original_text = callback.message.text or callback.message.caption or ""
    
    action_text = ""
    if action == "confirm":
        action_text = f"✅ <b>ПОДТВЕРЖДЕНО</b> (@{callback.from_user.username})"
        if context == "google_profile":
            await user_state.set_state(UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
            prompt_msg = await bot.send_message(user_id, "Профиль прошел проверку. Пришлите скриншот последних отзывов.", reply_markup=inline.get_google_last_reviews_check_keyboard())
            await user_state.update_data(prompt_message_id=prompt_msg.message_id)
        elif context == "google_last_reviews":
            await user_state.set_state(UserState.GOOGLE_REVIEW_READY_TO_CONTINUE)
            await bot.send_message(user_id, "Отзывы прошли проверку. Можете продолжить.", reply_markup=inline.get_google_continue_writing_keyboard())
        elif "yandex_profile" in context:
            await user_state.set_state(UserState.YANDEX_REVIEW_READY_TO_TASK)
            await bot.send_message(user_id, "Профиль Yandex прошел проверку. Можете продолжить.", reply_markup=inline.get_yandex_continue_writing_keyboard())
        elif context == "gmail_device_model":
            responsible_admin = await admin_roles.get_gmail_data_admin()
            if callback.from_user.id != responsible_admin:
                admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
                await callback.message.answer(f"Запрос на выдачу данных отправлен {admin_name}")
                try:
                    user_info = await bot.get_chat(user_id)
                    await send_notification_to_admins(
                        bot,
                        text=f"❗️Пользователь @{user_info.username} (ID: {user_id}) ожидает данные для создания Gmail. Вы назначены ответственным.",
                        task_type="gmail_issue_data"
                    )
                except Exception: pass
            else:
                prompt_msg = await bot.send_message(callback.from_user.id, "✅ Модель подтверждена.\nВведите данные для аккаунта:\nИмя\nФамилия\nПароль\nПочта (без @gmail.com)")
                await admin_state.set_state(AdminState.ENTER_GMAIL_DATA)
                await admin_state.update_data(gmail_user_id=user_id, prompt_message_id=prompt_msg.message_id)
    
    elif action == "warn":
        action_text = f"⚠️ <b>ВЫДАЧА ПРЕДУПРЕЖДЕНИЯ</b> (@{callback.from_user.username})"
        platform = "gmail" if "gmail" in context else context.split('_')[0]
        prompt_msg = await bot.send_message(callback.from_user.id, f"✍️ Отправьте причину предупреждения для {user_id_str}.")
        await admin_state.set_state(AdminState.PROVIDE_WARN_REASON)
        await admin_state.update_data(
            target_user_id=user_id, 
            platform=platform, 
            context=context, 
            prompt_message_id=prompt_msg.message_id,
            original_verification_message_id=callback.message.message_id
        )

    elif action == "reject":
        action_text = f"❌ <b>ОТКЛОНЕН</b> (@{callback.from_user.username})"
        context_map = {"google_profile": "google_profile", "google_last_reviews": "google_last_reviews", "yandex_profile": "yandex_profile", "yandex_profile_screenshot": "yandex_profile", "gmail_device_model": "gmail_device_model"}
        rejection_context = context_map.get(context)
        if rejection_context:
            prompt_msg = await bot.send_message(callback.from_user.id, f"✍️ Отправьте причину отклонения для {user_id_str}.")
            await admin_state.set_state(AdminState.PROVIDE_REJECTION_REASON)
            await admin_state.update_data(
                target_user_id=user_id, 
                rejection_context=rejection_context, 
                prompt_message_id=prompt_msg.message_id,
                original_verification_message_id=callback.message.message_id
            )
        else:
            await bot.send_message(callback.from_user.id, "Ошибка: неизвестный контекст.")
    
    if callback.message:
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=f"{original_text}\n\n{action_text}", reply_markup=None)
            else: await callback.message.edit_text(f"{original_text}\n\n{action_text}", reply_markup=None)
        except TelegramBadRequest: pass

# --- БЛОК УПРАВЛЕНИЯ ТЕКСТОМ ОТЗЫВА ---

@router.callback_query(F.data.startswith('admin_provide_text:'), IsAdmin())
async def admin_start_providing_text(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    
    try:
        _, platform, user_id_str, link_id_str = callback.data.split(':')
        
        if platform == 'google':
            responsible_admin = await admin_roles.get_google_issue_admin()
        elif platform == 'yandex_with_text':
            responsible_admin = await admin_roles.get_yandex_text_issue_admin()
        else:
            await callback.message.answer("Ошибка: неизвестная платформа для выдачи текста.")
            return

        if callback.from_user.id != responsible_admin:
            admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
            await callback.message.answer(f"Эту задачу выполняет {admin_name}")
            return

        state_map = {'google': AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, 'yandex_with_text': AdminState.PROVIDE_YANDEX_REVIEW_TEXT}
        if platform not in state_map: await callback.message.answer("Ошибка платформы."); return
        
        edit_text = f"✍️ Введите текст отзыва для ID: {user_id_str}"
        new_content = f"{(callback.message.caption or callback.message.text)}\n\n{edit_text}"
        
        prompt_msg = None
        if callback.message:
            if callback.message.photo: 
                await callback.message.edit_caption(caption=new_content, reply_markup=None)
            else: 
                prompt_msg = await callback.message.edit_text(new_content, reply_markup=None)

        await state.set_state(state_map[platform])
        await state.update_data(
            target_user_id=int(user_id_str), 
            target_link_id=int(link_id_str), 
            platform=platform,
            prompt_message_id=prompt_msg.message_id if prompt_msg else None
        )
    except Exception as e: logger.warning(f"Error in admin_start_providing_text: {e}")

@router.callback_query(F.data.startswith('admin_ai_generate_start:'), IsAdmin())
async def admin_ai_generate_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer("Ожидаю сценарий...")
    except TelegramBadRequest:
        pass
    
    try:
        _, platform, user_id_str, link_id_str = callback.data.split(':')
        
        if platform == 'google':
            responsible_admin = await admin_roles.get_google_issue_admin()
        elif platform == 'yandex_with_text':
            responsible_admin = await admin_roles.get_yandex_text_issue_admin()
        else:
            await callback.answer("Ошибка: неизвестная платформа для генерации текста.", show_alert=True)
            return
        
        if callback.from_user.id != responsible_admin:
            admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
            await callback.answer(f"Эту задачу выполняет {admin_name}", show_alert=True)
            return

        edit_text = "✍️ Введите короткий сценарий/описание для генерации отзыва:"
        new_content = f"{(callback.message.caption or callback.message.text)}\n\n{edit_text}"
        
        prompt_msg = None
        if callback.message:
            if callback.message.photo: 
                await callback.message.edit_caption(caption=new_content, reply_markup=None)
            else: 
                prompt_msg = await callback.message.edit_text(new_content, reply_markup=None)

        await state.set_state(AdminState.AI_AWAITING_SCENARIO)
        await state.update_data(
            target_user_id=int(user_id_str), 
            target_link_id=int(link_id_str), 
            platform=platform,
            prompt_message_id=prompt_msg.message_id if prompt_msg else None,
            original_message_id=callback.message.message_id 
        )
    except Exception as e: 
        logger.exception(f"Ошибка на старте AI генерации: {e}")
        if callback.message:
            await callback.message.answer("Произошла ошибка на старте генерации.", show_alert=True)

@router.message(AdminState.AI_AWAITING_SCENARIO, IsAdmin())
async def admin_process_ai_scenario(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Сценарий не может быть пустым. Пожалуйста, отправьте текст.")
        return
        
    await delete_previous_messages(message, state)
    data = await state.get_data()
    
    original_message_id = data.get("original_message_id")
    if original_message_id:
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=original_message_id)
        except TelegramBadRequest:
            pass

    status_msg = await message.answer("🤖 Получил сценарий. Генерирую текст, пожалуйста, подождите...")
    
    scenario = message.text
    
    link_id = data.get('target_link_id')
    link = await db_manager.db_get_link_by_id(link_id)
    company_info = link.url if link else "Неизвестная компания"
    
    generated_text = await generate_review_text(
        company_info=company_info,
        scenario=scenario
    )

    await status_msg.delete()

    if "ошибка" in generated_text.lower() or "ai-сервис" in generated_text.lower() or "ai-модель" in generated_text.lower():
        await message.answer(
            f"❌ {generated_text}\n\nПопробуйте снова или напишите вручную.", 
            reply_markup=inline.get_ai_error_keyboard()
        )
        await state.update_data(ai_scenario=scenario)
        await state.set_state(AdminState.AI_AWAITING_MODERATION) 
        return

    moderation_text = (
        "📄 <b>Сгенерированный текст отзыва:</b>\n\n"
        f"<i>{generated_text}</i>\n\n"
        "Выберите следующее действие:"
    )
    
    await message.answer(moderation_text, reply_markup=inline.get_ai_moderation_keyboard())
    
    await state.set_state(AdminState.AI_AWAITING_MODERATION)
    await state.update_data(ai_scenario=scenario, ai_generated_text=generated_text)


@router.callback_query(F.data.startswith('ai_moderation:'), AdminState.AI_AWAITING_MODERATION, IsAdmin())
async def admin_process_ai_moderation(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    await callback.answer()
    action = callback.data.split(':')[1]
    data = await state.get_data()
    
    if action == 'send':
        review_text = data.get('ai_generated_text')
        
        dp_dummy = Dispatcher(storage=state.storage)
        success, response_text = await send_review_text_to_user_logic(
            bot=bot, dp=dp_dummy, scheduler=scheduler,
            user_id=data['target_user_id'], link_id=data['target_link_id'],
            platform=data['platform'], review_text=review_text
        )
        await callback.message.edit_text(f"Текст отправлен пользователю.\nСтатус: {response_text}", reply_markup=None)
        await state.clear()

    elif action == 'regenerate':
        scenario = data.get('ai_scenario')
        
        if not scenario:
            await callback.message.edit_text("Не найден исходный сценарий для повторной генерации. Пожалуйста, начните заново.", reply_markup=None)
            await state.clear()
            return

        link_id = data.get('target_link_id')
        link = await db_manager.db_get_link_by_id(link_id)
        company_info = link.url if link else "Неизвестная компания"

        status_msg = await callback.message.answer("🤖 Повторная генерация...")
        generated_text = await generate_review_text(
            company_info=company_info,
            scenario=scenario,
        )
        await status_msg.delete()

        if "ошибка" in generated_text.lower() or "ai-сервис" in generated_text.lower() or "ai-модель" in generated_text.lower():
            await callback.message.edit_text(
                f"❌ {generated_text}\n\nПопробуйте снова или напишите вручную.", 
                reply_markup=inline.get_ai_error_keyboard()
            )
            return

        new_moderation_text = (
            "📄 <b>Новый сгенерированный текст отзыва:</b>\n\n"
            f"<i>{generated_text}</i>\n\n"
            "Выберите следующее действие:"
        )
        await callback.message.edit_text(new_moderation_text, reply_markup=inline.get_ai_moderation_keyboard())
        await state.update_data(ai_generated_text=generated_text)
    
    elif action == 'manual':
        platform = data['platform']
        state_map = {'google': AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, 'yandex_with_text': AdminState.PROVIDE_YANDEX_REVIEW_TEXT}
        
        prompt_msg = await callback.message.edit_text(
            "Введите текст отзыва вручную. Вы можете скопировать и отредактировать сгенерированный текст выше.",
            reply_markup=inline.get_cancel_inline_keyboard()
        )
        await state.set_state(state_map[platform])
        await state.update_data(prompt_message_id=prompt_msg.message_id)

# --- БЛОК МОДЕРАЦИИ ОТЗЫВОВ ---

@router.callback_query(F.data.startswith("admin_final_approve:"), IsAdmin())
async def admin_final_approve(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    review_id = int(callback.data.split(':')[1])
    
    review = await db_manager.get_review_by_id(review_id)
    if not review:
        await callback.answer("Ошибка: отзыв не найден.", show_alert=True)
        return
    
    platform = review.platform
    responsible_admin = SUPER_ADMIN_ID

    if platform == 'google': responsible_admin = await admin_roles.get_google_final_admin()
    elif platform == 'yandex_with_text': responsible_admin = await admin_roles.get_yandex_text_final_admin()
    elif platform == 'yandex_without_text': responsible_admin = await admin_roles.get_yandex_no_text_final_admin()
        
    if callback.from_user.id != responsible_admin:
        admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
        await callback.answer(f"Эту проверку выполняет {admin_name}", show_alert=True)
        return

    success, message_text = await approve_review_to_hold_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        await callback.message.edit_caption(caption=f"{(callback.message.caption or '')}\n\n✅ В <b>ХОЛДЕ</b> (@{callback.from_user.username})", reply_markup=None)

@router.callback_query(F.data.startswith('admin_final_reject:'), IsAdmin())
async def admin_final_reject_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    
    review = await db_manager.get_review_by_id(review_id)
    if not review:
        await callback.answer("Ошибка: отзыв не найден.", show_alert=True)
        return
        
    platform = review.platform
    responsible_admin = SUPER_ADMIN_ID

    if platform == 'google': responsible_admin = await admin_roles.get_google_final_admin()
    elif platform == 'yandex_with_text': responsible_admin = await admin_roles.get_yandex_text_final_admin()
    elif platform == 'yandex_without_text': responsible_admin = await admin_roles.get_yandex_no_text_final_admin()
        
    if callback.from_user.id != responsible_admin:
        admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
        await callback.answer(f"Эту проверку выполняет {admin_name}", show_alert=True)
        return

    await state.set_state(AdminState.PROVIDE_FINAL_REJECTION_REASON)
    await state.update_data(review_id_to_reject=review_id)
    
    prompt_msg = await callback.message.answer(
        f"✍️ Введите причину отклонения для отзыва ID: {review_id}",
        reply_markup=inline.get_cancel_inline_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer("Ожидание причины...")

@router.message(AdminState.PROVIDE_FINAL_REJECTION_REASON, IsAdmin())
async def admin_final_reject_process_reason(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    if not message.text:
        await message.answer("Причина не может быть пустой.")
        return

    await delete_previous_messages(message, state)
    data = await state.get_data()
    review_id = data.get('review_id_to_reject')
    reason = message.text

    success, message_text = await reject_initial_review_logic(review_id, bot, scheduler, reason=reason)
    
    admin_info_msg = await message.answer(message_text)
    asyncio.create_task(schedule_message_deletion(admin_info_msg, Durations.DELETE_ADMIN_REPLY_DELAY))

    try:
        review = await db_manager.get_review_by_id(review_id)
        if review and review.admin_message_id:
            responsible_admin = SUPER_ADMIN_ID
            if review.platform == 'google': responsible_admin = await admin_roles.get_google_final_admin()
            elif review.platform == 'yandex_with_text': responsible_admin = await admin_roles.get_yandex_text_final_admin()
            elif review.platform == 'yandex_without_text': responsible_admin = await admin_roles.get_yandex_no_text_final_admin()

            original_message = await bot.edit_message_caption(
                chat_id=responsible_admin,
                message_id=review.admin_message_id,
                caption=f"{(review.review_text or '')}\n\n❌ <b>ОТКЛОНЕН</b> (@{message.from_user.username})\nПричина: {reason}",
                reply_markup=None
            )
    except Exception as e:
        logger.warning(f"Не удалось отредактировать исходное сообщение об отклонении отзыва {review_id}: {e}")

    await state.clear()


@router.callback_query(F.data.startswith('final_verify_approve:'), IsAdmin())
async def final_verify_approve_handler(callback: CallbackQuery, bot: Bot):
    """Админ одобряет отзыв после холда и выплачивает награду."""
    review_id = int(callback.data.split(':')[1])
    
    responsible_admin = await admin_roles.get_other_hold_admin()
    if callback.from_user.id != responsible_admin:
        admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
        await callback.answer(f"Эту проверку выполняет {admin_name}", show_alert=True)
        return

    success, message_text = await approve_final_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        new_caption = (callback.message.caption or "") + f"\n\n✅ <b>ОДОБРЕН И ВЫПЛАЧЕН</b> (@{callback.from_user.username})"
        try:
            if callback.message.media_group_id:
                await bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    caption=new_caption,
                    reply_markup=None
                )
            else: 
                await callback.message.edit_caption(caption=new_caption, reply_markup=None)
        except TelegramBadRequest:
            pass

@router.callback_query(F.data.startswith('final_verify_reject:'), IsAdmin())
async def final_verify_reject_handler(callback: CallbackQuery, bot: Bot):
    """Админ отклоняет отзыв после холда."""
    review_id = int(callback.data.split(':')[1])
    
    responsible_admin = await admin_roles.get_other_hold_admin()
    if callback.from_user.id != responsible_admin:
        admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
        await callback.answer(f"Эту проверку выполняет {admin_name}", show_alert=True)
        return

    success, message_text = await reject_final_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        new_caption = (callback.message.caption or "") + f"\n\n❌ <b>ОТКЛОНЕН</b> (@{callback.from_user.username})"
        try:
            if callback.message.media_group_id:
                await bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    caption=new_caption,
                    reply_markup=None
                )
            else:
                await callback.message.edit_caption(caption=new_caption, reply_markup=None)
        except TelegramBadRequest:
            pass
            
# --- БЛОК ВЫВОДА СРЕДСТВ ---

@router.callback_query(F.data.startswith("admin_withdraw_approve:"), IsAdmin())
async def admin_approve_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await approve_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        try:
            new_text = (callback.message.text or "") + f"\n\n<i>[ ✅ <b>ВЫПЛАЧЕНО</b> Администратором @{callback.from_user.username} ]</i>"
            await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit withdrawal message in channel: {e}")

@router.callback_query(F.data.startswith("admin_withdraw_reject:"), IsAdmin())
async def admin_reject_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await reject_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        try:
            new_text = (callback.message.text or "") + f"\n\n<i>[ ❌ <b>ОТКЛОНЕНО</b> Администратором @{callback.from_user.username} ]</i>"
            await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit withdrawal message in channel: {e}")

# --- ПРОЧИЕ АДМИН-КОМАНДЫ ---

@router.message(Command("reset_cooldown"), IsAdmin())
async def reset_cooldown_handler(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используйте: <code>/reset_cooldown ID_или_@username</code>"); return
    user_id = await db_manager.find_user_by_identifier(args[1])
    if not user_id:
        await message.answer(f"❌ Пользователь <code>{args[1]}</code> не найден."); return
    if await db_manager.reset_user_cooldowns(user_id):
        user = await db_manager.get_user(user_id)
        username = f"@{user.username}" if user.username else f"ID: {user_id}"
        await message.answer(f"✅ Кулдауны для <i>{username}</i> сброшены.")
    else: await message.answer(f"❌ Ошибка при сбросе кулдаунов для <code>{args[1]}</code>.")

@router.message(Command("viewhold"), IsAdmin())
async def viewhold_handler(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /viewhold ID_пользователя_или_@username")
        return
    identifier = args[1]
    response_text = await get_user_hold_info_logic(identifier)
    await message.answer(response_text)

@router.message(Command("fine"), IsAdmin())
async def fine_user_start(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    prompt_msg = await message.answer("Введите ID или @username пользователя для штрафа.", reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.FINE_USER_ID)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(Command("create_promo"), IsSuperAdmin())
async def create_promo_start(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    prompt_msg = await message.answer("Введите название для нового промокода (например, <code>NEWYEAR2025</code>). Оно должно быть уникальным.",
                         reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.PROMO_CODE_NAME)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(Command("ban"), IsSuperAdmin())
async def ban_user_start(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await state.clear()
    
    args = message.text.split()
    if len(args) < 2:
        msg = await message.answer("Использование: <code>/ban ID_пользователя_или_@username</code>")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return
    
    identifier = args[1]
    user_id_to_ban = await db_manager.find_user_by_identifier(identifier)

    if not user_id_to_ban:
        msg = await message.answer(f"❌ Пользователь <code>{identifier}</code> не найден.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return
        
    user_to_ban = await db_manager.get_user(user_id_to_ban)
    if user_to_ban.is_banned:
        msg = await message.answer(f"Пользователь @{user_to_ban.username} (<code>{user_id_to_ban}</code>) уже забанен.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return

    await state.set_state(AdminState.BAN_REASON)
    await state.update_data(user_id_to_ban=user_id_to_ban)
    
    prompt_msg = await message.answer(f"Введите причину бана для пользователя @{user_to_ban.username} (<code>{user_id_to_ban}</code>).", reply_markup=inline.get_cancel_inline_keyboard())
    await state.update_data(prompt_message_id=prompt_msg.message_id)


# --- НОВЫЙ БЛОК: СПИСКИ ЗАБАНЕННЫХ И ПРОМОКОДОВ (только для Главного Админа) ---

@router.message(Command("banlist"), IsSuperAdmin())
async def show_ban_list(message: Message, state: FSMContext):
    await message.delete()
    await state.set_state(AdminState.BAN_LIST_VIEW)
    await show_banned_users_page(message, state, 1)

async def show_banned_users_page(message_or_callback: Message | CallbackQuery, state: FSMContext, page: int):
    users = await db_manager.get_banned_users(page=page)
    total_users_count = await db_manager.get_banned_users_count()
    users_per_page = 6
    total_pages = ceil(total_users_count / users_per_page) if total_users_count > 0 else 1

    text = await format_banned_user_page(users, page, total_pages)
    
    keyboard = inline.get_pagination_keyboard("banlist", page, total_pages)
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=keyboard)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("banlist:page:"), AdminState.BAN_LIST_VIEW, IsSuperAdmin())
async def banlist_pagination_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[2])
    await show_banned_users_page(callback, state, page)


@router.message(Command("promolist"), IsSuperAdmin())
async def show_promo_list(message: Message, state: FSMContext):
    await message.delete()
    await state.set_state(AdminState.PROMO_LIST_VIEW)
    await show_promo_codes_page(message, state, 1)

async def show_promo_codes_page(message_or_callback: Message | CallbackQuery, state: FSMContext, page: int):
    promos = await db_manager.get_all_promo_codes(page=page)
    total_promos_count = await db_manager.get_promo_codes_count()
    promos_per_page = 6
    total_pages = ceil(total_promos_count / promos_per_page) if total_promos_count > 0 else 1

    text = await format_promo_code_page(promos, page, total_pages)
    
    keyboard = inline.get_promo_list_keyboard(page, total_pages)
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=keyboard)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("promolist:page:"), AdminState.PROMO_LIST_VIEW, IsSuperAdmin())
async def promolist_pagination_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[2])
    await show_promo_codes_page(callback, state, page)

@router.callback_query(F.data == "promolist:delete_start", AdminState.PROMO_LIST_VIEW, IsSuperAdmin())
async def promo_delete_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminState.PROMO_DELETE_CONFIRM)
    prompt_msg = await callback.message.answer(
        "Введите ID или название промокода, который хотите удалить.",
        reply_markup=inline.get_cancel_inline_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AdminState.PROMO_DELETE_CONFIRM, IsSuperAdmin())
async def process_delete_promo_id(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    
    identifier = message.text.strip()
    promo_to_delete = None
    
    if identifier.isdigit():
        promo_id = int(identifier)
        # ИСПРАВЛЕНИЕ: Нужно искать по ID, а не по коду
        promo_to_delete = await db_manager.get_promo_by_id(promo_id) 
    else:
        promo_to_delete = await db_manager.get_promo_by_code(identifier)

    if not promo_to_delete:
        await message.answer(f"❌ Промокод '{identifier}' не найден.")
        await state.set_state(AdminState.PROMO_LIST_VIEW)
        await show_promo_codes_page(message, state, 1)
        return

    success = await db_manager.delete_promo_code(promo_to_delete.id)
    if success:
        await message.answer(f"✅ Промокод `{promo_to_delete.code}` и все его активации были успешно удалены.")
    else:
        await message.answer(f"❌ Произошла ошибка при удалении промокода `{promo_to_delete.code}`.")
        
    await state.set_state(AdminState.PROMO_LIST_VIEW)
    await show_promo_codes_page(message, state, 1)

# --- НОВЫЙ БЛОК: УПРАВЛЕНИЕ АМНИСТИЯМИ ---

@router.message(Command("amnesty"), IsSuperAdmin())
async def show_amnesty_list(message: Message, state: FSMContext):
    await message.delete()
    await state.set_state(AdminState.AMNESTY_LIST_VIEW)
    await show_amnesty_page(message, state, 1)

async def show_amnesty_page(message_or_callback: Message | CallbackQuery, state: FSMContext, page: int):
    requests = await db_manager.get_pending_unban_requests(page=page)
    total_requests_count = await db_manager.get_pending_unban_requests_count()
    requests_per_page = 5 # Меньше, т.к. текста больше
    total_pages = ceil(total_requests_count / requests_per_page) if total_requests_count > 0 else 1

    text = await get_unban_requests_page(requests, page, total_pages)
    
    keyboard = inline.get_amnesty_keyboard(requests, page, total_pages)
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=keyboard)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("amnesty:page:"), AdminState.AMNESTY_LIST_VIEW, IsSuperAdmin())
async def amnesty_pagination_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[2])
    await show_amnesty_page(callback, state, page)

@router.callback_query(F.data.startswith("amnesty:action:"), AdminState.AMNESTY_LIST_VIEW, IsSuperAdmin())
async def amnesty_action_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, action, request_id_str = callback.data.split(":")
    request_id = int(request_id_str)
    admin_id = callback.from_user.id

    success, message_text = await process_unban_request_logic(bot, request_id, action, admin_id)
    
    await callback.answer(message_text, show_alert=True)
    
    # Обновляем список, чтобы убрать обработанный запрос
    await show_amnesty_page(callback, state, 1)


# --- НОВЫЙ БЛОК: УПРАВЛЕНИЕ НАГРАДАМИ СТАТИСТИКИ ---

async def show_reward_settings_menu(message_or_callback: Message | CallbackQuery, state: FSMContext):
    """Отображает меню настроек наград."""
    await state.set_state(AdminState.REWARD_SETTINGS_MENU)
    
    settings = await db_manager.get_reward_settings()
    timer_hours_str = await db_manager.get_system_setting("reward_timer_hours")
    timer_hours = int(timer_hours_str) if timer_hours_str and timer_hours_str.isdigit() else 24
    
    text = "⚙️ <b>Управление наградами для топа статистики</b>\n\n<b>Текущие настройки:</b>\n"
    if not settings:
        text += "Призовые места не настроены.\n"
    else:
        for setting in settings:
            text += f" • {setting.place}-е место: {setting.reward_amount} ⭐\n"
    
    text += f"\n<b>Период выдачи:</b> раз в {timer_hours} часов."
    
    markup = inline.get_reward_settings_menu_keyboard(timer_hours)

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=markup)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=markup)


@router.message(Command("stat_rewards"), IsSuperAdmin())
async def stat_rewards_handler(message: Message, state: FSMContext):
    await show_reward_settings_menu(message, state)


@router.callback_query(F.data == "reward_setting:set_places", AdminState.REWARD_SETTINGS_MENU, IsSuperAdmin())
async def ask_places_count(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminState.REWARD_SET_PLACES_COUNT)
    prompt_msg = await callback.message.edit_text(
        "Введите новое количество призовых мест (например, 3). Это действие сбросит текущие суммы наград.",
        reply_markup=inline.get_cancel_inline_keyboard("go_main_menu")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AdminState.REWARD_SET_PLACES_COUNT, F.text, IsSuperAdmin())
async def process_places_count(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    if not message.text.isdigit() or not (0 < int(message.text) <= 10):
        await message.answer("❌ Введите целое число от 1 до 10.")
        return
    
    count = int(message.text)
    new_settings = [{"place": i, "reward_amount": 0.0} for i in range(1, count + 1)]
    await db_manager.update_reward_settings(new_settings)
    
    await message.answer(f"✅ Количество призовых мест установлено на {count}. Теперь настройте суммы наград.")
    await show_reward_settings_menu(message, state)


@router.callback_query(F.data == "reward_setting:set_amounts", AdminState.REWARD_SETTINGS_MENU, IsSuperAdmin())
async def ask_reward_amount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminState.REWARD_SET_AMOUNT_FOR_PLACE)
    prompt_msg = await callback.message.edit_text(
        "Введите данные для изменения наград. Каждая настройка с новой строки в формате: <code>МЕСТО СУММА</code>\n\nНапример:\n<code>1 50.5</code>\n<code>2 30</code>\n<code>3 15.0</code>",
        reply_markup=inline.get_cancel_inline_keyboard("go_main_menu")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AdminState.REWARD_SET_AMOUNT_FOR_PLACE, F.text, IsSuperAdmin())
async def process_reward_amount(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    
    lines = message.text.strip().split('\n')
    updates = {}
    errors = []

    for i, line in enumerate(lines, 1):
        try:
            place_str, amount_str = line.split()
            place = int(place_str)
            amount = float(amount_str.replace(',', '.'))
            if place <= 0 or amount < 0: raise ValueError
            updates[place] = amount
        except (ValueError, TypeError):
            errors.append(f"Строка {i}: Неверный формат. Используйте: `МЕСТО СУММА`.")

    if errors:
        await message.answer("❌ Обнаружены ошибки:\n\n" + "\n".join(errors))
        return

    settings = await db_manager.get_reward_settings()
    settings_dict = {s.place: s for s in settings}
    
    for place, amount in updates.items():
        if place not in settings_dict:
            await message.answer(f"❌ Призовое место №{place} не настроено. Сначала установите количество призовых мест.")
            return
        settings_dict[place].reward_amount = amount

    new_settings_list = [{"place": p, "reward_amount": s.reward_amount} for p, s in settings_dict.items()]
    await db_manager.update_reward_settings(new_settings_list)

    await message.answer(f"✅ Награды успешно обновлены.")
    await show_reward_settings_menu(message, state)


@router.callback_query(F.data == "reward_setting:set_timer", AdminState.REWARD_SETTINGS_MENU, IsSuperAdmin())
async def ask_timer_duration(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminState.REWARD_SET_TIMER)
    prompt_msg = await callback.message.edit_text(
        "Введите интервал автоматической выдачи наград в часах (например, 24).",
        reply_markup=inline.get_cancel_inline_keyboard("go_main_menu")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AdminState.REWARD_SET_TIMER, F.text, IsSuperAdmin())
async def process_timer_duration(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите целое положительное число.")
        return
    
    hours = message.text
    await db_manager.set_system_setting("reward_timer_hours", hours)
    await db_manager.set_system_setting("next_reward_timestamp", "0")
    
    await message.answer(f"✅ Интервал выдачи наград установлен на {hours} часов. Изменения вступят в силу после следующего цикла.")
    await show_reward_settings_menu(message, state)
    

# --- Обработчики состояний (FSM) ---

@router.message(AdminState.PROVIDE_WARN_REASON, IsAdmin())
async def process_warning_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text: return
    await delete_previous_messages(message, state)
    admin_data = await state.get_data()
    user_id, platform, context = admin_data.get("target_user_id"), admin_data.get("platform"), admin_data.get("context")
    if not all([user_id, platform, context]):
        await message.answer("Ошибка: не найдены данные. Состояние сброшено."); await state.clear(); return
    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    response = await process_warning_reason_logic(bot, user_id, platform, message.text, user_state, context)
    await message.answer(response)
    
    original_message_id = admin_data.get("original_verification_message_id")
    if original_message_id:
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=original_message_id)
        except TelegramBadRequest:
            pass
    
    await state.clear()

@router.message(AdminState.PROVIDE_REJECTION_REASON, IsAdmin())
async def process_rejection_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text: return
    await delete_previous_messages(message, state)
    admin_data = await state.get_data()
    user_id, context = admin_data.get("target_user_id"), admin_data.get("rejection_context")
    if not user_id:
        await message.answer("Ошибка: не найден ID. Состояние сброшено."); await state.clear(); return
    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    response = await process_rejection_reason_logic(bot, user_id, message.text, context, user_state)
    await message.answer(response)

    original_message_id = admin_data.get("original_verification_message_id")
    if original_message_id:
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=original_message_id)
        except TelegramBadRequest:
            pass

    await state.clear()

@router.message(AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, IsAdmin())
@router.message(AdminState.PROVIDE_YANDEX_REVIEW_TEXT, IsAdmin())
async def admin_process_review_text(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    if not message.text: return
    await delete_previous_messages(message, state)
    data = await state.get_data()
    dp_dummy = Dispatcher(storage=state.storage)
    success, response_text = await send_review_text_to_user_logic(
        bot=bot, dp=dp_dummy, scheduler=scheduler,
        user_id=data['target_user_id'], link_id=data['target_link_id'],
        platform=data['platform'], review_text=message.text
    )
    await message.answer(response_text)
    if success: await state.clear()

@router.message(AdminState.FINE_USER_ID, IsAdmin())
async def fine_user_get_id(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    user_id = await db_manager.find_user_by_identifier(message.text)
    if not user_id:
        prompt_msg = await message.answer(f"❌ Пользователь <code>{message.text}</code> не найден.", reply_markup=inline.get_cancel_inline_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(target_user_id=user_id)
    prompt_msg = await message.answer(f"Введите сумму штрафа (например, 10).", reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.FINE_AMOUNT)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.FINE_AMOUNT, IsAdmin())
async def fine_user_get_amount(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
    except (ValueError, TypeError):
        prompt_msg = await message.answer("❌ Введите положительное число.", reply_markup=inline.get_cancel_inline_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(fine_amount=amount)
    prompt_msg = await message.answer("Введите причину штрафа.", reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.FINE_REASON)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.FINE_REASON, IsAdmin())
async def fine_user_get_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text: return
    await delete_previous_messages(message, state)
    data = await state.get_data()
    result_text = await apply_fine_to_user(data.get("target_user_id"), message.from_user.id, data.get("fine_amount"), message.text, bot)
    await message.answer(result_text)
    await state.clear()

@router.message(AdminState.PROMO_CODE_NAME, IsSuperAdmin())
async def promo_name_entered(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    promo_name = message.text.strip().upper()
    existing_promo = await db_manager.get_promo_by_code(promo_name)
    if existing_promo:
        prompt_msg = await message.answer("❌ Промокод с таким названием уже существует. Пожалуйста, придумайте другое название.", reply_markup=inline.get_cancel_inline_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(promo_name=promo_name)
    prompt_msg = await message.answer("Отлично. Теперь введите количество активаций.", reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.PROMO_USES)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.PROMO_USES, IsSuperAdmin())
async def promo_uses_entered(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    if not message.text.isdigit():
        prompt_msg = await message.answer("❌ Пожалуйста, введите целое число.", reply_markup=inline.get_cancel_inline_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    uses = int(message.text)
    if uses <= 0:
        prompt_msg = await message.answer("❌ Количество активаций должно быть больше нуля.", reply_markup=inline.get_cancel_inline_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(promo_uses=uses)
    prompt_msg = await message.answer(f"Принято. Количество активаций: {uses}.\n\nТеперь введите сумму вознаграждения в звездах (например, <code>25</code>).", reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.PROMO_REWARD)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.PROMO_REWARD, IsSuperAdmin())
async def promo_reward_entered(message: Message, state: FSMContext):
    if not message.text: return
    await delete_previous_messages(message, state)
    try:
        reward = float(message.text.replace(',', '.'))
        if reward <= 0: raise ValueError
    except (ValueError, TypeError):
        prompt_msg = await message.answer("❌ Пожалуйста, введите положительное число (можно дробное, например <code>10.5</code>).", reply_markup=inline.get_cancel_inline_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await state.update_data(promo_reward=reward)
    await message.answer(f"Принято. Награда: {reward} ⭐.\n\nТеперь выберите обязательное условие для получения награды.", reply_markup=inline.get_promo_condition_keyboard())
    await state.set_state(AdminState.PROMO_CONDITION)

@router.callback_query(F.data.startswith("promo_cond:"), AdminState.PROMO_CONDITION, IsSuperAdmin())
async def promo_condition_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    condition = callback.data.split(":")[1]
    data = await state.get_data()
    new_promo = await db_manager.create_promo_code(
        code=data['promo_name'], total_uses=data['promo_uses'],
        reward=data['promo_reward'], condition=condition
    )
    if new_promo and callback.message:
        await callback.message.edit_text(f"✅ Промокод <code>{new_promo.code}</code> успешно создан!")
    elif callback.message:
        await callback.message.edit_text("❌ Произошла ошибка при создании промокода.")
    await state.clear()

@router.message(AdminState.BAN_REASON, IsSuperAdmin())
async def ban_user_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Причина не может быть пустой. Введите причину текстом.")
        return
        
    await delete_previous_messages(message, state)
    data = await state.get_data()
    user_id_to_ban = data.get("user_id_to_ban")
    ban_reason = message.text

    success = await db_manager.ban_user(user_id_to_ban, ban_reason)
    if not success:
        await message.answer("❌ Произошла при бане пользователя.")
        await state.clear()
       