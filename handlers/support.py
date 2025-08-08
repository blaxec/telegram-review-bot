# file: handlers/support.py

import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_IDS
from database import db_manager

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == 'Поддержка', UserState.MAIN_MENU)
async def support_handler(message: Message, state: FSMContext):
    """Начало диалога с поддержкой."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    
    await state.set_state(UserState.SUPPORT_AWAITING_QUESTION)
    await message.answer(
        "Пожалуйста, опишите вашу проблему или задайте вопрос одним сообщением. Мы передадим его администратору.",
        reply_markup=inline.get_cancel_inline_keyboard()
    )

@router.message(UserState.SUPPORT_AWAITING_QUESTION)
async def process_question(message: Message, state: FSMContext, bot: Bot):
    """Обработка вопроса от пользователя и отправка его админам."""
    if not message.text:
        await message.answer("Пожалуйста, отправьте ваш вопрос в виде текста.")
        return

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)
    
    user_id = message.from_user.id
    username = message.from_user.username or "Без @username"
    
    admin_text = (
        f"🚨 Новый вопрос в поддержку от пользователя @{username} (ID: `{user_id}`)\n\n"
        f"**Вопрос:**\n_{message.text}_"
    )
    
    sent_messages = {}
    success_sent_count = 0
    # Отправляем вопрос всем админам
    for i, admin_id in enumerate(ADMIN_IDS):
        try:
            sent_msg = await bot.send_message(admin_id, admin_text)
            sent_messages[i] = sent_msg.message_id
            success_sent_count += 1
        except Exception as e:
            logger.error(f"Не удалось отправить вопрос в поддержку админу {admin_id}: {e}")
            sent_messages[i] = None
    
    if success_sent_count > 0:
        # Создаем тикет в базе данных, только если удалось отправить хотя бы одному админу
        ticket = await db_manager.create_support_ticket(
            user_id=user_id,
            username=username,
            question=message.text,
            admin_message_ids=sent_messages
        )
        # Обновляем клавиатуру у админов, добавляя ID тикета
        for i, admin_id in enumerate(ADMIN_IDS):
            if sent_messages[i]:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=admin_id,
                        message_id=sent_messages[i],
                        reply_markup=inline.get_support_admin_keyboard(ticket.id)
                    )
                except Exception as e:
                    logger.error(f"Не удалось обновить клавиатуру у админа {admin_id}: {e}")

        await message.answer("Ваш вопрос отправлен администраторам. Пожалуйста, ожидайте ответа.")
    else:
        await message.answer("❌ К сожалению, не удалось связаться с поддержкой. Попробуйте снова позже.")

@router.callback_query(F.data.startswith("support_answer:"))
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
        except:
            pass
        return

    # Уведомляем других админов
    other_admin_ids = [aid for aid in ADMIN_IDS if aid != admin_id]
    for other_admin_id in other_admin_ids:
        # Определяем, какой message_id принадлежит другому админу
        msg_id_to_edit = ticket.admin_message_id_1 if ADMIN_IDS.index(other_admin_id) == 0 else ticket.admin_message_id_2
        if msg_id_to_edit:
            try:
                original_text = (
                    f"🚨 Новый вопрос в поддержку от пользователя @{ticket.username} (ID: `{ticket.user_id}`)\n\n"
                    f"**Вопрос:**\n_{ticket.question}_"
                )
                await bot.edit_message_text(
                    text=f"{original_text}\n\n*Взят в работу администратором @{admin_username}*",
                    chat_id=other_admin_id,
                    message_id=msg_id_to_edit,
                    reply_markup=None
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение у админа {other_admin_id}: {e}")

    # Редактируем сообщение у того, кто нажал
    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        f"✅ Вы отвечаете на этот вопрос. Отправьте ответ следующим сообщением.",
        reply_markup=None
    )
    
    await state.set_state(AdminState.SUPPORT_AWAITING_ANSWER)
    await state.update_data(support_ticket_id=ticket_id, support_user_id=ticket.user_id)
    
    await callback.answer()

@router.message(AdminState.SUPPORT_AWAITING_ANSWER)
async def admin_send_answer(message: Message, state: FSMContext, bot: Bot):
    """Админ отправляет ответ, который пересылается пользователю."""
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
        f"📩 **Вам пришел ответ от поддержки:**\n\n"
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