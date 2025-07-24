# file: handlers/profile.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from functools import wraps

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager

router = Router()
logger = logging.getLogger(__name__)

# --- Главный экран профиля и навигация ---

async def show_profile_menu(message_or_callback: Message | CallbackQuery, state: FSMContext):
    """Универсальная функция для отображения меню профиля."""
    await state.set_state(UserState.MAIN_MENU)
    user_id = message_or_callback.from_user.id
    balance, hold_balance = await db_manager.get_user_balance(user_id)
    referrer_info = await db_manager.get_referrer_info(user_id)
    
    profile_text = (
        f"✨ Ваш Профиль ✨\n\n"
        f"Вас пригласил: {referrer_info}\n"
        f"Баланс звезд: {balance} ⭐\n"
        f"В холде: {hold_balance} ⭐"
    )
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(profile_text, reply_markup=inline.get_profile_keyboard())
    else: 
        try:
            await message_or_callback.message.edit_text(profile_text, reply_markup=inline.get_profile_keyboard())
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await message_or_callback.answer()
            else:
                try:
                    await message_or_callback.message.delete()
                except TelegramBadRequest:
                    pass
                await message_or_callback.message.answer(profile_text, reply_markup=inline.get_profile_keyboard())


@router.message(Command("stars"))
@router.message(F.text == 'Профиль', UserState.MAIN_MENU)
async def profile_handler(message: Message, state: FSMContext):
    await show_profile_menu(message, state)

@router.callback_query(F.data == 'go_profile')
async def go_profile_handler(callback: CallbackQuery, state: FSMContext):
    await show_profile_menu(callback, state)


# --- Подмодуль: Передача звезд ---

@router.callback_query(F.data == 'profile_transfer')
async def initiate_transfer(callback: CallbackQuery, state: FSMContext, **kwargs):
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    # ИЗМЕНЕНО: Принудительное приведение к float для надежного сравнения
    try:
        balance = float(balance)
    except (ValueError, TypeError):
        balance = 0.0

    logger.info(f"Transfer check for user {callback.from_user.id}: Balance is {balance} (type: {type(balance)})")
    
    if balance < 1.0:
        await callback.answer("Недостаточно звезд на балансе для выполнения этой операции.", show_alert=True)
        return

    await state.set_state(UserState.TRANSFER_AMOUNT_OTHER)
    await callback.message.edit_text(
        "Сколько звезд вы хотите передать?",
        reply_markup=inline.get_cancel_inline_keyboard()
    )

async def process_transfer_amount(amount: float, message: Message, state: FSMContext):
    balance, _ = await db_manager.get_user_balance(message.from_user.id)
    if amount > float(balance):
        await message.answer(f"Недостаточно звезд. Ваш баланс: {balance} ⭐")
        return

    await state.update_data(transfer_amount=amount)
    await state.set_state(UserState.TRANSFER_RECIPIENT)
    await message.answer(
        "Кому вы хотите передать звезды? Укажите никнейм (например, @username) или ID пользователя.",
        reply_markup=inline.get_cancel_inline_keyboard()
    )

@router.message(UserState.TRANSFER_AMOUNT_OTHER)
async def transfer_other_amount_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
    except (ValueError, TypeError):
        await message.answer("Неверный формат. Пожалуйста, введите положительное число.")
        return
    await process_transfer_amount(amount, message, state)

@router.message(UserState.TRANSFER_RECIPIENT)
async def process_transfer_recipient(message: Message, state: FSMContext):
    recipient_id = await db_manager.find_user_by_identifier(message.text)
    if not recipient_id or recipient_id == message.from_user.id:
        await message.answer("Пользователь не найден или вы пытаетесь отправить звезды себе. Попробуйте еще раз.")
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
    await callback.message.edit_text(
        "Хотите оставить комментарий к передаче?",
        reply_markup=inline.get_ask_comment_keyboard(prefix='transfer')
    )

@router.callback_query(F.data == 'transfer_ask_comment_no', UserState.TRANSFER_ASK_COMMENT)
async def process_transfer_no_comment(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    await finish_transfer(callback.from_user, state, bot, comment=None)

@router.callback_query(F.data == 'transfer_ask_comment_yes', UserState.TRANSFER_ASK_COMMENT)
async def process_transfer_yes_comment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.TRANSFER_COMMENT_INPUT)
    await callback.message.edit_text("Введите ваш комментарий:")

