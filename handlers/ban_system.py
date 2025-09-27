# file: handlers/ban_system.py

import logging
import asyncio
import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from config import SUPER_ADMIN_ID, Durations, PAYMENT_PROVIDER_TOKEN, PAID_UNBAN_COST_STARS
from keyboards import inline
from logic.user_notifications import format_timedelta
from utils.access_filters import IsSuperAdmin
from states.user_states import UserState
from aiogram.fsm.context import FSMContext

router = Router()
logger = logging.getLogger(__name__)

async def schedule_message_deletion(message: Message, delay: int):
    """Вспомогательная функция для планирования удаления сообщения."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

@router.message(Command("unban_request"))
async def request_unban_start(message: Message, state: FSMContext):
    """Начало процесса подачи запроса на разбан."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
        
    user = await db_manager.get_user(message.from_user.id)

    if not user or not user.is_banned:
        msg = await message.answer("Эта команда доступна только для заблокированных пользователей.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return

    if user.last_unban_request_at:
        time_since_last_request = datetime.datetime.utcnow() - user.last_unban_request_at
        if time_since_last_request < datetime.timedelta(minutes=Durations.COOLDOWN_UNBAN_REQUEST_MINUTES):
            remaining_time = datetime.timedelta(minutes=Durations.COOLDOWN_UNBAN_REQUEST_MINUTES) - time_since_last_request
            msg = await message.answer(f"Вы сможете отправить следующий запрос через: {format_timedelta(remaining_time)}")
            asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
            return
    
    await state.set_state(UserState.UNBAN_AWAITING_REASON)
    prompt_msg = await message.answer(
        "✍️ Пожалуйста, опишите причину, по которой вы считаете, что бан был выдан ошибочно, или почему вас следует разбанить. "
        "Ваше сообщение будет передано администратору."
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.UNBAN_AWAITING_REASON, F.text)
async def process_unban_reason(message: Message, state: FSMContext, bot: Bot):
    """Обработка причины от пользователя и создание запроса."""
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_message_id")
    if prompt_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_msg_id)
        except TelegramBadRequest:
            pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    user_id = message.from_user.id
    reason = message.text
    
    await db_manager.create_unban_request(user_id, reason)
    await db_manager.update_last_unban_request_time(user_id)
    
    await message.answer("✅ Ваш запрос на разбан отправлен главному администратору. Ожидайте решения.")
    
    try:
        await bot.send_message(SUPER_ADMIN_ID, f"🔔 Поступил новый запрос на амнистию! Используйте /amnesty для просмотра.")
    except Exception as e:
        logger.error(f"Failed to notify super admin about new unban request: {e}")
        
    await state.clear()


@router.message(Command("unban"), IsSuperAdmin())
async def unban_user_command(message: Message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
        
    args = message.text.split()
    if len(args) < 2:
        msg = await message.answer("Использование: <code>/unban ID_пользователя_или_@username</code>")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return

    identifier = args[1]
    user_id_to_unban = await db_manager.find_user_by_identifier(identifier)

    if not user_id_to_unban:
        msg = await message.answer(f"❌ Пользователь <code>{identifier}</code> не найден.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return
        
    user_to_unban = await db_manager.get_user(user_id_to_unban)
    if not user_to_unban.is_banned:
        msg = await message.answer(f"Пользователь @{user_to_unban.username} (<code>{user_id_to_unban}</code>) не забанен.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return
        
    success = await db_manager.unban_user(user_id_to_unban)
    if success:
        msg = await message.answer(f"✅ Пользователь @{user_to_unban.username} (<code>{user_id_to_unban}</code>) был разбанен.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        try:
            await message.bot.send_message(user_id_to_unban, "✅ Администратор разбанил вас вручную.")
        except: pass
    else:
        await message.answer("❌ Произошла ошибка при разбане.")

# --- ОБРАБОТЧИКИ ПЛАТЕЖЕЙ ---

@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Подтверждает готовность к приему платежа."""
    # Здесь можно добавить дополнительную логику, например, проверку доступности товара
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    logger.info(f"Pre-checkout query for user {pre_checkout_query.from_user.id} confirmed.")

@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    """Обрабатывает успешный платеж за разбан."""
    user_id = message.from_user.id
    logger.info(f"Successful payment of {message.successful_payment.total_amount} stars received from user {user_id} for unban.")
    
    request = await db_manager.get_unban_request_by_status(user_id, 'payment_pending')
    
    if not request:
        logger.error(f"CRITICAL: Successful payment from {user_id}, but no 'payment_pending' unban request found!")
        await message.answer("Спасибо за оплату! Однако, произошла ошибка при поиске вашего запроса. Пожалуйста, обратитесь в поддержку.")
        return

    # Разбаниваем пользователя
    await db_manager.unban_user(user_id)
    # Помечаем запрос как одобренный
    await db_manager.update_unban_request_status(request.id, 'approved', SUPER_ADMIN_ID)
    
    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "Вы были разблокированы и снова можете пользоваться всеми функциями бота."
    )