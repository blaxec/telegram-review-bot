# file: handlers/ban_system.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database import db_manager
from config import ADMIN_ID_1, ADMIN_IDS
from keyboards import inline

router = Router()
logger = logging.getLogger(__name__)
ADMINS = set(ADMIN_IDS)

@router.message(Command("unban_request"))
async def request_unban(message: Message, bot: Bot):
    user = await db_manager.get_user(message.from_user.id)

    if not user or not user.is_banned:
        await message.answer("Эта команда доступна только для заблокированных пользователей.")
        return

    admin_notification = (
        f"🚨 **Запрос на амнистию!** 🚨\n\n"
        f"Пользователь @{user.username} (ID: <code>{user.id}</code>) просит о разбане."
    )
    
    try:
        await bot.send_message(
            chat_id=ADMIN_ID_1,
            text=admin_notification,
            reply_markup=inline.get_unban_request_keyboard(user.id)
        )
        await message.answer("✅ Ваш запрос на разбан отправлен главному администратору. Ожидайте решения.")
    except Exception as e:
        logger.error(f"Не удалось отправить запрос на разбан админу {ADMIN_ID_1}: {e}")
        await message.answer("❌ Не удалось отправить запрос. Попробуйте позже.")


# ИЗМЕНЕНИЕ: Новая команда /unban для администраторов
@router.message(Command("unban"), F.from_user.id.in_(ADMINS))
async def unban_user_command(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: <code>/unban ID_пользователя_или_@username</code>")
        return

    identifier = args[1]
    user_id_to_unban = await db_manager.find_user_by_identifier(identifier)

    if not user_id_to_unban:
        await message.answer(f"❌ Пользователь <code>{identifier}</code> не найден.")
        return
        
    user_to_unban = await db_manager.get_user(user_id_to_unban)
    if not user_to_unban.is_banned:
        await message.answer(f"Пользователь @{user_to_unban.username} (<code>{user_id_to_unban}</code>) не забанен.")
        return
        
    success = await db_manager.unban_user(user_id_to_unban)
    if success:
        await message.answer(f"✅ Пользователь @{user_to_unban.username} (<code>{user_id_to_unban}</code>) был разбанен.")
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
        await bot.send_message(user_id_to_unban, "🎉 **Хорошие новости!**\n\nГлавный администратор одобрил ваш запрос. Вы были разблокированы и снова можете пользоваться ботом.")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id_to_unban} о разбане: {e}")

    await callback.answer("✅ Пользователь разбанен.", show_alert=True)
    if callback.message:
        await callback.message.edit_text(f"{callback.message.text}\n\n*Статус: РАЗБАНЕН*", reply_markup=None)

@router.callback_query(F.data.startswith("unban_reject:"))
async def reject_unban_request(callback: CallbackQuery):
    user_id_to_reject = int(callback.data.split(":")[1])
    await callback.answer("Запрос на разбан отклонен.", show_alert=True)
    if callback.message:
        await callback.message.edit_text(f"{callback.message.text}\n\n*Статус: ОТКЛОНЕНО*", reply_markup=None)