@router.message(UserState.TRANSFER_COMMENT_INPUT)
async def process_transfer_comment_input(message: Message, state: FSMContext, bot: Bot):
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


# --- Подмодуль: Вывод звезд ---

@router.callback_query(F.data == 'profile_withdraw')
async def initiate_withdraw(callback: CallbackQuery, state: FSMContext, **kwargs):
    balance, _ = await db_manager.get_user_balance(callback.from_user.id)
    
    # ИЗМЕНЕНО: Принудительное приведение к float для надежного сравнения
    try:
        # Пытаемся преобразовать полученное значение в float.
        # Это защитит от случаев, когда из базы приходит строка или другой тип.
        balance = float(balance)
    except (ValueError, TypeError):
        # Если преобразование не удалось, считаем баланс нулевым.
        balance = 0.0

    logger.info(f"Withdraw check for user {callback.from_user.id}: Balance is {balance} (type: {type(balance)})")
    
    # ИЗМЕНЕНО: Сравниваем float с float (15.0) для точности.
    if balance < 15.0:
        # ИЗМЕНЕНО: Более информативное сообщение об ошибке для отладки
        await callback.answer(f"Недостаточно звезд. Ваш баланс: {balance} ⭐.", show_alert=True)
        return

    await state.set_state(UserState.WITHDRAW_AMOUNT)
    await callback.message.edit_text(
        "Сколько звезд вы хотите вывести?",
        reply_markup=inline.get_withdraw_amount_keyboard()
    )

async def process_withdraw_amount(amount: float, message: Message, state: FSMContext):
    balance, _ = await db_manager.get_user_balance(message.from_user.id)
    if amount > float(balance):
        await message.answer(f"Недостаточно звезд. Ваш баланс: {balance} ⭐")
        return

    await state.update_data(withdraw_amount=amount)
    await state.set_state(UserState.WITHDRAW_RECIPIENT)
    await message.answer(
        "Кому вы хотите отправить подарок?",
        reply_markup=inline.get_withdraw_recipient_keyboard()
    )

@router.callback_query(F.data.startswith('withdraw_amount_'), UserState.WITHDRAW_AMOUNT)
async def withdraw_predefined_amount(callback: CallbackQuery, state: FSMContext):
    amount = float(callback.data.split('_')[-1])
    await callback.message.delete()
    await process_withdraw_amount(amount, callback.message, state)

@router.callback_query(F.data == 'withdraw_amount_other', UserState.WITHDRAW_AMOUNT)
async def withdraw_other_amount_request(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.WITHDRAW_AMOUNT_OTHER)
    await callback.message.edit_text("Введите сумму для вывода:", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(UserState.WITHDRAW_AMOUNT_OTHER)
async def withdraw_other_amount_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 15: raise ValueError
    except (ValueError, TypeError):
        await message.answer("Неверный формат. Пожалуйста, введите число (минимум 15).")
        return
    await process_withdraw_amount(amount, message, state)

@router.callback_query(F.data.startswith('withdraw_recipient_'), UserState.WITHDRAW_RECIPIENT)
async def process_withdraw_recipient(callback: CallbackQuery, state: FSMContext, bot: Bot):
    recipient_type = callback.data.split('_')[-1]
    
    await callback.message.delete()

    if recipient_type == 'self':
        data = await state.get_data()
        amount = data['withdraw_amount']
        await db_manager.update_balance(callback.from_user.id, -amount)
        await bot.send_message(callback.from_user.id, "Запрос на вывод звезд создан. Звезды будут отправлены вам.")
        await state.clear()
        await state.set_state(UserState.MAIN_MENU)
    elif recipient_type == 'other':
        await state.set_state(UserState.WITHDRAW_USER_ID)
        await bot.send_message(
            callback.from_user.id,
            "Укажите никнейм или ID пользователя, которому нужно отправить подарок.",
            reply_markup=inline.get_cancel_inline_keyboard()
        )

@router.message(UserState.WITHDRAW_USER_ID)
async def process_withdraw_user_id(message: Message, state: FSMContext):
    recipient_id = await db_manager.find_user_by_identifier(message.text)
    if not recipient_id:
        await message.answer("Не могу найти пользователя с таким никнеймом или ID.")
        return
        
    await state.update_data(withdraw_recipient_id=recipient_id)
    await state.set_state(UserState.WITHDRAW_ASK_COMMENT)
    await message.answer(
        "Хотите оставить комментарий к подарку?",
        reply_markup=inline.get_ask_comment_keyboard(prefix='withdraw')
    )

@router.callback_query(F.data == 'withdraw_ask_comment_no', UserState.WITHDRAW_ASK_COMMENT)
async def process_withdraw_no_comment(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    await finish_withdraw(callback.from_user, state, bot, comment=None)

@router.callback_query(F.data == 'withdraw_ask_comment_yes', UserState.WITHDRAW_ASK_COMMENT)
async def process_withdraw_yes_comment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.WITHDRAW_COMMENT_INPUT)
    await callback.message.edit_text("Введите ваш комментарий к подарку:")

@router.message(UserState.WITHDRAW_COMMENT_INPUT)
async def process_withdraw_comment_input(message: Message, state: FSMContext, bot: Bot):
    await finish_withdraw(message.from_user, state, bot, comment=message.text)

async def finish_withdraw(user, state: FSMContext, bot: Bot, comment: str | None):
    data = await state.get_data()
    sender_id = user.id
    recipient_id = data['withdraw_recipient_id']
    amount = data['withdraw_amount']
    
    await db_manager.update_balance(sender_id, -amount)
    
    notification_text = (
        f"🎁 Вам отправлен подарок! 🎁\n\n"
        f"Отправитель: @{user.username}\n"
        f"Количество: {amount} ⭐"
    )
    if comment:
        notification_text += f"\nКомментарий: {comment}"
        
    try:
        await bot.send_message(recipient_id, notification_text)
    except Exception as e:
        print(f"Не удалось уведомить о подарке {recipient_id}: {e}")

    await bot.send_message(sender_id, f"Подарок в {amount} ⭐ успешно отправлен!", reply_markup=reply.get_main_menu_keyboard())

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)


