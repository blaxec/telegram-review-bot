# file: handlers/referral.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from keyboards import inline
from database import db_manager
from config import Rewards

router = Router()
logger = logging.getLogger(__name__)

async def show_selected_referral_path(message_or_callback: Message | CallbackQuery, bot: Bot):
    """Отображает информацию о реферальной системе."""
    user_id = message_or_callback.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={user_id}"
    referral_earnings = await db_manager.get_referral_earnings(user_id)

    path_description = f"Вы получаете **{Rewards.REFERRAL_REWARD_PERCENT}%** от суммы вознаграждения за каждый успешно выполненный отзыв на Google и Яндекс картах вашими рефералами."

    ref_text = (
        f"🚀 **Ваша реферальная система**\n\n"
        f"{path_description}\n\n"
        f"🔗 **Ссылка для приглашений:**\n"
        f"<code>{referral_link}</code>\n"
        f"(Нажмите на ссылку выше, чтобы скопировать её)\n\n"
        f"💰 Накоплено в копилке: **{referral_earnings:.2f} ⭐**"
    )

    is_message = isinstance(message_or_callback, Message)
    target_message = message_or_callback if is_message else message_or_callback.message

    if not target_message:
        return

    try:
        if is_message:
             await target_message.answer(
                ref_text,
                reply_markup=inline.get_referral_info_keyboard(),
                disable_web_page_preview=True
            )
        else:
            await target_message.edit_text(
                ref_text,
                reply_markup=inline.get_referral_info_keyboard(),
                disable_web_page_preview=True
            )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning(f"Error editing referral message: {e}")
        if not is_message:
            await message_or_callback.answer()


@router.callback_query(F.data == 'profile_referral')
async def referral_entry_point(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Точка входа в реферальную систему."""
    await show_selected_referral_path(callback, bot)

@router.callback_query(F.data == 'profile_referrals_list')
async def show_referrals_list(callback: CallbackQuery):
    """Показывает пользователю список его рефералов."""
    referrals = await db_manager.get_referrals(callback.from_user.id)
    
    if not referrals:
        text = "У вас пока нет приглашенных пользователей."
    else:
        text = "👥 **Ваши рефералы:**\n\n" + "\n".join([f"- @{username}" for username in referrals if username])
        
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_back_to_referral_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == 'profile_claim_referral_stars')
async def claim_referral_stars(callback: CallbackQuery, bot: Bot):
    """Переводит накопленные звезды на основной баланс."""
    user_id = callback.from_user.id
    earnings = await db_manager.get_referral_earnings(user_id)
    
    if earnings > 0:
        await db_manager.claim_referral_earnings(user_id)
        await callback.answer(f"{earnings:.2f} ⭐ переведены на ваш основной баланс!", show_alert=True)
    else:
        await callback.answer("Ваша реферальная копилка пуста.", show_alert=True)
        
    await show_selected_referral_path(callback, bot)