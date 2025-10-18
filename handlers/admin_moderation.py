# file: handlers/admin_moderation.py

import asyncio
import logging
from math import ceil
from typing import Union
import random

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Durations, Limits, SUPER_ADMIN_ID
from database import db_manager
from keyboards import inline, reply
from logic import (admin_logic, admin_roles, internship_logic)
from logic.ai_helper import generate_review_text
from logic.notification_logic import notify_subscribers
from logic.notification_manager import send_notification_to_admins
from logic.ocr_helper import analyze_screenshot
from references import reference_manager
from states.user_states import AdminState, UserState
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


# --- БЛОК: УПРАВЛЕНИЕ ССЫЛКАМИ (НОВЫЙ FSM) ---

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
            f"Управление ссылками для платформы: **{platform_name}**",
            reply_markup=inline.get_admin_platform_refs_keyboard(platform)
        )

# --- Начало FSM добавления ссылок ---
@router.callback_query(F.data.startswith("admin_refs:add:"), IsSuperAdmin())
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(':')[2]
    link_type_data = callback.data.split(':')[3]
    
    await state.update_data(
        platform_for_links=platform,
        is_fast_track_for_links="fast" in link_type_data,
        requires_photo_for_links="photo" in link_type_data
    )
    
    await state.set_state(AdminState.waiting_for_reward_amount)
    prompt_msg = await callback.message.edit_text(
        "**Шаг 1/4:** Введите сумму награды в звездах за выполнение отзыва по этим ссылкам (например, 15 или 25.5).",
        reply_markup=inline.get_cancel_inline_keyboard(f"admin_refs:select_platform:{platform}")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()


@router.message(AdminState.waiting_for_reward_amount, IsSuperAdmin())
async def admin_add_link_reward(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    try:
        reward = float(message.text.replace(",", "."))
        if reward < 0: raise ValueError
    except ValueError:
        prompt_msg = await message.answer("❌ Некорректная сумма. Введите положительное число.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await state.update_data(reward_amount_for_links=reward)
    await state.set_state(AdminState.waiting_for_gender_requirement)
    prompt_msg = await message.answer(
        "**Шаг 2/4:** Укажите гендерное требование для этих ссылок:",
        reply_markup=inline.get_gender_requirement_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data.startswith("gender_"), AdminState.waiting_for_gender_requirement)
async def admin_add_link_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split("_")[1]
    await state.update_data(gender_requirement_for_links=gender)
    
    await state.set_state(AdminState.waiting_for_campaign_tag)
    prompt_msg = await callback.message.edit_text(
        "**Шаг 3/4 (необязательно):** Хотите добавить тег кампании для этих ссылок? (Например, #кафе_ромашка). Это поможет отслеживать статистику. Введите тег или нажмите 'Пропустить'.",
        reply_markup=inline.get_campaign_tag_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "skip_campaign_tag", AdminState.waiting_for_campaign_tag)
async def admin_skip_campaign_tag(callback: CallbackQuery, state: FSMContext):
    await state.update_data(campaign_tag_for_links=None)
    await state.set_state(AdminState.waiting_for_links)
    prompt_msg = await callback.message.edit_text(
        "**Шаг 4/4:** Отправьте URL-ссылки. Каждая ссылка с новой строки.",
        reply_markup=inline.get_cancel_inline_keyboard(f"admin_refs:select_platform:{(await state.get_data())['platform_for_links']}")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()

@router.message(AdminState.waiting_for_campaign_tag, IsSuperAdmin())
async def admin_add_link_campaign(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    await state.update_data(campaign_tag_for_links=message.text.strip())
    
    await state.set_state(AdminState.waiting_for_links)
    prompt_msg = await message.answer(
        "**Шаг 4/4:** Отправьте URL-ссылки. Каждая ссылка с новой строки.",
        reply_markup=inline.get_cancel_inline_keyboard(f"admin_refs:select_platform:{(await state.get_data())['platform_for_links']}")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.waiting_for_links, F.text, IsSuperAdmin())
async def admin_add_links_handler(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await delete_previous_messages(message, state)

    platform = data.get("platform_for_links")
    reward = data.get("reward_amount_for_links")
    gender = data.get("gender_requirement_for_links")
    campaign = data.get("campaign_tag_for_links")
    is_fast = data.get("is_fast_track_for_links")
    requires_photo = data.get("requires_photo_for_links")

    try:
        result_text = await admin_logic.process_add_links_logic(
            links_text=message.text, 
            platform=platform,
            is_fast_track=is_fast,
            requires_photo=requires_photo,
            reward_amount=reward,
            gender_requirement=gender,
            campaign_tag=campaign
        )
        await message.answer(result_text, reply_markup=inline.get_back_to_platform_refs_keyboard(platform))
        
        await notify_subscribers(platform, gender, bot)

    except Exception as e:
        logger.exception(f"Критическая ошибка (FSM) при добавлении ссылок: {e}")
        await message.answer("❌ Произошла критическая ошибка. Обратитесь к логам.", reply_markup=inline.get_back_to_platform_refs_keyboard(platform))
    finally:
        await state.clear()


@router.callback_query(F.data == "admin_refs:back_to_selection", IsSuperAdmin())
async def admin_back_to_platform_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())


@router.callback_query(F.data.startswith("admin_refs:stats:"), IsSuperAdmin())
async def admin_view_refs_stats(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Загружаю...", show_alert=False)
    platform = callback.data.split(':')[2]
    await state.clear()
    stats = await db_manager.db_get_link_stats(platform)
    
    text = (f"📊 Статистика по *{platform}*:\n\n"
            f"Всего: {stats.get('total', 0)}\n"
            f"🟢 Доступно: {stats.get('available', 0)}\n"
            f"🟡 В работе: {stats.get('assigned', 0)}\n"
            f"🔴 Использовано: {stats.get('used', 0)}\n"
            f"⚫ Просрочено: {stats.get('expired', 0)}")
            
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_back_to_platform_refs_keyboard(platform))


# --- ОБНОВЛЕННЫЙ БЛОК ПРОСМОТРА СПИСКА ССЫЛОК С ФИЛЬТРАМИ ---

async def show_links_page(callback: CallbackQuery, state: FSMContext, platform: str, page: int):
    """Отображает конкретную страницу списка ссылок с учетом всех фильтров из state."""
    data = await state.get_data()
    filter_type = data.get("link_list_filter_type", "all")
    gender_filter = data.get("link_list_gender_filter")
    reward_filter = data.get("link_list_reward_filter")
    sort_by_tag = data.get("link_list_sort_by_tag", False)

    total_links, links_on_page = await db_manager.db_get_paginated_references(
        platform, page, Limits.LINKS_PER_PAGE, filter_type, gender_filter, reward_filter, sort_by_tag
    )
    total_pages = ceil(total_links / Limits.LINKS_PER_PAGE) if total_links > 0 else 1
    
    page_text = admin_logic.get_paginated_links_text(links_on_page, page, total_pages, platform, filter_type)
    keyboard = inline.get_link_list_control_keyboard(platform, page, total_pages, filter_type, reward_filter, gender_filter, sort_by_tag)
    
    if callback.message:
        await callback.message.edit_text(page_text, reply_markup=keyboard, disable_web_page_preview=True)

@router.callback_query(F.data.startswith("admin_refs:list"), IsSuperAdmin())
async def admin_view_refs_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(':')
    platform = parts[2]
    filter_type = parts[3] if len(parts) > 3 else "all"
    
    await state.set_state(AdminState.LINK_LIST_VIEW)
    # При смене типа сбрасываем остальные фильтры
    await state.update_data(
        link_list_platform=platform,
        link_list_filter_type=filter_type,
        link_list_gender_filter=None,
        link_list_reward_filter=None,
        link_list_sort_by_tag=False
    )
    await show_links_page(callback, state, platform, 1)

@router.callback_query(F.data.startswith("links_page:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def link_list_paginator(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    _, platform, page_str = callback.data.split(":")
    await show_links_page(callback, state, platform, int(page_str))

@router.callback_query(F.data.startswith("admin_refs:filter_gender:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def filter_by_gender_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[-1]
    await callback.message.edit_reply_markup(reply_markup=inline.get_gender_filter_keyboard(platform))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_refs:set_gender:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def set_gender_filter(callback: CallbackQuery, state: FSMContext):
    _, _, gender, platform = callback.data.split(":")
    await state.update_data(link_list_gender_filter=gender)
    await show_links_page(callback, state, platform, 1)

@router.callback_query(F.data.startswith("admin_refs:filter_reward:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def filter_by_reward_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[-1]
    await state.set_state(AdminState.waiting_for_reward_filter_amount)
    prompt_msg = await callback.message.edit_text(
        "Введите точную сумму награды для фильтрации (например, 15.0):",
        reply_markup=inline.get_reward_filter_keyboard(platform)
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.waiting_for_reward_filter_amount, IsSuperAdmin())
async def set_reward_filter(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")

    try:
        reward = float(message.text.replace(",", "."))
    except ValueError:
        msg = await message.answer("Неверный формат. Введите число.")
        await message.delete()
        await asyncio.sleep(3)
        await msg.delete()
        return

    platform = data.get("link_list_platform")
    await state.update_data(link_list_reward_filter=reward)
    await state.set_state(AdminState.LINK_LIST_VIEW)
    
    await message.delete()

    # Имитируем callback, чтобы обновить список, редактируя исходное сообщение
    if prompt_id:
        dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=Message(message_id=prompt_id, chat=message.chat))
        await show_links_page(dummy_callback, state, platform, 1)


@router.callback_query(F.data.startswith("admin_refs:toggle_sort:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def toggle_tag_sort(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[-1]
    data = await state.get_data()
    current_sort = data.get("link_list_sort_by_tag", False)
    await state.update_data(link_list_sort_by_tag=not current_sort)
    await show_links_page(callback, state, platform, 1)

@router.callback_query(F.data.startswith("admin_refs:reset_filters:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def reset_all_filters(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[-1]
    await state.update_data(link_list_gender_filter=None, link_list_reward_filter=None)
    await show_links_page(callback, state, platform, 1)

# --- Остальные действия со ссылками (удаление, возврат) ---

@router.callback_query(F.data.startswith("admin_refs:delete_start:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def admin_delete_ref_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(':')[2]
    
    links_count = await db_manager.db_get_links_count(platform)
    if links_count == 0:
        await callback.answer("База ссылок для этой платформы пуста. Нечего удалять.", show_alert=True)
        return
        
    await callback.answer()
    await state.set_state(AdminState.DELETE_LINK_ID)
    await state.update_data(platform_for_deletion=platform)
    if callback.message:
        cancel_button = inline.get_cancel_inline_keyboard(f"admin_refs:list:{platform}:all")
        prompt_msg = await callback.message.edit_text(
            "Введите ID ссылок, которые хотите удалить.\n"
            "Можно ввести несколько ID через пробел или запятую.", 
            reply_markup=cancel_button
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.DELETE_LINK_ID, IsSuperAdmin())
async def admin_process_delete_ref_id(message: Message, state: FSMContext, bot: Bot):
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
    
    temp_message = await message.answer(summary_text)
    await state.clear()
    
    dummy_callback_query = CallbackQuery(
        id=str(message.message_id), from_user=message.from_user, chat_instance="dummy", 
        message=temp_message, 
        data=f"admin_refs:list:{platform}:all"
    )
    await admin_view_refs_list(callback=dummy_callback_query, state=state)

@router.callback_query(F.data.startswith("admin_refs:return_start:"), AdminState.LINK_LIST_VIEW, IsSuperAdmin())
async def admin_return_ref_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса возврата ссылки в 'available'."""
    platform = callback.data.split(':')[2]

    links_count = await db_manager.db_get_links_count(platform)
    if links_count == 0:
        await callback.answer("База ссылок для этой платформы пуста. Нечего возвращать.", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AdminState.RETURN_LINK_ID)
    await state.update_data(platform_for_return=platform)
    if callback.message:
        cancel_button = inline.get_cancel_inline_keyboard(f"admin_refs:list:{platform}:all")
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
        data=f"admin_refs:list:{platform}:all",
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
            caption=f"{original_caption}\n\n🤖 **Запущена проверка с помощью ИИ...**",
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
        ai_summary_text = f"🤖 **Вердикт ИИ:**\n- {summary}\n- **Обоснование:** {reasoning}"
    else: 
        reason = ocr_result.get('message') or ocr_result.get('reason', 'Неизвестная ошибка')
        ai_summary_text = (f"⚠️ **AI не уверен или произошла ошибка.**\n"
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
        action_text = f"✅ **ПОДТВЕРЖДЕНО** (@{callback.from_user.username})"
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
                        bot=bot,
                        text=f"❗️Пользователь @{user_info.username} (ID: {user_id}) ожидает данные для создания Gmail. Вы назначены ответственным.",
                        task_type="gmail_issue_data",
                        scheduler=Dispatcher.get_current().get("scheduler")
                    )
                except Exception: pass
            else:
                prompt_msg = await bot.send_message(callback.from_user.id, "✅ Модель подтверждена.\nВведите данные для аккаунта:\nИмя\nФамилия\nПароль\nПочта (без @gmail.com)")
                await admin_state.set_state(AdminState.ENTER_GMAIL_DATA)
                await admin_state.update_data(gmail_user_id=user_id, prompt_message_id=prompt_msg.message_id)
    
    elif action == "warn":
        action_text = f"⚠️ **ВЫДАЧА ПРЕДУПРЕЖДЕНИЯ** (@{callback.from_user.username})"
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
        action_text = f"❌ **ОТКЛОНЕН** (@{callback.from_user.username})"
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
        _, platform, user_id_str, link_id_str, photo_required = callback.data.split(':')
        
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
        if photo_required == 'true':
            edit_text += "\n\n❗️**ВНИМАНИЕ:** К этому отзыву требуется фото. Отправьте сначала фото, а затем, ответом на него, текст отзыва."

        new_content = f"{(callback.message.caption or callback.message.text)}\n\n{edit_text}"
        
        prompt_msg = None
        if callback.message:
            cancel_kb = inline.get_cancel_inline_keyboard(f"admin_back_to_text_choice:{platform}:{user_id_str}:{link_id_str}:{photo_required}")
            if callback.message.photo: 
                await callback.message.edit_caption(caption=new_content, reply_markup=cancel_kb)
            else: 
                await callback.message.edit_text(new_content, reply_markup=cancel_kb)
        
        await state.set_state(state_map[platform])
        await state.update_data(
            target_user_id=int(user_id_str), 
            target_link_id=int(link_id_str), 
            platform=platform,
            photo_required=(photo_required == 'true'),
            original_message_id=callback.message.message_id
        )
    except Exception as e: logger.warning(f"Error in admin_start_providing_text: {e}")

@router.callback_query(F.data.startswith('admin_ai_generate_start:'), IsAdmin())
async def admin_ai_generate_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
    except TelegramBadRequest: pass
    
    try:
        _, platform, user_id_str, link_id_str, photo_required = callback.data.split(':')
        
        if platform == 'google': responsible_admin = await admin_roles.get_google_issue_admin()
        elif platform == 'yandex_with_text': responsible_admin = await admin_roles.get_yandex_text_issue_admin()
        else: return
        
        if callback.from_user.id != responsible_admin:
            admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
            await callback.answer(f"Эту задачу выполняет {admin_name}", show_alert=True)
            return

        await state.update_data(
            target_user_id=int(user_id_str), 
            target_link_id=int(link_id_str), 
            platform=platform,
            photo_required=(photo_required == 'true'),
            original_message_id=callback.message.message_id
        )
        
        await callback.message.edit_reply_markup(reply_markup=inline.get_manual_text_scenario_keyboard())

    except Exception as e: 
        logger.exception(f"Ошибка на старте AI генерации: {e}")

@router.callback_query(F.data == "input_scenario_manually", IsAdmin())
async def input_scenario_manually(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    edit_text = "✍️ Введите короткий сценарий/описание для генерации отзыва:"
    if data.get('photo_required'):
        edit_text += "\n\n❗️**ВНИМАНИЕ:** К этому отзыву требуется фото. Отправьте сначала фото, а затем, ответом на него, сценарий."

    await callback.message.edit_text(edit_text, reply_markup=inline.get_cancel_inline_keyboard("cancel_action"))
    await state.set_state(AdminState.AI_AWAITING_SCENARIO)

@router.callback_query(F.data == "use_scenario_template", IsAdmin())
async def use_scenario_template(callback: CallbackQuery, state: FSMContext):
    categories = await db_manager.get_all_scenario_categories()
    if not categories:
        await callback.answer("Банк сценариев пуст. Сначала добавьте шаблоны через /scenarios.", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите категорию для шаблона:",
        reply_markup=inline.get_scenario_category_selection_keyboard(categories)
    )

@router.callback_query(F.data.startswith("use_scenario_cat:"), IsAdmin())
async def select_scenario_from_template(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    scenarios = await db_manager.get_ai_scenarios_by_category(category)
    if not scenarios:
        await callback.answer("В этой категории нет сценариев.", show_alert=True)
        return

    random_scenario = random.choice(scenarios)
    await state.update_data(ai_scenario=random_scenario.text)

    await callback.message.edit_text(
        f"Выбран случайный шаблон из категории '{category}':\n\n"
        f"*{random_scenario.text}*\n\n"
        "Использовать этот сценарий для генерации?",
        reply_markup=inline.get_ai_template_use_keyboard()
    )

@router.callback_query(F.data.startswith("ai_template:"), IsAdmin())
async def handle_template_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    data = await state.get_data()
    scenario = data.get('ai_scenario')
    if not scenario:
        await callback.answer("Ошибка: сценарий не найден. Начните заново.", show_alert=True)
        return

    if action == "confirm_use":
        dummy_message = callback.message
        dummy_message.text = scenario
        await admin_process_ai_scenario(dummy_message, state, callback.bot)
    elif action == "edit_text":
        await state.set_state(AdminState.waiting_for_edited_scenario_text)
        await callback.message.edit_text(
            "Отредактируйте текст сценария и отправьте его:",
            reply_markup=inline.get_cancel_inline_keyboard("cancel_action")
        )

@router.message(AdminState.waiting_for_edited_scenario_text, IsAdmin())
async def process_edited_scenario(message: Message, state: FSMContext, bot: Bot):
    await admin_process_ai_scenario(message, state, bot)


@router.callback_query(F.data.startswith("admin_back_to_text_choice:"))
async def back_to_text_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    _, platform, user_id_str, link_id_str, photo_required = callback.data.split(':')
    link = await db_manager.db_get_link_by_id(int(link_id_str))
    
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=inline.get_admin_provide_text_keyboard(platform, int(user_id_str), int(link_id_str), link.requires_photo))
    await callback.answer()


@router.message(AdminState.AI_AWAITING_SCENARIO, IsAdmin())
async def admin_process_ai_scenario(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    attached_photo_id = None
    if data.get('photo_required'):
        if not message.reply_to_message or not message.reply_to_message.photo:
            await message.answer("❌ Ошибка: для этого задания требуется фото. Пожалуйста, отправьте фото, а затем ответом на него - сценарий.")
            return
        attached_photo_id = message.reply_to_message.photo[-1].file_id
        scenario = message.text
    else:
        scenario = message.text

    if not scenario:
        await message.answer("Сценарий не может быть пустым. Пожалуйста, отправьте текст.")
        return
        
    original_message_id = data.get("original_message_id")
    if original_message_id:
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=original_message_id)
        except TelegramBadRequest:
            pass

    status_msg = await message.answer("🤖 Получил сценарий. Генерирую текст, пожалуйста, подождите...")
    
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
        await state.update_data(ai_scenario=scenario, attached_photo_id=attached_photo_id)
        await state.set_state(AdminState.AI_AWAITING_MODERATION) 
        return

    moderation_text = (
        "📄 **Сгенерированный текст отзыва:**\n\n"
        f"*{generated_text}*\n\n"
        "Выберите следующее действие:"
    )
    
    await message.answer(moderation_text, reply_markup=inline.get_ai_moderation_keyboard())
    
    await state.set_state(AdminState.AI_AWAITING_MODERATION)
    await state.update_data(ai_scenario=scenario, ai_generated_text=generated_text, attached_photo_id=attached_photo_id)


@router.callback_query(F.data.startswith('ai_moderation:'), AdminState.AI_AWAITING_MODERATION, IsAdmin())
async def admin_process_ai_moderation(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    await callback.answer()
    action = callback.data.split(':')[1]
    data = await state.get_data()
    
    if action == 'send':
        review_text = data.get('ai_generated_text')
        
        dp_dummy = Dispatcher(storage=state.storage)
        success, response_text = await admin_logic.send_review_text_to_user_logic(
            bot=bot, dp=dp_dummy, scheduler=scheduler,
            user_id=data['target_user_id'], link_id=data['target_link_id'],
            platform=data['platform'], review_text=review_text,
            attached_photo_id=data.get('attached_photo_id')
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
            "📄 **Новый сгенерированный текст отзыва:**\n\n"
            f"*{generated_text}*\n\n"
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

    success, message_text = await admin_logic.approve_review_to_hold_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        await callback.message.edit_caption(caption=f"{(callback.message.caption or '')}\n\n✅ В **ХОЛДЕ** (@{callback.from_user.username})", reply_markup=None)

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

    success, message_text = await admin_logic.reject_initial_review_logic(review_id, bot, scheduler, reason=reason)
    
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
                caption=f"{(review.review_text or '')}\n\n❌ **ОТКЛОНЕН** (@{message.from_user.username})\nПричина: {reason}",
                reply_markup=None
            )
    except Exception as e:
        logger.warning(f"Не удалось отредактировать исходное сообщение об отклонении отзыва {review_id}: {e}")

    await state.clear()


@router.callback_query(F.data.startswith('final_verify_approve:'), IsAdmin())
async def final_verify_approve_handler(callback: CallbackQuery, bot: Bot):
    """Админ одобряет отзыв после холда и выплачивает награду."""
    review_id = int(callback.data.split(':')[1])
    admin_username = callback.from_user.username or "Admin"
    
    review = await db_manager.get_review_by_id(review_id)
    if review and review.user and review.user.is_busy_intern:
        success, message_text = await admin_logic.handle_mentor_verdict(
            review_id=review_id, 
            is_approved_by_mentor=True, 
            reason="Проверка совпала с решением ментора",
            bot=bot,
            admin_username=admin_username
        )
        await callback.answer(message_text, show_alert=True)
        if success and callback.message:
            new_caption = (callback.message.caption or "") + f"\n\n{message_text}"
            try:
                await bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=callback.message.message_id, caption=new_caption, reply_markup=None)
            except TelegramBadRequest: pass
        return

    responsible_admin = await admin_roles.get_other_hold_admin()
    if callback.from_user.id != responsible_admin:
        admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
        await callback.answer(f"Эту проверку выполняет {admin_name}", show_alert=True)
        return

    success, message_text = await admin_logic.approve_final_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        new_caption = (callback.message.caption or "") + f"\n\n✅ **ОДОБРЕН И ВЫПЛАЧЕН** (@{callback.from_user.username})"
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
async def final_verify_reject_handler(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Админ отклоняет отзыв после холда."""
    review_id = int(callback.data.split(':')[1])
    review = await db_manager.get_review_by_id(review_id)
    
    if review and review.user and review.user.is_busy_intern:
        await state.set_state(AdminState.MENTOR_REJECT_REASON)
        await state.update_data(review_id_for_intern_rejection=review_id)
        prompt_msg = await callback.message.answer(
            f"❗️Это была проверка стажера @{review.user.username}.\n"
            f"✍️ **Введите причину отклонения.** Эта причина будет записана в историю ошибок стажера, и ему будет начислен штраф."
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        await callback.answer("Ожидание причины для стажера...")
        return

    responsible_admin = await admin_roles.get_other_hold_admin()
    if callback.from_user.id != responsible_admin:
        admin_name = await admin_roles.get_admin_username(bot, responsible_admin)
        await callback.answer(f"Эту проверку выполняет {admin_name}", show_alert=True)
        return

    success, message_text = await admin_logic.reject_final_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        new_caption = (callback.message.caption or "") + f"\n\n❌ **ОТКЛОНЕН** (@{callback.from_user.username})"
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
            

# --- БЛОК УПРАВЛЕНИЯ НАГРАДАМИ СТАТИСТИКИ ---

async def show_reward_settings_menu(message_or_callback: Union[Message, CallbackQuery], state: FSMContext):
    """Отображает меню настроек наград."""
    await state.set_state(AdminState.REWARD_SETTINGS_MENU)
    
    settings = await db_manager.get_reward_settings()
    timer_hours_str = await db_manager.get_system_setting("reward_timer_hours")
    timer_hours = int(timer_hours_str) if timer_hours_str and timer_hours_str.isdigit() else 24
    
    text = "**⚙️ Управление наградами для топа статистики**\n\n**Текущие настройки:**\n"
    if not settings:
        text += "Призовые места не настроены.\n"
    else:
        for setting in settings:
            text += f" • {setting.place}-е место: {setting.reward_amount} ⭐\n"
    
    text += f"\n**Период выдачи:** раз в {timer_hours} часов."
    
    markup = inline.get_reward_settings_menu_keyboard(timer_hours)

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=markup)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=markup)


@router.message(Command("stat_rewards"), IsSuperAdmin())
async def stat_rewards_handler(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
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

# --- БЛОК: УПРАВЛЕНИЕ СИСТЕМОЙ СТАЖИРОВОК ---

@router.message(Command("internships"), IsSuperAdmin())
async def internships_main_menu(message: Message, state: FSMContext):
    """Главное меню управления стажировками."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    
    stats = await db_manager.get_internship_stats_counts()
    await message.answer(
        "**Панель управления стажировками**",
        reply_markup=await inline.get_admin_internships_main_menu(stats)
    )

@router.callback_query(F.data == "admin_internships:back_to_main", IsSuperAdmin())
async def back_to_internships_main_menu(callback: CallbackQuery, state: FSMContext):
    stats = await db_manager.get_internship_stats_counts()
    await callback.message.edit_text(
        "**Панель управления стажировками**",
        reply_markup=await inline.get_admin_internships_main_menu(stats)
    )


@router.callback_query(F.data.startswith("admin_internships:view:"), IsSuperAdmin())
async def view_internship_list(callback: CallbackQuery, state: FSMContext):
    """Показывает списки анкет, кандидатов или стажеров."""
    await callback.answer()
    _, _, list_type, page_str = callback.data.split(":")
    page = int(page_str)
    
    if list_type == "applications":
        apps, total = await db_manager.get_paginated_applications("pending", page)
        total_pages = ceil(total / 5) if total > 0 else 1
        text = internship_logic.format_applications_page(apps, page, total_pages)
        keyboard = inline.get_pagination_keyboard("admin_internships:view:applications", page, total_pages, back_callback="admin_internships:back_to_main")
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif list_type == "candidates":
        apps, total = await db_manager.get_paginated_applications("approved", page)
        total_pages = ceil(total / 5) if total > 0 else 1
        text = internship_logic.format_candidates_page(apps, page, total_pages)
        keyboard = inline.get_pagination_keyboard("admin_internships:view:candidates", page, total_pages, back_callback="admin_internships:back_to_main")
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif list_type == "interns":
        interns, total = await db_manager.get_paginated_interns(page)
        total_pages = ceil(total / 5) if total > 0 else 1
        text = internship_logic.format_interns_page(interns, page, total_pages)
        keyboard = inline.get_pagination_keyboard("admin_internships:view:interns", page, total_pages, back_callback="admin_internships:back_to_main")
        await callback.message.edit_text(text, reply_markup=keyboard)

@router.message(F.text.startswith("/view_app_"), IsSuperAdmin())
async def view_single_application(message: Message, state: FSMContext):
    """Показывает детальную информацию по одной анкете."""
    try:
        app_id = int(message.text.split("_")[2])
    except (IndexError, ValueError):
        return

    app = await db_manager.get_application_by_id(app_id)
    if not app:
        await message.answer("Анкета не найдена.")
        return
        
    text = internship_logic.format_single_application(app)
    await message.answer(text, reply_markup=inline.get_admin_application_review_keyboard(app))

@router.message(F.text.startswith("/view_intern_"), IsSuperAdmin())
async def view_single_intern(message: Message, state: FSMContext):
    """Показывает детальную информацию по одному стажеру."""
    try:
        intern_id = int(message.text.split("_")[2])
    except (IndexError, ValueError):
        return

    intern = await db_manager.get_user(intern_id)
    if not intern or not intern.is_intern:
        await message.answer("Стажер не найден.")
        return
        
    text = internship_logic.format_single_intern(intern)
    await message.answer(text, reply_markup=inline.get_admin_intern_view_keyboard(intern))

@router.message(F.text.startswith("/assign_task_"), IsSuperAdmin())
async def assign_task_start(message: Message, state: FSMContext):
    """Начало процесса назначения задачи кандидату."""
    try:
        candidate_id = int(message.text.split("_")[2])
    except (IndexError, ValueError):
        return

    candidate_app = await db_manager.get_internship_application(candidate_id)
    if not candidate_app or candidate_app.status != 'approved':
        await message.answer("Кандидат не найден или его анкета не одобрена.")
        return

    await state.set_state(AdminState.INTERNSHIP_CANDIDATE_TASK_GOAL)
    await state.update_data(
        task_candidate_id=candidate_id,
        task_candidate_username=candidate_app.username
    )
    prompt_msg = await message.answer(
        f"Назначение задачи для @{candidate_app.username}.\n"
        f"Желаемые платформы: {candidate_app.platforms}\n\n"
        "**Шаг 1/3:** Выберите тип задания.",
        reply_markup=inline.get_admin_intern_task_setup_keyboard(candidate_id)
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.callback_query(F.data.startswith("admin_internships:action:"), IsSuperAdmin())
async def process_application_action(callback: CallbackQuery, bot: Bot):
    """Обрабатывает одобрение или отклонение анкеты."""
    await callback.answer()
    _, _, action, app_id_str = callback.data.split(":")
    app_id = int(app_id_str)
    
    app = await db_manager.get_application_by_id(app_id)
    if not app or app.status != 'pending':
        await callback.message.edit_text("Эта анкета уже была обработана.", reply_markup=None)
        return

    if action == "approve":
        await db_manager.update_application_status(app_id, "approved")
        await callback.message.edit_text(f"✅ Анкета @{app.username} одобрена.", reply_markup=None)
        try:
            await bot.send_message(app.user_id, "🎉 Поздравляем! Ваша анкета на стажировку была одобрена. Ожидайте назначения первого задания.")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {app.user_id} об одобрении анкеты: {e}")
    
    elif action == "reject":
        await db_manager.update_application_status(app_id, "rejected")
        await callback.message.edit_text(f"❌ Анкета @{app.username} отклонена.", reply_markup=None)
        try:
            await bot.send_message(app.user_id, "К сожалению, ваша анкета на стажировку была отклонена.")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {app.user_id} об отклонении анкеты: {e}")


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
    response = await admin_logic.process_warning_reason_logic(bot, user_id, platform, message.text, user_state, context)
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
    response = await admin_logic.process_rejection_reason_logic(bot, user_id, message.text, context, user_state)
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
    data = await state.get_data()
    
    attached_photo_id = None
    if data.get('photo_required'):
        if not message.reply_to_message or not message.reply_to_message.photo:
            await message.answer("❌ Ошибка: для этого задания требуется фото. Пожалуйста, отправьте фото, а затем ответом на него - текст отзыва.")
            return
        attached_photo_id = message.reply_to_message.photo[-1].file_id
        review_text = message.text
    else:
        if not message.text:
            await message.answer("Текст не может быть пустым.")
            return
        review_text = message.text

    original_message_id = data.get("original_message_id")
    if original_message_id:
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=original_message_id)
        except TelegramBadRequest:
            pass
            
    dp_dummy = Dispatcher(storage=state.storage)
    success, response_text = await admin_logic.send_review_text_to_user_logic(
        bot=bot, dp=dp_dummy, scheduler=scheduler,
        user_id=data['target_user_id'], link_id=data['target_link_id'],
        platform=data['platform'], review_text=review_text,
        attached_photo_id=attached_photo_id
    )
    await message.answer(response_text)
    if success: await state.clear()

@router.message(AdminState.MENTOR_REJECT_REASON, IsAdmin())
async def process_mentor_rejection_reason(message: Message, state: FSMContext, bot: Bot):
    """Ментор вводит причину отклонения работы стажера."""
    await delete_previous_messages(message, state)
    if not message.text:
        await message.answer("Причина не может быть пустой. Пожалуйста, введите текст.")
        return

    data = await state.get_data()
    review_id = data.get('review_id_for_intern_rejection')
    reason = message.text
    admin_username = message.from_user.username or "Admin"

    if not review_id:
        await message.answer("Ошибка: не удалось найти ID отзыва для обработки. Состояние сброшено.")
        await state.clear()
        return

    success, message_text = await admin_logic.handle_mentor_verdict(
        review_id=review_id,
        is_approved_by_mentor=False, # Это отклонение
        reason=reason,
        bot=bot,
        admin_username=admin_username
    )
    
    await message.answer(message_text)
    await state.clear()