# --- Подмодуль: "Реф. ссылка" и "Холд" ---

@router.callback_query(F.data == 'profile_referral')
async def show_referral_info(callback: CallbackQuery, state: FSMContext, bot: Bot, **kwargs):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={user_id}"
    referral_earnings = await db_manager.get_referral_earnings(user_id)
    ref_text = (
        f"🚀 Ваша реферальная ссылка:\n`{referral_link}`\n\n"
        "🔥 Получайте 0.45 звезд за каждый одобренный отзыв, написанный вашим рефералом в Google.Картах!\n\n"
        f"💰 Заработано всего: {referral_earnings} ⭐"
    )
    await callback.message.edit_text(ref_text, reply_markup=inline.get_referral_info_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == 'profile_referrals_list')
async def show_referrals_list(callback: CallbackQuery, state: FSMContext, **kwargs):
    referrals = await db_manager.get_referrals(callback.from_user.id)
    if not referrals:
        text = "🤝 Ваши рефералы:\n\nУ вас пока нет рефералов."
    else:
        text = f"🤝 Ваши рефералы:\nУ вас {len(referrals)} рефералов.\n\nСписок:\n" + "\n".join([f"- @{username}" for username in referrals if username])
    await callback.message.edit_text(text, reply_markup=inline.get_back_to_profile_keyboard())

@router.callback_query(F.data == 'profile_claim_referral_stars')
async def claim_referral_stars(callback: CallbackQuery, state: FSMContext, bot: Bot, **kwargs):
    earnings = await db_manager.get_referral_earnings(callback.from_user.id)
    if earnings > 0:
        await db_manager.claim_referral_earnings(callback.from_user.id)
        await callback.answer(f"{earnings} ⭐ зачислены на ваш основной баланс!", show_alert=True)
        await show_referral_info(callback, state, bot)
    else:
        await callback.answer("У вас нет начислений для сбора.", show_alert=True)

@router.callback_query(F.data == 'profile_hold')
async def show_hold_info(callback: CallbackQuery, state: FSMContext, **kwargs):
    reviews_in_hold = await db_manager.get_user_hold_reviews(callback.from_user.id)
    if not reviews_in_hold:
        text = "⏳ Ваши отзывы в холде:\n\nУ вас нет отзывов в холде."
    else:
        text = "⏳ Ваши отзывы в холде:\n\n"
        review_lines = [f"- {review.amount} ⭐ ({review.platform}) до {review.hold_until.strftime('%d.%m.%Y %H:%M')} UTC" for review in reviews_in_hold]
        text += "\n".join(review_lines)
    await callback.message.edit_text(text, reply_markup=inline.get_back_to_profile_keyboard())