# file: handlers/admin.py

import logging
import asyncio
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_ID_1, ADMIN_IDS, FINAL_CHECK_ADMIN, Rewards, Durations
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
    approve_hold_review_logic,
    reject_hold_review_logic,
    approve_withdrawal_logic,
    reject_withdrawal_logic,
    apply_fine_to_user
)
# --- НОВЫЙ ИМПОРТ ---
from logic.ai_helper import generate_review_text

router = Router()
logger = logging.getLogger(__name__)

ADMINS = set(ADMIN_IDS)
TEXT_ADMIN = ADMIN_ID_1

# Хранилище для временной задачи добавления ссылок
temp_admin_tasks = {}  # Хранит {user_id: platform}

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


@router.message(Command("addstars"), F.from_user.id.in_(ADMINS))
async def admin_add_stars(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    await db_manager.update_balance(message.from_user.id, Rewards.ADMIN_ADD_STARS)
    msg = await message.answer(f"✅ На ваш баланс зачислено {Rewards.ADMIN_ADD_STARS} ⭐.")
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))

# --- БЛОК: УПРАВЛЕНИЕ ССЫЛКАМИ ---

@router.message(Command("admin_refs"), F.from_user.id.in_(ADMINS))
async def admin_refs_menu(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    temp_admin_tasks.pop(message.from_user.id, None)
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())

@router.callback_query(F.data == "admin_refs:reset_expired", F.from_user.id.in_(ADMINS))
async def admin_reset_expired(callback: CallbackQuery):
    await callback.answer("⚙️ Сбрасываю просроченные ссылки...")
    count = await db_manager.reset_all_expired_links()
    if callback.message:
        await callback.message.answer(f"✅ Готово. {count} просроченных ссылок возвращены в статус 'available'.")
        await callback.message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    try:
        if callback.message:
            await callback.message.delete()
    except:
        pass

@router.callback_query(F.data == "back_to_refs_menu", F.from_user.id.in_(ADMINS))
async def back_to_refs_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    temp_admin_tasks.pop(callback.from_user.id, None)
    
    data = await state.get_data()
    message_ids_to_delete = data.get("link_message_ids", [])
    if callback.message:
        message_ids_to_delete.append(callback.message.message_id)
    
    for msg_id in set(message_ids_to_delete):
        try: 
            await bot.delete_message(chat_id=callback.from_user.id, message_id=msg_id)
        except TelegramBadRequest: 
            pass

    await bot.send_message(callback.from_user.id, "Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("admin_refs:add:"), F.from_user.id.in_(ADMINS))
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    platform = callback.data.split(':')[2]
    temp_admin_tasks[callback.from_user.id] = platform
    logger.info(f"[NO_FSM_ADD_LINK] Task started for user {callback.from_user.id}. Platform: {platform}")
    if callback.message:
        await callback.message.edit_text(
            f"Выбрана платформа: <i>{platform}</i>.\n\nОтправьте ссылки следующим сообщением.",
            reply_markup=inline.get_back_to_admin_refs_keyboard()
        )
    await callback.answer()

@router.message(
    lambda message: message.from_user.id in temp_admin_tasks, 
    F.text, 
    F.from_user.id.in_(ADMINS)
)
async def admin_add_links_handler(message: Message):
    user_id = message.from_user.id
    platform = temp_admin_tasks.pop(user_id)
    logger.info(f"[NO_FSM_ADD_LINK] Processing link submission for user {user_id}. Platform: {platform}")
    
    try:
        result_text = await process_add_links_logic(message.text, platform)
        await message.answer(result_text)
        await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    except Exception as e:
        logger.exception(f"Критическая ошибка (без FSM) для пользователя {user_id}: {e}")
        await message.answer("❌ Произошла критическая ошибка. Обратитесь к логам.")

@router.callback_query(F.data.startswith("admin_refs:stats:"), F.from_user.id.in_(ADMINS))
async def admin_view_refs_stats(callback: CallbackQuery):
    try: await callback.answer("Загружаю...", show_alert=False)
    except: pass
    platform = callback.data.split(':')[2]
    all_links = await reference_manager.get_all_references(platform)
    stats = {status: len([link for link in all_links if link.status == status]) for status in ['available', 'assigned', 'used']}
    text = (f"📊 Статистика по <i>{platform}</i>:\n\n"
            f"Всего: {len(all_links)}\n"
            f"🟢 Доступно: {stats.get('available', 0)}\n"
            f"🟡 В работе: {stats.get('assigned', 0)}\n"
            f"🔴 Использовано: {stats.get('used', 0)}")
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_back_to_admin_refs_keyboard())

