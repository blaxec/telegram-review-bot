# file: handlers/profile.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, User
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager
from config import WITHDRAWAL_CHANNEL_ID, Limits

router = Router()
logger = logging.getLogger(__name__)

async def delete_previous_messages(message: Message, state: FSMContext):
    """Вспомогательная функция для удаления старых сообщений."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_message_id)
        except TelegramBadRequest:
            pass
    try:
        await message.delete()
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
        f"Баланс звезд: {balance} ⭐\n"
        f"В холде: {hold_balance} ⭐"
    )
    
    keyboard = inline.get_profile_keyboard()
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(profile_text, reply_markup=keyboard)
    else: 
        try:
            if message_or_callback.message:
                await message_or_callback.message.edit_text(profile_text, reply_markup=keyboard)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                try:
                    await message_or_callback.answer()
                except TelegramBadRequest:
                    pass
            else:
                logger.warning(f"Could not edit profile message, sending a new one. Error: {e}")
                try:
                    if message_or_callback.message:
                        await message_or_callback.message.delete()
                except TelegramBadRequest:
                    pass
                if message_or_callback.message:
                    await bot.send_message(chat_id=message_or_callback.message.chat.id, text=profile_text, reply_markup=keyboard)


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

@router.callback_query(F.data == 'profile_transfer')
async def initiate_transfer(callback: CallbackQuery, state: FSMContext, **kwargs):
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    try:
        balance = float(balance)
    except (ValueError, TypeError):
        balance = 0.0

    if balance < 0:
        await callback.answer("Ваш баланс отрицательный. Передача звезд невозможна, пока вы не погасите долг.", show_alert=True)
        return
        
    if balance < Limits.MIN_TRANSFER_AMOUNT:
        await callback.answer(f"Недостаточно звезд на балансе для выполнения этой операции (минимум {Limits.MIN_TRANSFER_AMOUNT} ⭐).", show_alert=True)
        return

    await state.set_state(UserState.TRANSFER_AMOUNT_OTHER)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Сколько звезд вы хотите передать?",
            reply_markup=inline.get_cancel_inline_keyboard()
        )
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

async def process_transfer_amount(amount: float, message: Message, state: FSMContext):
    balance, _ = await db_manager.get_user_balance(message.from_user.id)
    if amount > float(balance):
        prompt_msg = await message.answer(f"Недостаточно звезд. Ваш баланс: {balance} ⭐")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await state.update_data(transfer_amount=amount)
    await state.set_state(UserState.TRANSFER_RECIPIENT)
    prompt_msg = await message.answer(
        "Кому вы хотите передать звезды? Укажите никнейм (например, @username) или ID пользователя.",
        reply_markup=inline.get_cancel_inline_keyboard()
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.TRANSFER_AMOUNT_OTHER)
async def transfer_other_amount_input(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    if not message.text: return
    try:
        amount = float(message.text)
        if amount < Limits.MIN_TRANSFER_AMOUNT: raise ValueError
    except (ValueError, TypeError):
        prompt_msg = await message.answer(f"Неверный формат. Пожалуйста, введите положительное число (минимум {Limits.MIN_TRANSFER_AMOUNT}).")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    await process_transfer_amount(amount, message, state)

@router.message(UserState.TRANSFER_RECIPIENT)
async def process_transfer_recipient(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    if not message.text: return
    recipient_id = await db_manager.find_user_by_identifier(message.text)
    if not recipient_id or recipient_id == message.from_user.id:
        prompt_msg = await message.answer("Пользователь не найден или вы пытаетесь отправить звезды себе. Попробуйте еще раз.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await state.update_data(recipient_id=recipient_id)
    await state.set_state(UserState.TRANSFER_SHOW_MY_NICK)
    await message.answer(
        "Хотите указать свой никнейм при передаче? Получатель увидит, от кого пришли звезды.",
        reply_markup=inline.get_transfer_show_nick_keyboard()
    )

@router.callback_query(F.data.in_({'transfer_show_nick_yes', 'transfer_show_nick_no'}), UserState.TRANSFER_SHOW_MY_NICK)
async def process_transfer_show_nick(callback: CallbackQuery, state: FSMContext):
    show_nick = callback.data == 'transfer_show_nick_yes'
    await state.update_data(show_nick=show_nick)
    await state.set_state(UserState.TRANSFER_ASK_COMMENT)
    if callback.message:
        prompt_msg = await callback.message.edit_text(
            "Хотите оставить комментарий к передаче?",
            reply_markup=inline.get_ask_comment_keyboard(prefix='transfer')
        )
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data == 'transfer_ask_comment_no', UserState.TRANSFER_ASK_COMMENT)
async def process_transfer_no_comment(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.message:
        await callback.message.delete()
    await finish_transfer(callback.from_user, state, bot, comment=None)

@router.callback_query(F.data == 'transfer_ask_comment_yes', UserState.TRANSFER_ASK_COMMENT)
async def process_transfer_yes_comment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.TRANSFER_COMMENT_INPUT)
    if callback.message:
        prompt_msg = await callback.message.edit_text("Введите ваш комментарий:")
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.TRANSFER_COMMENT_INPUT)
async def process_transfer_comment_input(message: Message, state: FSMContext, bot: Bot):
    await delete_previous_messages(message, state)
    if not message.text: return
    await finish_transfer(message.from_user, state, bot, comment=message.text)

async def finish_transfer(user, state: FSMContext, bot: Bot, comment: str | None):
    data = await state.get_data()
    sender_id = user.id
    sender_username = user.username
    
    success = await db_manager.transfer_stars(
        sender_id=sender_id,
        recipient_id=data['recipient_id'],
        amount=data['transfer_amount']
    )

    if success:
        sender_name = f"@{sender_username}" if data['show_nick'] else "Анонимный пользователь"
        notification_text = (
            f"✨ Вам переданы звезды ✨\n\n"
            f"От: {sender_name}\n"
            f"Количество: {data['transfer_amount']} ⭐"
        )
        if comment:
            notification_text += f"\nКомментарий: {comment}"
        
        try:
            await bot.send_message(data['recipient_id'], notification_text)
        except Exception as e:
            print(f"Не удалось уведомить о переводе {data['recipient_id']}: {e}")

        await bot.send_message(sender_id, "Звезды успешно переданы!", reply_markup=reply.get_main_menu_keyboard())
    else:
        await bot.send_message(sender_id, "Произошла ошибка при переводе. Попробуйте снова.", reply_markup=reply.get_main_menu_keyboard())

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)

@router.callback_query(F.data == 'profile_withdraw')
async def initiate_withdraw(callback: CallbackQuery, state: FSMContext, **kwargs):
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    try:
        balance = float(balance)
    except (ValueError, TypeError):
        balance = 0.0
    
    if balance < 0:
        await callback.answer("Ваш баланс отрицательный. Вывод невозможен, пока вы не погасите долг.", show_alert=True)
        return

    if balance < Limits.MIN_WITHDRAWAL_AMOUNT:
        await callback.answer(f"Минимальная сумма для вывода {Limits.MIN_WITHDRAWAL_AMOUNT} звезд. Ваш баланс: {balance} ⭐.", show_alert=True)
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
    user_id = callback.from_user.id
    amount_str = callback.data.split('_')[-1]
    
    if amount_str == 'other':
        await state.set_state(UserState.WITHDRAW_AMOUNT_OTHER)
        if callback.message:
            prompt_msg = await callback.message.edit_text(f"Введите сумму для вывода (минимум {Limits.MIN_WITHDRAWAL_AMOUNT}):", reply_markup=inline.get_cancel_inline_keyboard())
            if prompt_msg:
                await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    amount = float(amount_str)
    
    balance, _ = await db_manager.get_user_balance(user_id)
    if float(balance) < amount:
        await callback.answer(f"Недостаточно звезд. Ваш баланс: {balance} ⭐", show_alert=True)
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

@router.message(UserState.WITHDRAW_AMOUNT_OTHER)
async def withdraw_other_amount_input(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    if not message.text: return
    try:
        amount = float(message.text)
        if amount < Limits.MIN_WITHDRAWAL_AMOUNT:
            prompt_msg = await message.answer(f"Минимальная сумма для вывода - {Limits.MIN_WITHDRAWAL_AMOUNT} звезд.")
            await state.update_data(prompt_message_id=prompt_msg.message_id)
            return
    except (ValueError, TypeError):
        prompt_msg = await message.answer("Неверный формат. Пожалуйста, введите число.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    balance, _ = await db_manager.get_user_balance(message.from_user.id)
    if float(balance) < amount:
        prompt_msg = await message.answer(f"Недостаточно звезд. Ваш баланс: {balance} ⭐")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

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
        await state.set_state(UserState.MAIN_MENU)
        return

    admin_message = (
        f"🚨 <b>Новый запрос на вывод средств!</b> 🚨\n\n"
        f"👤 <b>Отправитель:</b> @{user.username} (ID: <code>{user.id}</code>)\n"
        f"💰 <b>Сумма:</b> {amount} ⭐\n"
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
        await bot.send_message(user.id, "❌ Не удалось отправить запрос администратору. Вероятно, бот не добавлен в канал выплат или не имеет нужных прав. Пожалуйста, обратитесь в поддержку. Ваши звезды не были списаны.")
        await db_manager.update_balance(user.id, amount)
    
    await state.clear()
    await state.set_state(UserState.MAIN_MENU)

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
            reply_markup=inline.get_cancel_inline_keyboard()
        )
        if prompt_msg:
            await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.WITHDRAW_USER_ID)
async def process_withdraw_user_id(message: Message, state: FSMContext):
    await delete_previous_messages(message, state)
    if not message.text: return
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

@router.message(UserState.WITHDRAW_COMMENT_INPUT)
async def process_withdraw_comment_input(message: Message, state: FSMContext, bot: Bot):
    await delete_previous_messages(message, state)
    if not message.text: return
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
        review_lines = [f"- {review.amount} ⭐ ({review.platform}) до {review.hold_until.strftime('%d.%m.%Y %H:%M')} UTC" for review in reviews_in_hold]
        text += "\n".join(review_lines)
    
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=inline.get_back_to_profile_keyboard())
        except TelegramBadRequest:
            pass