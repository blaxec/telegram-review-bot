# file: handlers/profile.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, User, InputMediaPhoto, InputMediaVideo, InputMediaAnimation
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager
from config import WITHDRAWAL_CHANNEL_ID, Limits, TRANSFER_COMMISSION_PERCENT
from logic.user_notifications import format_timedelta

router = Router()
logger = logging.getLogger(__name__)

async def delete_prompt_message(message: Message, state: FSMContext):
    """Удаляет только предыдущее сообщение-приглашение от бота."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_message_id)
            await state.update_data(prompt_message_id=None)
        except TelegramBadRequest:
            pass

# --- Главный экран профиля и навигация ---
async def show_profile_menu(message_or_callback: Message | CallbackQuery, state: FSMContext, bot: Bot):
    """Универсальная функция для отображения меню профиля."""
    await state.set_state(UserState.MAIN_MENU)
    user_id = message_or_callback.from_user.id
    
    await db_manager.ensure_user_exists(user_id, message_or_callback.from_user.username)
    
    user = await db_manager.get_user(user_id)
    if not user:
        await bot.send_message(user_id, "Произошла критическая ошибка, не удалось найти или создать ваш профиль. Попробуйте /start")
        return

    balance, hold_balance = user.balance, user.hold_balance
    referrer_info = await db_manager.get_referrer_info(user_id)
    
    profile_text = (
        f"✨ Ваш <b>Профиль</b> ✨\n\n"
        f"Вас пригласил: {referrer_info}\n"
        f"Баланс звезд: {balance:.2f} ⭐\n"
        f"В холде: {hold_balance:.2f} ⭐"
    )
    
    keyboard = inline.get_profile_keyboard()
    
    is_message = isinstance(message_or_callback, Message)
    target_message = message_or_callback if is_message else message_or_callback.message

    if not target_message: return

    if is_message:
        await target_message.answer(profile_text, reply_markup=keyboard)
    else:
        try:
            await target_message.edit_text(profile_text, reply_markup=keyboard)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await message_or_callback.answer()
            else:
                logger.warning(f"Could not edit profile message, sending new. Error: {e}")
                await target_message.delete()
                await bot.send_message(chat_id=target_message.chat.id, text=profile_text, reply_markup=keyboard)


@router.message(Command("stars"))
@router.message(F.text == '👤 Профиль', UserState.MAIN_MENU)
async def profile_handler(message: Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await show_profile_menu(message, state, bot)

@router.callback_query(F.data == 'go_profile')
async def go_profile_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await show_profile_menu(callback, state, bot)

@router.callback_query(F.data == 'profile_history')
async def show_operation_history(callback: CallbackQuery):
    """Показывает последние операции пользователя за 24 часа."""
    user_id = callback.from_user.id
    operations = await db_manager.get_operation_history(user_id)

    if not operations:
        text = "📜 <b>История операций за последние 24 часа:</b>\n\nОпераций не найдено."
    else:
        text = "📜 <b>История операций за последние 24 часа:</b>\n\n"
        for op in operations:
            time_str = op.created_at.strftime('%H:%M:%S UTC')
            amount_str = f"{op.amount:+.2f} ⭐" if op.amount > 0 else f"{op.amount:.2f} ⭐"
            
            op_map = {
                "REVIEW_APPROVED": "✅ Одобрен отзыв", "PROMO_ACTIVATED": "🎁 Активация промокода",
                "WITHDRAWAL": "📤 Запрос на вывод", "FINE": "💸 Штраф",
                "TRANSFER_SENT": "➡️ Перевод звезд", "TRANSFER_RECEIVED": "⬅️ Получение звезд",
                "TOP_REWARD": "🏆 Награда из топа"
            }
            op_description = op_map.get(op.operation_type, "Неизвестная операция")
            
            description_suffix = f" ({op.description})" if op.description else ""
            text += f"<code>{time_str}</code>: {op_description} {amount_str}{description_suffix}\n"
    
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_operation_history_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == 'profile_transfer')
async def initiate_transfer(callback: CallbackQuery, state: FSMContext, **kwargs):
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    if float(balance) < Limits.MIN_TRANSFER_AMOUNT:
        await callback.answer(f"Недостаточно звезд на балансе для перевода (минимум {Limits.MIN_TRANSFER_AMOUNT} ⭐).", show_alert=True)
        return

    await state.set_state(UserState.TRANSFER_AMOUNT_OTHER)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            f"Сколько звезд вы хотите передать? (Минимум {Limits.MIN_TRANSFER_AMOUNT} ⭐)\n"
            f"Комиссия за перевод: {TRANSFER_COMMISSION_PERCENT}%",
            reply_markup=inline.get_cancel_to_profile_keyboard()
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)

async def process_transfer_amount(amount: float, message: Message, state: FSMContext):
    balance, _ = await db_manager.get_user_balance(message.from_user.id)
    commission = amount * (TRANSFER_COMMISSION_PERCENT / 100)
    total_deduction = amount + commission

    await delete_prompt_message(message, state)

    if total_deduction > float(balance):
        prompt_msg = await message.answer(f"Недостаточно звезд. Ваш баланс: {balance:.2f} ⭐. С учетом комиссии ({commission:.2f} ⭐) вам нужно {total_deduction:.2f} ⭐.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await state.update_data(transfer_amount=amount)
    await state.set_state(UserState.TRANSFER_RECIPIENT)
    prompt_msg = await message.answer(
        "Кому вы хотите передать звезды? Укажите никнейм (@username) или ID пользователя.",
        reply_markup=inline.get_cancel_to_profile_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.TRANSFER_AMOUNT_OTHER, F.text)
async def transfer_other_amount_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < Limits.MIN_TRANSFER_AMOUNT: raise ValueError
    except (ValueError, TypeError):
        await delete_prompt_message(message, state)
        prompt_msg = await message.answer(f"Неверный формат. Пожалуйста, введите положительное число (минимум {Limits.MIN_TRANSFER_AMOUNT}).")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    finally:
        await message.delete()
    await process_transfer_amount(amount, message, state)

@router.message(UserState.TRANSFER_RECIPIENT, F.text)
async def process_transfer_recipient(message: Message, state: FSMContext):
    recipient_id = await db_manager.find_user_by_identifier(message.text)
    await delete_prompt_message(message, state)
    await message.delete()
    
    if not recipient_id or recipient_id == message.from_user.id:
        prompt_msg = await message.answer("Пользователь не найден или вы пытаетесь отправить звезды себе. Попробуйте еще раз.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await state.update_data(recipient_id=recipient_id)
    
    # ИЗМЕНЕНИЕ: Переход к подтверждению вместо комментария
    await ask_for_transfer_confirmation(message, state)

async def ask_for_transfer_confirmation(message: Message, state: FSMContext):
    """Показывает экран подтверждения перевода с расчетом комиссии."""
    data = await state.get_data()
    amount = data['transfer_amount']
    recipient_id = data['recipient_id']
    
    recipient_user = await db_manager.get_user(recipient_id)
    recipient_info = f"@{recipient_user.username}" if recipient_user and recipient_user.username else f"ID: {recipient_id}"
    
    commission = amount * (TRANSFER_COMMISSION_PERCENT / 100)
    total_to_deduct = amount + commission

    confirmation_text = (
        f"<b>Подтверждение перевода</b>\n\n"
        f"Вы собираетесь перевести <b>{amount:.2f} ⭐</b> пользователю {recipient_info}.\n\n"
        f"Сумма перевода: {amount:.2f} ⭐\n"
        f"Комиссия ({TRANSFER_COMMISSION_PERCENT}%): {commission:.2f} ⭐\n"
        f"<b>Итого к списанию: {total_to_deduct:.2f} ⭐</b>\n\n"
        "Подтверждаете операцию?"
    )
    
    await state.set_state(UserState.TRANSFER_CONFIRMATION)
    prompt_msg = await message.answer(
        confirmation_text,
        reply_markup=inline.get_transfer_confirmation_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data == 'transfer_confirm', UserState.TRANSFER_CONFIRMATION)
async def process_transfer_confirmed(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка подтверждения перевода."""
    if callback.message:
        await callback.message.delete()
    await finish_transfer(callback.from_user, state, bot)

