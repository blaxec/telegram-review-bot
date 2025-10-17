# file: handlers/donations.py

import logging
import datetime
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import DonationStates
from keyboards import inline
from database import db_manager
from config import NOVICE_HELP_AMOUNT
from logic.user_notifications import format_timedelta

router = Router()
logger = logging.getLogger(__name__)

async def show_donation_menu(callback: CallbackQuery, bot: Bot):
    fund_balance_str = await db_manager.get_system_setting('donation_fund_balance')
    fund_balance = float(fund_balance_str) if fund_balance_str else 0.0
    top_donators = await db_manager.get_top_donators(limit=5)
    
    leaderboard_text = ""
    if not top_donators:
        leaderboard_text = "Пока никто не сделал пожертвований."
    else:
        emojis = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, (user_id, amount) in enumerate(top_donators):
            try:
                user_info = await bot.get_chat(user_id)
                display_name = f"@{user_info.username}" if user_info.username else f"{user_info.first_name}"
            except Exception:
                display_name = f"ID {user_id}"
            leaderboard_text += f"{emojis[i]} {display_name} - {amount:.2f} ⭐\n"
            
    menu_text = (
        "💖 **Фонд Помощи Новичкам**\n\n"
        "Здесь вы можете пожертвовать звезды, чтобы помочь новым пользователям освоиться в нашем боте. "
        "Ваши пожертвования напрямую идут в общую копилку, из которой новички могут получать небольшую ежедневную поддержку.\n\n"
        f"Сейчас в фонде: **{fund_balance:.2f} ⭐**\n\n"
        "**Доска Почета (топ-5 меценатов):**\n"
        f"{leaderboard_text}"
    )
    
    await callback.message.edit_text(menu_text, reply_markup=inline.get_donation_menu_keyboard())

@router.callback_query(F.data == 'profile_donate')
async def donation_entry(callback: CallbackQuery, bot: Bot):
    await show_donation_menu(callback, bot)

@router.callback_query(F.data == 'make_donation')
async def make_donation_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DonationStates.waiting_for_donation_amount)
    prompt_msg = await callback.message.edit_text(
        "Введите сумму, которую вы хотите пожертвовать в Фонд Помощи:",
        reply_markup=inline.get_cancel_inline_keyboard("profile_donate")
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(DonationStates.waiting_for_donation_amount)
async def process_donation_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Некорректная сумма. Пожалуйста, введите положительное число.")
        return

    user = await db_manager.get_user(message.from_user.id)
    if not user or user.balance < amount:
        await message.answer("❌ Недостаточно средств на балансе!")
        return
        
    await db_manager.process_donation(message.from_user.id, amount)
    
    await message.answer(f"💖 Спасибо за ваше пожертвование в {amount:.2f} ⭐! Ваша помощь очень ценна для новичков.")
    
    data = await state.get_data()
    if prompt_id := data.get("prompt_message_id"):
        try: await bot.delete_message(message.chat.id, prompt_id)
        except TelegramBadRequest: pass
    try: await message.delete()
    except TelegramBadRequest: pass
    
    await state.clear()
    
    dummy_callback_message = await message.answer("...")
    dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=dummy_callback_message)
    await show_donation_menu(dummy_callback, bot)
    await dummy_callback_message.delete()

@router.callback_query(F.data == 'get_daily_help')
async def get_daily_help(callback: CallbackQuery, bot: Bot):
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user or user.first_task_completed:
        await callback.answer("Вы уже не новичок и можете зарабатывать самостоятельно! 🎉", show_alert=True)
        return

    if user.last_help_request_at and (datetime.datetime.utcnow() - user.last_help_request_at) < datetime.timedelta(hours=24):
        remaining = (user.last_help_request_at + datetime.timedelta(hours=24)) - datetime.datetime.utcnow()
        await callback.answer(f"Вы уже получали помощь сегодня. Следующая выплата будет доступна через {format_timedelta(remaining)}.", show_alert=True)
        return
        
    success = await db_manager.process_help_request(user.id, NOVICE_HELP_AMOUNT)
    
    if success:
        await callback.answer(f"✅ Вы получили {NOVICE_HELP_AMOUNT} ⭐ из Фонда Помощи!", show_alert=True)
        await bot.send_message(user.id, "Следующая выплата будет доступна через 24 часа.")
    else:
        await callback.answer("😔 К сожалению, в Фонде Помощи сейчас недостаточно средств. Попробуйте позже.", show_alert=True)