@router.callback_query(F.data.startswith("admin_refs:list:"), F.from_user.id.in_(ADMINS))
async def admin_view_refs_list(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await callback.answer("Загружаю список...")
    platform = callback.data.split(':')[2]
    all_links = await reference_manager.get_all_references(platform)

    if callback.message:
        await callback.message.delete()

    if not all_links:
        msg = await bot.send_message(callback.from_user.id, f"В базе нет ссылок для платформы <i>{platform}</i>.", reply_markup=inline.get_admin_refs_list_keyboard(platform))
        await state.update_data(link_message_ids=[msg.message_id])
        return

    message_ids = []
    base_text = f"📄 Список ссылок для <i>{platform}</i>:\n\n"
    chunks = [""]
    icons = {"available": "🟢", "assigned": "🟡", "used": "🔴", "expired": "⚫"}

    for link in all_links:
        user_info = f"-> ID: {link.assigned_to_user_id}" if link.assigned_to_user_id else ""
        line = f"{icons.get(link.status, '❓')} <b>ID:{link.id}</b> | <code>{link.status}</code> {user_info}\n🔗 <code>{link.url}</code>\n\n"
        
        if len(chunks[-1] + line) > 4000:
            chunks.append("")
        chunks[-1] += line
    
    for i, chunk in enumerate(chunks):
        final_text = (base_text + chunk) if i == 0 else chunk
        keyboard = inline.get_admin_refs_list_keyboard(platform) if i == len(chunks) - 1 else None
        msg = await bot.send_message(callback.from_user.id, final_text, reply_markup=keyboard, disable_web_page_preview=True)
        message_ids.append(msg.message_id)

    await state.update_data(link_message_ids=message_ids)

@router.callback_query(F.data.startswith("admin_refs:delete_start:"), F.from_user.id.in_(ADMINS))
async def admin_delete_ref_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(':')[2]
    await state.set_state(AdminState.DELETE_LINK_ID)
    await state.update_data(platform_for_deletion=platform)
    if callback.message:
        prompt_msg = await callback.message.edit_text("Введите ID ссылки, которую хотите удалить:", reply_markup=inline.get_back_to_admin_refs_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()

@router.message(AdminState.DELETE_LINK_ID, F.from_user.id.in_(ADMINS))
async def admin_process_delete_ref_id(message: Message, state: FSMContext, bot: Bot):
    await delete_previous_messages(message, state)

    if not message.text or not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите корректный числовой ID.")
        return
    
    link_id = int(message.text)
    data = await state.get_data()
    platform = data.get("platform_for_deletion")
    
    success, assigned_user_id = await reference_manager.delete_reference(link_id)
    
    if not success:
        await message.answer(f"❌ Ссылка с ID {link_id} не найдена.")
    else:
        await message.answer(f"✅ Ссылка ID {link_id} удалена.")
    
        if assigned_user_id:
            try:
                user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=assigned_user_id, chat_id=assigned_user_id))
                await user_state.clear()
                await bot.send_message(assigned_user_id, "❗️ Ссылка для вашего задания была удалена. Процесс остановлен.", reply_markup=reply.get_main_menu_keyboard())
                await user_state.set_state(UserState.MAIN_MENU)
            except Exception as e: 
                logger.warning(f"Не удалось уведомить {assigned_user_id} об удалении ссылки: {e}")

    await state.clear()
    
    temp_message = await message.answer("Обновляю список...")
    dummy_callback_query = CallbackQuery(
        id=str(message.message_id), from_user=message.from_user, chat_instance="dummy", 
        message=temp_message,
        data=f"admin_refs:list:{platform}"
    )
    await admin_view_refs_list(callback=dummy_callback_query, bot=bot, state=state)
    await temp_message.delete()

