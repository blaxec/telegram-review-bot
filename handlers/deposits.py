# file: handlers/deposits.py
# (Новый файл)
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import DepositStates
from keyboards import inline
from database import db_manager
from config import DEPOSIT_PLANS
from logic.user_notifications import format_timedelta

router = Router()
logger = logging.getLogger(__name__)

async def show_deposits_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    deposits = await db_manager.get_active_user_deposits(user_id)
    total_on_deposits = sum(d.current_balance for d in deposits)

    text = f"🏦 **Депозиты**\n\nВаши активные депозиты: **{total_on_deposits:.2f} ⭐**\n\n"
    if not deposits:
        text += "У вас нет активных вкладов."
    else:
        text += "**Активные вклады:**\n"
        for dep in deposits:
            time_left = dep.closes_at - datetime.utcnow()
            days, rem = divmod(time_left.total_seconds(), 86400)
            hours, _ = divmod(rem, 3600)
            time_left_str = f"осталось {int(days)}д {int(hours)}ч"
            
            plan_name = DEPOSIT_PLANS.get(dep.deposit_plan_id, {}).get("name", "Неизвестный")
            text += f"• План '{plan_name}': **{dep.current_balance:.2f} ⭐**, закроется {dep.closes_at.strftime('%d.%m.%Y %H:%M')} ({time_left_str})\n"

    await callback.message.edit_text(text, reply_markup=inline.get_deposits_menu_keyboard())


@router.callback_query(F.data == 'show_deposits_menu')
async def deposits_entry_point(callback: CallbackQuery):
    await show_deposits_menu(callback)

@router.callback_query(F.data == 'open_new_deposit')
async def open_new_deposit_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.choosing_plan)
    await callback.message.edit_text(
        "Выберите план для нового депозита:",
        reply_markup=inline.get_deposit_plan_selection_keyboard(DEPOSIT_PLANS)
    )

@router.callback_query(F.data.startswith("select_deposit_plan:"), DepositStates.choosing_plan)
async def select_deposit_plan(callback: CallbackQuery, state: FSMContext):
    plan_id = callback.data.split(":")[1]
    plan = DEPOSIT_PLANS.get(plan_id)
    
    if not plan:
        await callback.answer("План не найден.", show_alert=True)
        return

    await state.update_data(selected_plan_id=plan_id)
    await state.set_state(DepositStates.waiting_for_amount)

    text = (
        f"Вы выбрали план **'{plan['name']}'**:\n"
        f"• {plan['description']}\n"
        f"• Срок: {plan['duration_days']} дня(дней)\n"
        f"• Минимальный вклад: {plan['min_amount']:.2f} ⭐\n\n"
        "⚠️ **Внимание!** Вы не сможете снять средства с этого депозита до окончания его срока. Средства блокируются на весь срок!\n\n"
        f"Введите сумму, которую хотите вложить (не менее {plan['min_amount']:.2f} ⭐):"
    )
    prompt_msg = await callback.message.edit_text(text, reply_markup=inline.get_cancel_inline_keyboard("show_deposits_menu"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(DepositStates.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    plan_id = data.get("selected_plan_id")
    plan = DEPOSIT_PLANS.get(plan_id)
    
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Некорректная сумма. Пожалуйста, введите положительное число.")
        return

    user = await db_manager.get_user(message.from_user.id)
    if user.balance < amount:
        await message.answer("❌ Недостаточно средств на балансе!")
        return
    if amount < plan['min_amount']:
        await message.answer(f"❌ Минимальная сумма для этого плана: {plan['min_amount']:.2f} ⭐.")
        return

    await db_manager.create_user_deposit(message.from_user.id, plan_id, amount)
    
    await message.answer(
        f"✅ Ваш депозит '{plan['name']}' на сумму {amount:.2f} ⭐ успешно открыт и будет работать {plan['duration_days']} дня(дней). "
        "Проценты будут начисляться и капитализироваться автоматически. Досрочное снятие невозможно."
    )
    
    if prompt_id := data.get("prompt_message_id"):
        try: await bot.delete_message(message.chat.id, prompt_id)
        except: pass
    await message.delete()

    await state.clear()
    
    dummy_callback = CallbackQuery(id="dummy", from_user=message.from_user, chat_instance="", message=await message.answer("..."))
    await show_deposits_menu(dummy_callback)
    await dummy_callback.message.delete()