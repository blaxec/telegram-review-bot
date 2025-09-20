# file: handlers/support.py

import logging
import asyncio
import datetime
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_IDS
from database import db_manager
# ИЗМЕНЕНИЕ: Удаляем импорт отсюда
# from logic import notification_manager
from utils.access_filters import IsAdmin

router = Router()
logger = logging.getLogger(__name__)

# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ---
async def delete_previous_messages(message_or_callback: Message | CallbackQuery, state: FSMContext, and_self: bool = True):
    """Вспомогательная функция для удаления старых сообщений. Работает и с Message, и с CallbackQuery."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    # Определяем, с чем работаем: с сообщением или с нажатием кнопки
    is_message = isinstance(message_or_callback, Message)
    target_message = message_or_callback if is_message else message_or_callback.message
    
    if not target_message:
        return

    if prompt_message_id:
        try:
            await target_message.bot.delete_message(target_message.chat.id, prompt_message_id)
        except TelegramBadRequest:
            pass

    # Удаляем само сообщение, только если это было Message, а не CallbackQuery
    if and_self and is_message:
        try:
            await target_message.delete()
        except TelegramBadRequest:
            pass

@router.message(F.text == '💬 Поддержка', UserState.MAIN_MENU)
async def support_handler(message: Message, state: FSMContext):
    """Начало диалога с поддержкой."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    
    user = await db_manager.get_user(message.from_user.id)
    if user and user.support_cooldown_until and user.support_cooldown_until > datetime.datetime.utcnow():
        remaining_time = user.support_cooldown_until - datetime.datetime.utcnow()
        await message.answer(f"Вы временно не можете отправлять запросы в поддержку. Ограничение еще на: {str(remaining_time).split('.')[0]}")
        return

    await state.set_state(UserState.SUPPORT_AWAITING_QUESTION)
    prompt_msg = await message.answer(
        "Пожалуйста, опишите вашу проблему или задайте вопрос одним сообщением. Мы передадим его администратору.",
        reply_markup=inline.get_cancel_inline_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(UserState.SUPPORT_AWAITING_QUESTION, F.text)
async def process_question(message: Message, state: FSMContext):
    """Обработка вопроса от пользователя, предложение добавить фото."""
    await delete_previous_messages(message, state)
    
    await state.update_data(support_question=message.text)
    await state.set_state(UserState.SUPPORT_AWAITING_PHOTO_CHOICE)
    
    prompt_msg = await message.answer(
        "Ваш вопрос принят. Хотите прикрепить к нему фотографию (например, скриншот проблемы)?",
        reply_markup=inline.get_support_photo_choice_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

async def send_ticket_to_admins(bot: Bot, state: FSMContext, user_id: int, username: str):
    """Финальная функция для создания тикета и отправки админам."""
    data = await state.get_data()
    question = data.get("support_question")
    photo_file_id = data.get("support_photo_id")

    admin_text = (
        f"🚨 <b>Новый вопрос в поддержку</b> от @{username} (ID: <code>{user_id}</code>)\n\n"
        f"<b>Вопрос:</b>\n<i>{question}</i>"
    )
    
    active_admins = await db_manager.get_active_admins(ADMIN_IDS)
    sent_messages_map = {} 
    
    for admin_id in active_admins:
        try:
            if photo_file_id:
                sent_msg = await bot.send_photo(admin_id, photo=photo_file_id, caption=admin_text)
            else:
                sent_msg = await bot.send_message(admin_id, admin_text)
            sent_messages_map[ADMIN_IDS.index(admin_id)] = sent_msg.message_id
        except Exception as e:
            logger.error(f"Не удалось отправить тикет админу {admin_id}: {e}")
            sent_messages_map[ADMIN_IDS.index(admin_id)] = None

    admin_message_ids_for_db = {
        0: sent_messages_map.get(0),
        1: sent_messages_map.get(1)
    }

    if any(sent_messages_map.values()):
        ticket = await db_manager.create_support_ticket(
            user_id=user_id,
            username=username,
            question=question,
            admin_message_ids=admin_message_ids_for_db,
            photo_file_id=photo_file_id
        )
        
        for i, admin_id_in_config in enumerate(ADMIN_IDS):
            msg_id_to_edit = sent_messages_map.get(i)
            if msg_id_to_edit:
                try:
                    if photo_file_id:
                        await bot.edit_message_reply_markup(
                            chat_id=admin_id_in_config, message_id=msg_id_to_edit,
                            reply_markup=inline.get_support_admin_keyboard(ticket.id, user_id)
                        )
                    else:
                        await bot.edit_message_reply_markup(
                            chat_id=admin_id_in_config, message_id=msg_id_to_edit,
                            reply_markup=inline.get_support_admin_keyboard(ticket.id, user_id)
                        )
                except Exception as e:
                    logger.error(f"Не удалось обновить клавиатуру у админа {admin_id_in_config} для тикета {ticket.id}: {e}")
        
        await bot.send_message(user_id, "Ваш вопрос отправлен администраторам. Пожалуйста, ожидайте ответа.")
    else:
        await bot.send_message(user_id, "❌ К сожалению, не удалось связаться с поддержкой. Все администраторы сейчас в «ночном режиме». Попробуйте снова позже.")

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)


@router.callback_query(F.data == "support_add_photo:no", UserState.SUPPORT_AWAITING_PHOTO_CHOICE)
async def process_no_photo_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Пользователь решил не прикреплять фото."""
    await delete_previous_messages(callback, state, and_self=False)
    try:
        if callback.message:
            await callback.message.edit_text("Отправляем ваш тикет...")
    except TelegramBadRequest: pass
    await callback.answer()
    await send_ticket_to_admins(bot, state, callback.from_user.id, callback.from_user.username or "N/A")

@router.callback_query(F.data == "support_add_photo:yes", UserState.SUPPORT_AWAITING_PHOTO_CHOICE)
async def process_yes_photo_choice(callback: CallbackQuery, state: FSMContext):
    """Пользователь решил прикрепить фото."""
    await delete_previous_messages(callback, state, and_self=False)
    await state.set_state(UserState.SUPPORT_AWAITING_PHOTO)
    prompt_msg = await callback.message.answer(
        "Пожалуйста, отправьте фотографию следующим сообщением.",
        reply_markup=inline.get_cancel_inline_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()

@router.message(UserState.SUPPORT_AWAITING_PHOTO, F.photo)
async def process_support_photo(message: Message, state: FSMContext, bot: Bot):
    """Пользователь отправил фото, создаем и отправляем тикет."""
    await delete_previous_messages(message, state)
    await state.update_data(support_photo_id=message.photo[-1].file_id)
    await message.answer("Фотография прикреплена. Отправляем ваш тикет...")
    await send_ticket_to_admins(bot, state, message.from_user.id, message.from_user.username or "N/A")


# --- Админские обработчики ---

@router.callback_query(F.data.startswith("support_answer:"), IsAdmin())
async def admin_claim_question(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Админ нажимает кнопку, чтобы ответить на вопрос."""
    ticket_id = int(callback.data.split(":")[1])
    admin_id = callback.from_user.id
    admin_username = callback.from_user.username or "Администратор"
    
    ticket = await db_manager.claim_support_ticket(ticket_id, admin_id)
    
    if not ticket:
        await callback.answer("Этот вопрос уже был взят в работу другим администратором.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except: pass
        return

    other_admins_to_notify = [aid for aid in ADMIN_IDS if aid != admin_id]
    
    for other_admin_id_in_config in other_admins_to_notify:
        msg_id_to_edit = None
        if ADMIN_IDS.index(other_admin_id_in_config) == 0:
            msg_id_to_edit = ticket.admin_message_id_1
        elif len(ADMIN_IDS) > 1 and ADMIN_IDS.index(other_admin_id_in_config) == 1:
            msg_id_to_edit = ticket.admin_message_id_2

        if msg_id_to_edit:
            try:
                if ticket.photo_file_id:
                    await bot.edit_message_caption(
                        caption=f"{callback.message.caption}\n\n<b>Взят в работу администратором @{admin_username}</b>",
                        chat_id=other_admin_id_in_config, message_id=msg_id_to_edit, reply_markup=None
                    )
                else:
                    await bot.edit_message_text(
                        text=f"{callback.message.text}\n\n<b>Взят в работу администратором @{admin_username}</b>",
                        chat_id=other_admin_id_in_config, message_id=msg_id_to_edit, reply_markup=None
                    )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение у админа {other_admin_id_in_config}: {e}")

    new_text = (callback.message.caption or callback.message.text) + "\n\n✅ Вы отвечаете на этот вопрос. Отправьте ответ следующим сообщением."
    
    if ticket.photo_file_id:
        await callback.message.edit_caption(caption=new_text, reply_markup=None)
    else:
        await callback.message.edit_text(text=new_text, reply_markup=None)

    prompt_msg = callback.message
    await state.set_state(AdminState.SUPPORT_AWAITING_ANSWER)
    await state.update_data(
        support_ticket_id=ticket_id, 
        support_user_id=ticket.user_id,
        prompt_message_id=prompt_msg.message_id
    )
    
    await callback.answer()

@router.message(AdminState.SUPPORT_AWAITING_ANSWER, IsAdmin())
async def admin_send_answer(message: Message, state: FSMContext, bot: Bot):
    """Админ отправляет ответ, который пересылается пользователю."""
    await delete_previous_messages(message, state)
    if not message.text:
        await message.answer("Пожалуйста, введите ответ текстом.")
        return

    data = await state.get_data()
    user_id = data.get("support_user_id")
    ticket_id = data.get("support_ticket_id")
    
    if not user_id or not ticket_id:
        await message.answer("Произошла ошибка: не найдены данные тикета. Состояние сброшено.")
        await state.clear()
        return

    user_text = (
        f"📩 <b>Вам пришел ответ от поддержки:</b>\n\n"
        f"{message.text}"
    )
    
    try:
        await bot.send_message(user_id, user_text)
        await message.answer("✅ Ваш ответ успешно отправлен пользователю.")
        await db_manager.close_support_ticket(ticket_id)
    except Exception as e:
        logger.error(f"Не удалось отправить ответ поддержки пользователю {user_id}: {e}")
        await message.answer("❌ Не удалось отправить ответ пользователю. Возможно, он заблокировал бота.")

    await state.clear()


@router.callback_query(F.data.startswith("support_warn:"), IsAdmin())
async def admin_start_support_warn(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Админ нажимает кнопку 'Выдать предупреждение'."""
    try:
        _, ticket_id_str, user_id_str = callback.data.split(":")
        ticket_id = int(ticket_id_str)
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        await callback.answer("Ошибка в данных кнопки.", show_alert=True)
        return

    admin_id = callback.from_user.id
    admin_username = callback.from_user.username or "Администратор"

    ticket = await db_manager.claim_support_ticket(ticket_id, admin_id)
    
    if not ticket:
        await callback.answer("Этот вопрос уже был взят в работу другим администратором.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception: 
            pass
        return

    other_admins_to_notify = [aid for aid in ADMIN_IDS if aid != admin_id]
    for other_admin_id_in_config in other_admins_to_notify:
        msg_id_to_edit = None
        if ADMIN_IDS.index(other_admin_id_in_config) == 0:
            msg_id_to_edit = ticket.admin_message_id_1
        elif len(ADMIN_IDS) > 1 and ADMIN_IDS.index(other_admin_id_in_config) == 1:
            msg_id_to_edit = ticket.admin_message_id_2

        if msg_id_to_edit:
            try:
                if ticket.photo_file_id:
                    await bot.edit_message_caption(
                        caption=f"{callback.message.caption}\n\n<b>Взят в работу (для предупреждения) администратором @{admin_username}</b>",
                        chat_id=other_admin_id_in_config, message_id=msg_id_to_edit, reply_markup=None
                    )
                else:
                    await bot.edit_message_text(
                        text=f"{callback.message.text}\n\n<b>Взят в работу (для предупреждения) администратором @{admin_username}</b>",
                        chat_id=other_admin_id_in_config, message_id=msg_id_to_edit, reply_markup=None
                    )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение у админа {other_admin_id_in_config} (warn): {e}")

    try:
        new_text = (callback.message.caption or callback.message.text) + "\n\n⚠️ Вы собираетесь выдать предупреждение. Введите причину следующим сообщением."
        if ticket.photo_file_id:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(text=new_text, reply_markup=None)
    except Exception as e:
         logger.warning(f"Не удалось отредактировать сообщение у админа {admin_id} (warn): {e}")

    await state.set_state(AdminState.SUPPORT_AWAITING_WARN_REASON)
    await state.update_data(
        support_ticket_id=ticket_id,
        target_user_id=user_id,
        original_message_id=callback.message.message_id
    )
    await callback.answer()


@router.message(AdminState.SUPPORT_AWAITING_WARN_REASON, F.text, IsAdmin())
async def admin_process_support_warn_reason(message: Message, state: FSMContext, bot: Bot):
    """Админ ввел причину, выдаем предупреждение и решаем, нужен ли кулдаун."""
    await delete_previous_messages(message, state)
    data = await state.get_data()
    user_id = data.get("target_user_id")
    ticket_id = data.get("support_ticket_id")
    warn_reason = message.text

    await state.update_data(support_warn_reason=warn_reason)

    user = await db_manager.get_user(user_id)
    current_warnings = user.support_warnings if user else 0
    new_warnings_count = current_warnings + 1

    if new_warnings_count == 1:
        # Первое предупреждение, просто выдаем
        await db_manager.add_support_warning_and_cooldown(user_id)
        await bot.send_message(user_id, f"⚠️ <b>Вам выдано предупреждение от службы поддержки.</b>\n\n<b>Причина:</b> {warn_reason}\n\nПожалуйста, задавайте вопросы по теме, чтобы избежать дальнейших ограничений.")
        await message.answer(f"✅ Предупреждение (№{new_warnings_count}) отправлено пользователю {user_id}.")
        await db_manager.close_support_ticket(ticket_id)
        await state.clear()
    elif new_warnings_count == 2:
        # Второе, выдаем кулдаун на 1 час
        await db_manager.add_support_warning_and_cooldown(user_id, hours=1)
        await bot.send_message(user_id, f"❗️ <b>Вы получили второе предупреждение от службы поддержки.</b>\n\n<b>Причина:</b> {warn_reason}\n\nЗа повторное нарушение доступ к поддержке заблокирован на 1 час.")
        await message.answer(f"✅ Предупреждение (№{new_warnings_count}) отправлено пользователю {user_id}. Доступ к поддержке заблокирован на 1 час.")
        await db_manager.close_support_ticket(ticket_id)
        await state.clear()
    else:
        # Третье и последующие, админ сам вводит срок
        await state.set_state(AdminState.SUPPORT_AWAITING_COOLDOWN_HOURS)
        prompt_msg = await message.answer(f"Это уже {new_warnings_count}-е предупреждение для пользователя. Введите срок блокировки доступа к поддержке в часах:")
        await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.SUPPORT_AWAITING_COOLDOWN_HOURS, F.text, IsAdmin())
async def admin_set_support_cooldown(message: Message, state: FSMContext, bot: Bot):
    """Админ вводит срок блокировки."""
    await delete_previous_messages(message, state)

    if not message.text.isdigit() or int(message.text) <= 0:
        prompt_msg = await message.answer("❌ Пожалуйста, введите целое положительное число.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
        
    hours = int(message.text)
    data = await state.get_data()
    user_id = data.get("target_user_id")
    ticket_id = data.get("support_ticket_id")
    warn_reason = data.get("support_warn_reason")
    
    current_warnings = await db_manager.add_support_warning_and_cooldown(user_id, hours=hours)

    await bot.send_message(user_id, f"❗️ <b>Вы получили очередное предупреждение от службы поддержки.</b>\n\n<b>Причина:</b> {warn_reason}\n\nДоступ к поддержке заблокирован на {hours} часов.")
    await message.answer(f"✅ Предупреждение (№{current_warnings}) отправлено. Доступ к поддержке для пользователя {user_id} заблокирован на {hours} часов.")
    
    await db_manager.close_support_ticket(ticket_id)
    await state.clear()