@router.callback_query(F.data.startswith("admin_refs:return_start:"), F.from_user.id.in_(ADMINS))
async def admin_return_ref_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса возврата ссылки в 'available'."""
    platform = callback.data.split(':')[2]
    await state.set_state(AdminState.RETURN_LINK_ID)
    await state.update_data(platform_for_return=platform)
    if callback.message:
        prompt_msg = await callback.message.edit_text("Введите ID 'зависшей' ссылки (в статусе 'assigned'), которую хотите вернуть в доступные:", reply_markup=inline.get_back_to_admin_refs_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()

@router.message(AdminState.RETURN_LINK_ID, F.from_user.id.in_(ADMINS))
async def admin_process_return_ref_id(message: Message, state: FSMContext, bot: Bot):
    """Обработка ID ссылки для возврата."""
    await delete_previous_messages(message, state)

    if not message.text or not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите корректный числовой ID.")
        return
    
    link_id = int(message.text)
    data = await state.get_data()
    platform = data.get("platform_for_return")
    
    success, assigned_user_id = await reference_manager.force_release_reference(link_id)
    
    if not success:
        await message.answer(f"❌ Не удалось вернуть ссылку с ID {link_id}. Возможно, она не в статусе 'assigned' или не найдена.")
    else:
        await message.answer(f"✅ Ссылка ID {link_id} возвращена в статус 'available'.")
        if assigned_user_id:
            try:
                user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=assigned_user_id, chat_id=assigned_user_id))
                await user_state.clear()
                await bot.send_message(assigned_user_id, "❗️ Администратор прервал ваше задание. Ссылка была возвращена в пул. Процесс остановлен.", reply_markup=reply.get_main_menu_keyboard())
                await user_state.set_state(UserState.MAIN_MENU)
            except Exception as e: 
                logger.warning(f"Не удалось уведомить {assigned_user_id} о возврате ссылки: {e}")

    await state.clear()
    
    # Обновляем список для наглядности
    temp_message = await message.answer("Обновляю список...")
    dummy_callback_query = CallbackQuery(
        id=str(message.message_id), from_user=message.from_user, chat_instance="dummy", 
        message=temp_message,
        data=f"admin_refs:list:{platform}"
    )
    await admin_view_refs_list(callback=dummy_callback_query, bot=bot, state=state)
    await temp_message.delete()


@router.callback_query(F.data.startswith('admin_verify:'), F.from_user.id.in_(ADMINS))
async def admin_verification_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try: await callback.answer()
    except: pass
    _, action, context, user_id_str = callback.data.split(':')
    user_id = int(user_id_str)
    admin_state = state
    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    original_text = ""
    if callback.message:
        original_text = callback.message.text or callback.message.caption or ""
    
    action_text = ""
    if action == "confirm":
        action_text = f"✅ ПОДТВЕРЖДЕНО (@{callback.from_user.username})"
        if context == "google_profile":
            await user_state.set_state(UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
            await bot.send_message(user_id, "Профиль прошел проверку. Пришлите скриншот последних отзывов.", reply_markup=inline.get_google_last_reviews_check_keyboard())
        elif context == "google_last_reviews":
            await user_state.set_state(UserState.GOOGLE_REVIEW_READY_TO_CONTINUE)
            await bot.send_message(user_id, "Отзывы прошли проверку. Можете продолжить.", reply_markup=inline.get_google_continue_writing_keyboard())
        elif "yandex_profile" in context:
            await user_state.set_state(UserState.YANDEX_REVIEW_READY_TO_TASK)
            await bot.send_message(user_id, "Профиль Yandex прошел проверку. Можете продолжить.", reply_markup=inline.get_yandex_continue_writing_keyboard())
        elif context == "gmail_device_model":
            prompt_msg = await bot.send_message(callback.from_user.id, "✅ Модель подтверждена.\nВведите данные для аккаунта:\nИмя\nФамилия\nПароль\nПочта (без @gmail.com)")
            await admin_state.set_state(AdminState.ENTER_GMAIL_DATA)
            await admin_state.update_data(gmail_user_id=user_id, prompt_message_id=prompt_msg.message_id)
    
    elif action == "warn":
        action_text = f"⚠️ ВЫДАЧА ПРЕДУПРЕЖДЕНИЯ (@{callback.from_user.username})"
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
        action_text = f"❌ ОТКЛОНЕН (@{callback.from_user.username})"
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

@router.callback_query(F.data.startswith('admin_provide_text:'), F.from_user.id == TEXT_ADMIN)
async def admin_start_providing_text(callback: CallbackQuery, state: FSMContext):
    try:
        _, platform, user_id_str, link_id_str = callback.data.split(':')
        state_map = {'google': AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, 'yandex_with_text': AdminState.PROVIDE_YANDEX_REVIEW_TEXT}
        if platform not in state_map: await callback.answer("Ошибка платформы."); return
        
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

# --- НОВЫЙ БЛОК: ИНТЕГРАЦИЯ С ИИ ---

@router.callback_query(F.data.startswith('admin_ai_generate_start:'), F.from_user.id == TEXT_ADMIN)
async def admin_ai_generate_start(callback: CallbackQuery, state: FSMContext):
    """Шаг 1: Админ нажимает кнопку 'Сгенерировать с ИИ'."""
    try:
        _, platform, user_id_str, link_id_str = callback.data.split(':')
        
        edit_text = "✍️ Введите короткий сценарий/описание для генерации отзыва:"
        new_content = f"{(callback.message.caption or callback.message.text)}\n\n{edit_text}"
        
        prompt_msg = None
        if callback.message:
            # Удаляем старую клавиатуру и добавляем текст-приглашение
            if callback.message.photo: 
                await callback.message.edit_caption(caption=new_content, reply_markup=None)
            else: 
                prompt_msg = await callback.message.edit_text(new_content, reply_markup=None)

        await state.set_state(AdminState.AI_AWAITING_SCENARIO)
        # Сохраняем все необходимые данные для последующих шагов
        await state.update_data(
            target_user_id=int(user_id_str), 
            target_link_id=int(link_id_str), 
            platform=platform,
            prompt_message_id=prompt_msg.message_id if prompt_msg else None,
            original_message_id=callback.message.message_id # Сохраняем ID исходного сообщения
        )
        await callback.answer("Ожидаю сценарий...")
    except Exception as e: 
        logger.exception(f"Ошибка на старте AI генерации: {e}")
        await callback.answer("Произошла ошибка.", show_alert=True)

@router.message(AdminState.AI_AWAITING_SCENARIO, F.from_user.id == TEXT_ADMIN)
async def admin_process_ai_scenario(message: Message, state: FSMContext, bot: Bot):
    """Шаг 2 и 3: Админ отправляет сценарий, бот генерирует текст."""
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

    if "ошибка" in generated_text.lower() or "ai-сервер" in generated_text.lower() or "ai-модель" in generated_text.lower():
        await message.answer(f"❌ {generated_text}\n\nПопробуйте снова или напишите вручную.", reply_markup=inline.get_cancel_inline_keyboard())
        return

    moderation_text = (
        "📄 **Сгенерированный текст отзыва:**\n\n"
        f"<i>{generated_text}</i>\n\n"
        "Выберите следующее действие:"
    )
    
    await message.answer(moderation_text, reply_markup=inline.get_ai_moderation_keyboard())
    
    await state.set_state(AdminState.AI_AWAITING_MODERATION)
    await state.update_data(ai_scenario=scenario, ai_generated_text=generated_text)


@router.callback_query(F.data.startswith('ai_moderation:'), AdminState.AI_AWAITING_MODERATION, F.from_user.id == TEXT_ADMIN)
async def admin_process_ai_moderation(callback: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    """Шаг 6: Обработка кнопок модерации."""
    action = callback.data.split(':')[1]
    data = await state.get_data()
    
    if action == 'send':
        await callback.answer("✅ Отправляю пользователю...", show_alert=False)
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
        await callback.answer("🔄 Генерирую новый вариант...", show_alert=False)
        scenario = data.get('ai_scenario')
        
        link_id = data.get('target_link_id')
        link = await db_manager.db_get_link_by_id(link_id)
        company_info = link.url if link else "Неизвестная компания"

        status_msg = await callback.message.answer("🤖 Повторная генерация...")
        generated_text = await generate_review_text(
            company_info=company_info,
            scenario=scenario,
        )
        await status_msg.delete()

        if "ошибка" in generated_text.lower() or "ai-сервер" in generated_text.lower() or "ai-модель" in generated_text.lower():
            await callback.message.answer(f"❌ {generated_text}\n\nПопробуйте снова или напишите вручную.", reply_markup=inline.get_cancel_inline_keyboard())
            return

        new_moderation_text = (
            "📄 **Новый сгенерированный текст отзыва:**\n\n"
            f"<i>{generated_text}</i>\n\n"
            "Выберите следующее действие:"
        )
        await callback.message.edit_text(new_moderation_text, reply_markup=inline.get_ai_moderation_keyboard())
        await state.update_data(ai_generated_text=generated_text)
    
    elif action == 'manual':
        await callback.answer("✍️ Переключаю на ручной ввод...", show_alert=False)
        platform = data['platform']
        state_map = {'google': AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, 'yandex_with_text': AdminState.PROVIDE_YANDEX_REVIEW_TEXT}
        
        prompt_msg = await callback.message.edit_text(
            "Введите текст отзыва вручную. Вы можете скопировать и отредактировать сгенерированный текст выше.",
            reply_markup=inline.get_cancel_inline_keyboard()
        )
        await state.set_state(state_map[platform])
        await state.update_data(prompt_message_id=prompt_msg.message_id)

# --- КОНЕЦ БЛОКА ИИ ---


@router.callback_query(F.data.startswith('admin_final_approve:'), F.from_user.id.in_(ADMINS))
async def admin_final_approve(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await approve_review_to_hold_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        await callback.message.edit_caption(caption=f"{(callback.message.caption or '')}\n\n✅ В ХОЛДЕ (@{callback.from_user.username})", reply_markup=None)

@router.callback_query(F.data.startswith('admin_final_reject:'), F.from_user.id.in_(ADMINS))
async def admin_final_reject(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await reject_initial_review_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        await callback.message.edit_caption(caption=f"{(callback.message.caption or '')}\n\n❌ ОТКЛОНЕН (@{callback.from_user.username})", reply_markup=None)

@router.message(Command("reviewhold"), F.from_user.id.in_(ADMINS))
async def admin_review_hold(message: Message, bot: Bot, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    await message.answer("⏳ Загружаю отзывы в холде...")
    hold_reviews = await db_manager.get_all_hold_reviews()
    if not hold_reviews:
        await message.answer("В холде нет отзывов."); return
    await message.answer(f"Найдено отзывов: {len(hold_reviews)}")
    for review in hold_reviews:
        link_url = review.link.url if review.link else "Ссылка удалена"
        info_text = (f"ID: <code>{review.id}</code> | User: <code>{review.user_id}</code>\nПлатформа: <code>{review.platform}</code> | Сумма: <code>{review.amount}</code> ⭐\n"
                     f"Ссылка: <code>{link_url}</code>\nТекст: «<i>{review.review_text}</i>»")
        try:
            if review.admin_message_id:
                await bot.copy_message(message.chat.id, FINAL_CHECK_ADMIN, review.admin_message_id, caption=info_text, reply_markup=inline.get_admin_hold_review_keyboard(review.id))
            else:
                await message.answer(info_text, reply_markup=inline.get_admin_hold_review_keyboard(review.id))
        except Exception as e:
            await message.answer(f"Ошибка обработки отзыва {review.id}: {e}\n\n{info_text}", reply_markup=inline.get_admin_hold_review_keyboard(review.id))

@router.callback_query(F.data.startswith('admin_hold_approve:'), F.from_user.id.in_(ADMINS))
async def admin_hold_approve_handler(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await approve_hold_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        new_caption = (callback.message.caption or "") + f"\n\n✅ ОДОБРЕН (@{callback.from_user.username})"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)

@router.callback_query(F.data.startswith('admin_hold_reject:'), F.from_user.id.in_(ADMINS))
async def admin_hold_reject_handler(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await reject_hold_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        new_caption = (callback.message.caption or "") + f"\n\n❌ ОТКЛОНЕН (@{callback.from_user.username})"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)

@router.callback_query(F.data.startswith("admin_withdraw_approve:"), F.from_user.id.in_(ADMINS))
async def admin_approve_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await approve_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        try:
            new_text = (callback.message.text or "") + f"\n\n<i>[ ✅ ВЫПЛАЧЕНО Администратором ]</i>"
            await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit withdrawal message in channel: {e}")

@router.callback_query(F.data.startswith("admin_withdraw_reject:"), F.from_user.id.in_(ADMINS))
async def admin_reject_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await reject_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success and callback.message:
        try:
            new_text = (callback.message.text or "") + f"\n\n<i>[ ❌ ОТКЛОНЕНО Администратором ]</i>"
            await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit withdrawal message in channel: {e}")

@router.message(Command("reset_cooldown"), F.from_user.id.in_(ADMINS))
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

@router.message(Command("viewhold"), F.from_user.id.in_(ADMINS))
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

@router.message(Command("fine"), F.from_user.id.in_(ADMINS))
async def fine_user_start(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    prompt_msg = await message.answer("Введите ID или @username пользователя для штрафа.", reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.FINE_USER_ID)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(Command("create_promo"), F.from_user.id.in_(ADMINS))
async def create_promo_start(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.clear()
    prompt_msg = await message.answer("Введите название для нового промокода (например, <code>NEWYEAR2025</code>). Оно должно быть уникальным.",
                         reply_markup=inline.get_cancel_inline_keyboard())
    await state.set_state(AdminState.PROMO_CODE_NAME)
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(Command("ban"), F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.BAN_REASON, F.from_user.id.in_(ADMINS))
async def ban_user_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Причина не может быть пустой. Введите причину текстом.")
        return
        
    await delete_previous_messages(message, state)
    data = await state.get_data()
    user_id_to_ban = data.get("user_id_to_ban")
    ban_reason = message.text

    success = await db_manager.ban_user(user_id_to_ban)

    if not success:
        await message.answer("❌ Произошла ошибка при бане пользователя.")
        await state.clear()
        return

    try:
        user_notification = (
            f"❗️ **Ваш аккаунт был заблокирован администратором.**\n\n"
            f"<b>Причина:</b> {ban_reason}\n\n"
            "Вам закрыт доступ ко всем функциям бота. "
            "Если вы считаете, что это ошибка, вы можете подать запрос на амнистию командой /unban_request."
        )
        await bot.send_message(user_id_to_ban, user_notification)
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id_to_ban} о бане: {e}")

    msg = await message.answer(f"✅ Пользователь <code>{user_id_to_ban}</code> успешно забанен.")
    asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
    await state.clear()

# --- Обработчики состояний (FSM) ---

@router.message(AdminState.PROVIDE_WARN_REASON, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.PROVIDE_REJECTION_REASON, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, F.from_user.id == TEXT_ADMIN)
@router.message(AdminState.PROVIDE_YANDEX_REVIEW_TEXT, F.from_user.id == TEXT_ADMIN)
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

@router.message(AdminState.FINE_USER_ID, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.FINE_AMOUNT, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.FINE_REASON, F.from_user.id.in_(ADMINS))
async def fine_user_get_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text: return
    await delete_previous_messages(message, state)
    data = await state.get_data()
    result_text = await apply_fine_to_user(data.get("target_user_id"), message.from_user.id, data.get("fine_amount"), message.text, bot)
    await message.answer(result_text)
    await state.clear()

@router.message(AdminState.PROMO_CODE_NAME, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.PROMO_USES, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.PROMO_REWARD, F.from_user.id.in_(ADMINS))
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

@router.callback_query(F.data.startswith("promo_cond:"), AdminState.PROMO_CONDITION, F.from_user.id.in_(ADMINS))
async def promo_condition_selected(callback: CallbackQuery, state: FSMContext):
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