
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from states.user_states import AdminState
from keyboards import inline, reply
from config import ADMIN_IDS

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
    
    # Сохраняем ID сообщения с вопросом, чтобы потом на него ответить
    question_message_id = message.message_id
    user_id = message.from_user.id
    username = message.from_user.username or "Без @username"

    admin_text = (
        f"🚨 Новый вопрос в поддержку от пользователя @{username} (ID: `{user_id}`)\n\n"
        f"**Вопрос:**\n_{message.text}_"
    )
    
    # Отправляем вопрос всем админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=inline.get_support_admin_keyboard(user_id, question_message_id)
            )
        except Exception as e:
            logger.error(f"Не удалось отправить вопрос в поддержку админу {admin_id}: {e}")
            
    await message.answer("Ваш вопрос отправлен администраторам. Пожалуйста, ожидайте ответа.")

@router.callback_query(F.data.startswith("support_answer:"))
async def admin_claim_question(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Админ нажимает кнопку, чтобы ответить на вопрос."""
    _, user_id_str, question_msg_id_str = callback.data.split(":")
    user_id = int(user_id_str)
    
    admin_username = callback.from_user.username or "Администратор"
    
    # Редактируем сообщение у всех админов, чтобы показать, что вопрос взят в работу
    for admin_id in ADMIN_IDS:
        try:
            # Мы не знаем message_id у второго админа, поэтому редактируем только у того, кто нажал
            if admin_id == callback.from_user.id:
                 await callback.message.edit_text(
                    f"{callback.message.text}\n\n"
                    f"✅ Вы отвечаете на этот вопрос.",
                    reply_markup=None
                )
            else:
                # Уведомляем другого админа
                await bot.send_message(
                    admin_id,
                    f"Вопрос от пользователя ID {user_id} был взят в работу администратором @{admin_username}."
                )
        except TelegramBadRequest:
            # Ошибка, если сообщение уже было изменено или удалено
            pass
        except Exception as e:
            logger.warning(f"Не удалось уведомить админа {admin_id} о взятии вопроса в работу: {e}")

    # Устанавливаем состояние для админа и сохраняем, кому отвечать
    await state.set_state(AdminState.SUPPORT_AWAITING_ANSWER)
    await state.update_data(support_user_id=user_id, support_question_msg_id=int(question_msg_id_str))
    
    await callback.answer("Введите ваш ответ на вопрос пользователя.", show_alert=True)

@router.message(AdminState.SUPPORT_AWAITING_ANSWER)
async def admin_send_answer(message: Message, state: FSMContext, bot: Bot):
    """Админ отправляет ответ, который пересылается пользователю."""
    if not message.text:
        await message.answer("Пожалуйста, введите ответ текстом.")
        return

    data = await state.get_data()
    user_id = data.get("support_user_id")
    question_msg_id = data.get("support_question_msg_id")
    
    if not user_id:
        await message.answer("Произошла ошибка: не найден ID пользователя для ответа. Состояние сброшено.")
        await state.clear()
        return

    user_text = (
        f"📩 **Вам пришел ответ от поддержки:**\n\n"
        f"{message.text}"
    )
    
    try:
        # Отвечаем пользователю прямо на его сообщение с вопросом
        await bot.send_message(user_id, user_text, reply_to_message_id=question_msg_id)
        await message.answer("✅ Ваш ответ успешно отправлен пользователю.")
    except TelegramBadRequest:
        # Если исходное сообщение удалено, просто отправляем новое
        await bot.send_message(user_id, user_text)
        await message.answer("✅ Ваш ответ успешно отправлен пользователю (исходный вопрос был удален).")
    except Exception as e:
        logger.error(f"Не удалось отправить ответ поддержки пользователю {user_id}: {e}")
        await message.answer("❌ Не удалось отправить ответ пользователю. Возможно, он заблокировал бота.")

    await state.clear()