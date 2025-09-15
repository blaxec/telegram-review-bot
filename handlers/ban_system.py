# file: handlers/ban_system.py

import logging
import asyncio
import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from config import ADMIN_ID_1, ADMIN_IDS, Durations
from keyboards import inline
from logic.user_notifications import format_timedelta

router = Router()
logger = logging.getLogger(__name__)
ADMINS = set(ADMIN_IDS)

async def schedule_message_deletion(message: Message, delay: int):
    """Вспомогательная функция для планирования удаления сообщения."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

@router.message(Command("unban_request"))
async def request_unban(message: Message, bot: Bot):
    # Планируем удаление команды пользователя для чистоты чата
    asyncio.create_task(schedule_message_deletion(message, Durations.DELETE_UNBAN_REQUEST_DELAY))

    user = await db_manager.get_user(message.from_user.id)

    if not user or not user.is_banned:
        msg = await message.answer("Эта команда доступна только для заблокированных пользователей.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
        return

    # Проверка кулдауна
    if user.last_unban_request_at:
        time_since_last_request = datetime.datetime.utcnow() - user.last_unban_request_at
        if time_since_last_request < datetime.timedelta(minutes=Durations.COOLDOWN_UNBAN_REQUEST_MINUTES):
            remaining_time = datetime.timedelta(minutes=Durations.COOLDOWN_UNBAN_REQUEST_MINUTES) - time_since_last_request
            msg = await message.answer(f"Вы сможете отправить следующий запрос через: {format_timedelta(remaining_time)}")
            asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
            return
    
    admin_notification = (
        f"🚨 <b>Запрос на амнистию!</b> 🚨\n\n"
        f"Пользователь @{user.username} (ID: <code>{user.id}</code>) просит о разбане."
    )
    
    try:
        await bot.send_message(
            chat_id=ADMIN_ID_1,
            text=admin_notification,
            reply_markup=inline.get_unban_request_keyboard(user.id)
        )
        # Обновляем время последнего запроса в БД
        await db_manager.update_last_unban_request_time(user.id)
        msg = await message.answer("✅ Ваш запрос на разбан отправлен главному администратору. Ожидайте решения.")
        asyncio.create_task(schedule_message_deletion(msg, Durations.DELETE_ADMIN_REPLY_DELAY))
    except Exception as e:
        logger.error(f"Не удалось отправить запрос на разбан админу {ADMIN_ID_1}: {e}")
        await message.answer("❌ Не удалось отправить запрос. Попробуйте позже.")


@router.message(Command("unban"), F.from_user.id.in_(ADMINS))
async def unban_user_command(message: Message):
    # Удаляем команду админа
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
    else:
        await message.answer("❌ Произошла ошибка при разбане.")


@router.callback_query(F.data.startswith("unban_approve:"))
async def approve_unban_request(callback: CallbackQuery, bot: Bot):
    user_id_to_unban = int(callback.data.split(":")[1])
    
    success = await db_manager.unban_user(user_id_to_unban)
    
    if not success:
        await callback.answer("❌ Не удалось найти пользователя для разбана.", show_alert=True)
        return

    try:
        await bot.send_message(user_id_to_unban, "🎉 <b>Хорошие новости!</b>\n\nГлавный администратор одобрил ваш запрос. Вы были разблокированы и снова можете пользоваться ботом.")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id_to_unban} о разбане: {e}")

    await callback.answer("✅ Пользователь разбанен.", show_alert=True)
    if callback.message:
        await callback.message.edit_text(f"{callback.message.text}\n\n<b>Статус: РАЗБАНЕН</b>", reply_markup=None)

@router.callback_query(F.data.startswith("unban_reject:"))
async def reject_unban_request(callback: CallbackQuery):
    await callback.answer("Запрос на разбан отклонен.", show_alert=True)
    if callback.message:
        await callback.message.edit_text(f"{callback.message.text}\n\n<b>Статус: ОТКЛОНЕНО</b>", reply_markup=None)