async def finish_transfer(user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    sender_id, sender_username = user.id, user.username
    recipient_id, amount = data['recipient_id'], data['transfer_amount']
    
    success = await db_manager.transfer_stars(sender_id, recipient_id, amount)

    if not success:
        await bot.send_message(sender_id, "Произошла ошибка при переводе. Попробуйте снова.", reply_markup=reply.get_main_menu_keyboard())
        await state.clear()
        return

    notification_text = f"✨ Вам переведены <b>{amount:.2f} ⭐</b> от @{sender_username}!"
        
    try:
        await bot.send_message(recipient_id, notification_text)
    except Exception as e:
        logger.error(f"Не удалось уведомить о переводе {recipient_id}: {e}")

    await bot.send_message(sender_id, "✅ Звезды успешно переведены!", reply_markup=reply.get_main_menu_keyboard())
    await state.clear()


@router.callback_query(F.data == 'profile_withdraw')
async def initiate_withdraw(callback: CallbackQuery, state: FSMContext, **kwargs):
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    if float(balance) < Limits.MIN_WITHDRAWAL_AMOUNT:
        await callback.answer(f"Минимальная сумма для вывода {Limits.MIN_WITHDRAWAL_AMOUNT:.2f} звезд. Ваш баланс: {balance:.2f} ⭐.", show_alert=True)
        return
    
    if not WITHDRAWAL_CHANNEL_ID:
        await callback.answer("Функция вывода временно недоступна. Администратор не настроил канал для выплат.", show_alert=True)
        logger.warning("Attempted to withdraw, but WITHDRAWAL_CHANNEL_ID is not set.")
        return

    await state.set_state(UserState.WITHDRAW_AMOUNT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Сколько звезд вы хотите вывести?",
            reply_markup=inline.get_withdraw_amount_keyboard()
        )
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data.startswith('withdraw_amount_'), UserState.WITHDRAW_AMOUNT)
async def withdraw_predefined_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split('_')[-1]
    
    if amount_str == 'other':
        await state.set_state(UserState.WITHDRAW_AMOUNT_OTHER)
        if callback.message:
            prompt_msg = await callback.message.edit_text(f"Введите сумму для вывода (минимум {Limits.MIN_WITHDRAWAL_AMOUNT:.2f}):", reply_markup=inline.get_cancel_to_profile_keyboard())
            if prompt_msg:
                await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    amount = float(amount_str)
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    if float(balance) < amount:
        await callback.answer(f"Недостаточно звезд. Ваш баланс: {balance:.2f} ⭐", show_alert=True)
        return

    await state.update_data(withdraw_amount=amount)
    await state.set_state(UserState.WITHDRAW_RECIPIENT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Кому вы хотите отправить подарок?",
            reply_markup=inline.get_withdraw_recipient_keyboard()
        )
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.WITHDRAW_AMOUNT_OTHER, F.text)
async def withdraw_other_amount_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < Limits.MIN_WITHDRAWAL_AMOUNT:
            raise ValueError
    except (ValueError, TypeError):
        await delete_prompt_message(message, state)
        await message.delete()
        prompt_msg = await message.answer(f"Неверный формат. Введите число не менее {Limits.MIN_WITHDRAWAL_AMOUNT:.2f}.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    
    balance, _ = await db_manager.get_user_balance(message.from_user.id)
    if float(balance) < amount:
        await delete_prompt_message(message, state)
        await message.delete()
        prompt_msg = await message.answer(f"Недостаточно звезд. Ваш баланс: {balance:.2f} ⭐")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await delete_prompt_message(message, state)
    await message.delete()
    await state.update_data(withdraw_amount=amount)
    await state.set_state(UserState.WITHDRAW_RECIPIENT)
    prompt_msg = await message.answer(
        "Кому вы хотите отправить подарок?",
        reply_markup=inline.get_withdraw_recipient_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    
async def _create_and_notify_withdrawal(user: User, amount: float, recipient_info: str, comment: str | None, bot: Bot, state: FSMContext):
    """Вспомогательная функция для создания запроса и отправки уведомления в канал."""
    request_id = await db_manager.create_withdrawal_request(user.id, amount, recipient_info, comment)

    if request_id is None:
        await bot.send_message(user.id, "❌ Произошла ошибка при создании запроса. Возможно, на балансе недостаточно средств. Попробуйте снова.")
        await state.clear()
        return

    admin_message = (
        f"🚨 <b>Новый запрос на вывод средств!</b> 🚨\n\n"
        f"👤 <b>Отправитель:</b> @{user.username} (ID: <code>{user.id}</code>)\n"
        f"💰 <b>Сумма:</b> {amount:.2f} ⭐\n"
        f"🎯 <b>Получатель:</b> {recipient_info}\n"
    )
    if comment:
        admin_message += f"💬 <b>Комментарий:</b> {comment}\n"
    
    admin_message += f"\nЗапрос ID: <code>{request_id}</code>"

    try:
        await bot.send_message(
            chat_id=WITHDRAWAL_CHANNEL_ID,
            text=admin_message,
            reply_markup=inline.get_admin_withdrawal_keyboard(request_id)
        )
        await bot.send_message(user.id, "✅ Ваш запрос на вывод средств создан и отправлен на проверку администратору.\n\nСледить за статусом можно в нашем <a href='https://t.me/conclusions_starref'>канале выплат</a>.")
    except Exception as e:
        logger.error(f"Не удалось отправить запрос в канал выплат {WITHDRAWAL_CHANNEL_ID}: {e}", exc_info=True)
        # Возвращаем звезды, если не удалось уведомить админов
        await db_manager.update_balance(user.id, amount, op_type="WITHDRAWAL", description="Возврат из-за ошибки отправки")
        await bot.send_message(user.id, "❌ Не удалось отправить запрос администратору. Вероятно, бот не добавлен в канал выплат. Ваши звезды возвращены на баланс.")
    
    await state.clear()

@router.callback_query(F.data.startswith('withdraw_recipient_'), UserState.WITHDRAW_RECIPIENT)
async def process_withdraw_recipient(callback: CallbackQuery, state: FSMContext, bot: Bot):
    recipient_type = callback.data.split('_')[-1]
    data = await state.get_data()
    amount = data['withdraw_amount']
    
    if callback.message:
        await callback.message.delete()

    if recipient_type == 'self':
        await _create_and_notify_withdrawal(callback.from_user, amount, "Себе", None, bot, state)
    elif recipient_type == 'other':
        await state.set_state(UserState.WITHDRAW_USER_ID)
        prompt_msg = await bot.send_message(
            callback.from_user.id,
            "Укажите никнейм или ID пользователя, которому нужно отправить подарок.",
            reply_markup=inline.get_cancel_to_profile_keyboard()
        )
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.WITHDRAW_USER_ID, F.text)
async def process_withdraw_user_id(message: Message, state: FSMContext):
    await delete_prompt_message(message, state)
    await message.delete()
    recipient_id = await db_manager.find_user_by_identifier(message.text)
    if not recipient_id or recipient_id == message.from_user.id:
        prompt_msg = await message.answer("Пользователь не найден или вы пытаетесь отправить подарок себе. Попробуйте еще раз.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
        
    await state.update_data(withdraw_recipient_id=recipient_id)
    await state.set_state(UserState.WITHDRAW_ASK_COMMENT)
    prompt_msg = await message.answer(
        "Хотите оставить комментарий к подарку?",
        reply_markup=inline.get_ask_comment_keyboard(prefix='withdraw')
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data == 'withdraw_ask_comment_no', UserState.WITHDRAW_ASK_COMMENT)
async def process_withdraw_no_comment(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.message:
        await callback.message.delete()
    await finish_withdraw(callback.from_user, state, bot, comment=None)

@router.callback_query(F.data == 'withdraw_ask_comment_yes', UserState.WITHDRAW_ASK_COMMENT)
async def process_withdraw_yes_comment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.WITHDRAW_COMMENT_INPUT)
    if callback.message:
        prompt_msg = await callback.message.edit_text("Введите ваш комментарий к подарку:")
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.WITHDRAW_COMMENT_INPUT, F.text)
async def process_withdraw_comment_input(message: Message, state: FSMContext, bot: Bot):
    await delete_prompt_message(message, state)
    await message.delete()
    await finish_withdraw(message.from_user, state, bot, comment=message.text)

async def finish_withdraw(user: User, state: FSMContext, bot: Bot, comment: str | None):
    data = await state.get_data()
    amount = data['withdraw_amount']
    recipient_id = data.get('withdraw_recipient_id')
    
    recipient_user = await db_manager.get_user(recipient_id)
    recipient_info = f"@{recipient_user.username}" if recipient_user and recipient_user.username else f"ID: {recipient_id}"

    await _create_and_notify_withdrawal(user, amount, recipient_info, comment, bot, state)

@router.callback_query(F.data == 'profile_hold')
async def show_hold_info(callback: CallbackQuery, state: FSMContext, **kwargs):
    reviews_in_hold = await db_manager.get_user_hold_reviews(callback.from_user.id)
    if not reviews_in_hold:
        text = "⏳ Ваши отзывы в холде:\n\nУ вас нет отзывов в холде."
    else:
        text = "⏳ Ваши отзывы в холде:\n\n"
        review_lines = [f"- {review.amount:.2f} ⭐ ({review.platform}) до {review.hold_until.strftime('%d.%m.%Y %H:%M')} UTC" for review in reviews_in_hold]
        text += "\n".join(review_lines)
    
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=inline.get_back_to_profile_keyboard())
        except TelegramBadRequest:
            pass

@router.callback_query(F.data == 'cancel_to_profile')
async def cancel_to_profile_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Возвращает в меню профиля из любого FSM."""
    await state.clear()
    await show_profile_menu(callback, state, bot)