# file: handlers/gmail.py

import datetime
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from database import db_manager
from config import FINAL_CHECK_ADMIN
from logic.user_notifications import format_timedelta
from logic.promo_logic import check_and_apply_promo_reward

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

@router.callback_query(F.data == 'earning_create_gmail')
async def initiate_gmail_creation(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    user = await db_manager.get_user(callback.from_user.id)
    if not user:
        return

    if user.blocked_until and user.blocked_until > datetime.datetime.utcnow():
        await callback.answer("Создание аккаунтов для вас временно заблокировано.", show_alert=True)
        return

    cooldown = await db_manager.check_platform_cooldown(user.id, "gmail")
    if cooldown:
        if callback.message:
            await callback.message.edit_text(
                f"Вы сможете создать следующий аккаунт через: <i>{format_timedelta(cooldown)}</i>\n\n"
                "Если у вас есть другое устройство, вы можете запросить создание дополнительного аккаунта.",
                reply_markup=inline.get_gmail_cooldown_keyboard()
            )
        return

    await state.set_state(UserState.GMAIL_ENTER_DEVICE_MODEL)
    if callback.message:
        await callback.message.edit_text(
            "За создание аккаунта выдается <i>5 звезд</i>.\n\n"
            "Пожалуйста, укажите <i>модель вашего устройства</i> (например, iPhone 13 Pro или Samsung Galaxy S22), "
            "с которого вы будете создавать аккаунт. Эту информацию увидит администратор.\n\n"
            "Отправьте модель следующим сообщением.",
            reply_markup=inline.get_cancel_to_earning_keyboard()
        )
        await state.update_data(prompt_message_id=callback.message.message_id)


@router.callback_query(F.data == 'gmail_another_phone', F.state.in_('*'))
async def request_another_phone(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    await state.set_state(UserState.GMAIL_ENTER_ANOTHER_DEVICE_MODEL)
    if callback.message:
        await callback.message.edit_text(
            "Введите модель <i>второго устройства</i>, с которого вы хотите создать аккаунт. "
            "Этот запрос будет отправлен на ручное подтверждение администратору.",
            reply_markup=inline.get_cancel_to_earning_keyboard()
        )
        await state.update_data(prompt_message_id=callback.message.message_id)

async def send_device_model_to_admin(message: Message, state: FSMContext, bot: Bot, is_another: bool):
    """Отправляет модель устройства на проверку админу с полным набором кнопок."""
    device_model = message.text
    user_id = message.from_user.id
    
    # Сначала подтверждаем пользователю, что его сообщение принято
    await message.answer(
        f"Ваша модель устройства: <i>{device_model}</i>.\n"
        "Запомните ее, администратор может ее уточнить.\n\n"
        "Ваш запрос отправлен администратору на проверку. Ожидайте..."
    )
    
    # Обновляем данные и состояние в FSM
    await state.update_data(device_model=device_model)
    await state.set_state(UserState.GMAIL_AWAITING_DATA)

    context = "gmail_device_model"
    admin_notification = (
        f"❗️ Пользователь @{message.from_user.username} (ID: <code>{user_id}</code>) "
        f"отправил модель устройства для создания аккаунта Gmail:\n\n"
        f"<i>Модель: {device_model}</i>"
    )
    if is_another:
        admin_notification += "\n\n<i>Это запрос на создание со второго устройства.</i>"

    try:
        await bot.send_message(
            FINAL_CHECK_ADMIN,
            admin_notification,
            reply_markup=inline.get_admin_verification_keyboard(user_id, context)
        )
    except Exception as e:
        await message.answer("Не удалось отправить запрос администратору. Попробуйте позже.")
        await state.clear()
        logger.error(f"Ошибка отправки модели устройства админу {FINAL_CHECK_ADMIN}: {e}")

@router.message(UserState.GMAIL_ENTER_DEVICE_MODEL)
async def process_device_model(message: Message, state: FSMContext, bot: Bot):
    await delete_previous_messages(message, state)
    if not message.text:
        prompt_msg = await message.answer("Пожалуйста, отправьте модель устройства в виде текста.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    logger.info(f"Caught device model from user {message.from_user.id} in state GMAIL_ENTER_DEVICE_MODEL.")
    await send_device_model_to_admin(message, state, bot, is_another=False)


@router.message(UserState.GMAIL_ENTER_ANOTHER_DEVICE_MODEL)
async def process_another_device_model(message: Message, state: FSMContext, bot: Bot):
    await delete_previous_messages(message, state)
    if not message.text:
        prompt_msg = await message.answer("Пожалуйста, отправьте модель устройства в виде текста.")
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return
    logger.info(f"Caught another device model from user {message.from_user.id} in state GMAIL_ENTER_ANOTHER_DEVICE_MODEL.")
    await send_device_model_to_admin(message, state, bot, is_another=True)


@router.callback_query(F.data == 'gmail_send_for_verification', UserState.GMAIL_AWAITING_VERIFICATION)
async def send_gmail_for_verification(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
    
    if callback.message:
        await callback.message.edit_text("Ваш аккаунт отправлен на проверку. Ожидайте.")
    user_data = await state.get_data()
    gmail_details = user_data.get('gmail_details')
    device_model = user_data.get('device_model', 'Не указана')
    
    if not gmail_details:
        logger.error(f"Критическая ошибка для user {user_id}: gmail_details не найдены в state data.")
        await callback.message.answer("Произошла ошибка, не найдены данные вашего аккаунта. Начните заново.", reply_markup=reply.get_main_menu_keyboard())
        await state.clear()
        await state.set_state(UserState.MAIN_MENU)
        return

    admin_notification = (
        f"🚨 Проверка созданного Gmail аккаунта 🚨\n\n"
        f"<i>Пользователь:</i> @{callback.from_user.username} (ID: <code>{user_id}</code>)\n"
        f"<i>Устройство:</i> <code>{device_model}</code>\n\n"
        f"<b>Данные:</b>\n"
        f"Имя: {gmail_details['name']}\n"
        f"Фамилия: {gmail_details['surname']}\n"
        f"Почта: {gmail_details['email']}\n"
        f"Пароль: <code>{gmail_details['password']}</code>\n\n"
        f"<i>Инструкция для проверки:</i>\n"
        f"1. Убедитесь, что данные заполнены верно.\n"
        f"2. Проверьте, совпадает ли модель устройства с указанной.\n"
        f"3. <i>Обязательно отключите устройство пользователя от аккаунта после проверки.</i>"
    )
    try:
        await bot.send_message(
            FINAL_CHECK_ADMIN,
            admin_notification,
            reply_markup=inline.get_admin_gmail_final_check_keyboard(user_id)
        )
    except Exception as e:
        await callback.message.answer("Не удалось отправить аккаунт на проверку. Попробуйте позже.")
        logger.error(f"Failed to send Gmail for verification to admin {FINAL_CHECK_ADMIN}: {e}")
    
    await state.clear()
    await state.set_state(UserState.MAIN_MENU)


@router.callback_query(F.data == 'gmail_how_to_create', UserState.GMAIL_AWAITING_VERIFICATION)
async def show_gmail_instructions(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.GMAIL_INSTRUCTIONS)
    instructions_text = (
        "<b>Инструкция по созданию аккаунта Gmail:</b>\n\n"
        "1. Откройте приложение Gmail или перейдите на сайт <code>gmail.com</code>.\n"
        "2. Нажмите 'Создать аккаунт'.\n"
        "3. Введите <i>Имя</i> и <i>Фамилию</i>, которые вам выдал администратор.\n"
        "4. Придумайте и введите <i>имя пользователя</i> (адрес почты), которое вам выдали.\n"
        "5. Введите и подтвердите <i>пароль</i>, который вам выдали.\n"
        "6. <i>ВАЖНО:</i> Если Google просит указать номер телефона для подтверждения, пропустите этот шаг. Если пропустить нельзя, сообщите об этом в поддержку.\n"
        "7. Завершите создание аккаунта. Резервную почту указывать не нужно.\n\n"
        "После успешного создания вернитесь сюда и нажмите 'Отправить на проверку'."
    )
    if callback.message:
        await callback.message.edit_text(
            instructions_text,
            reply_markup=inline.get_gmail_back_to_verification_keyboard()
        )


@router.callback_query(F.data == 'gmail_back_to_verification', UserState.GMAIL_INSTRUCTIONS)
async def back_to_gmail_verification(callback: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    gmail_details = user_data.get('gmail_details', {})
    
    name = gmail_details.get('name', 'N/A')
    surname = gmail_details.get('surname', 'N/A')
    password = gmail_details.get('password', 'N/A')
    full_email = gmail_details.get('email', 'N/A')

    user_message = (
        "✅ Администратор одобрил ваш запрос и прислал данные для создания аккаунта:\n\n"
        "<b>Данные для создания:</b>\n"
        f"Имя: <code>{name}</code>\n"
        f"Фамилия: <code>{surname}</code>\n"
        f"Пароль: <code>{password}</code>\n"
        f"Почта: <code>{full_email}</code>"
    )

    await state.set_state(UserState.GMAIL_AWAITING_VERIFICATION)
    if callback.message:
        await callback.message.edit_text(
            user_message,
            reply_markup=inline.get_gmail_verification_keyboard()
        )

# --- ХЭНДЛЕРЫ АДМИНА ДЛЯ УПРАВЛЕНИЯ GMAIL ---

@router.callback_query(F.data.startswith('admin_gmail_send_data:'))
async def admin_send_gmail_data_request(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    user_id = int(callback.data.split(':')[1])
    await state.update_data(gmail_user_id=user_id)
    await state.set_state(AdminState.ENTER_GMAIL_DATA)
    if callback.message:
        await callback.message.edit_text(
            "Введите данные для создания аккаунта в формате:\n"
            "Имя\nФамилия\nПароль\nПочта (без @gmail.com)",
            reply_markup=None
        )


@router.message(AdminState.ENTER_GMAIL_DATA)
async def process_admin_gmail_data(message: Message, state: FSMContext, bot: Bot):
    if not message.text: return
    await delete_previous_messages(message, state)
    admin_data = await state.get_data()
    user_id = admin_data.get('gmail_user_id')
    
    data_lines = message.text.strip().split('\n')
    if len(data_lines) != 4:
        await message.answer("Неверный формат. Нужно 4 строки: Имя, Фамилия, Пароль, Почта. Попробуйте снова.")
        return
        
    name, surname, password, email = data_lines
    full_email = f"{email}@gmail.com"
    user_message = (
        "✅ Администратор одобрил ваш запрос и прислал данные для создания аккаунта:\n\n"
        "<b>Данные для создания:</b>\n"
        f"Имя: <code>{name}</code>\n"
        f"Фамилия: <code>{surname}</code>\n"
        f"Пароль: <code>{password}</code>\n"
        f"Почта: <code>{full_email}</code>"
    )
    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    
    user_current_data = await user_state.get_data()
    user_current_data['gmail_details'] = {"name": name, "surname": surname, "password": password, "email": full_email}

    logger.info(f"Admin {message.from_user.id} is sending data to user {user_id}. Setting user state to GMAIL_AWAITING_VERIFICATION.")
    
    await user_state.set_state(UserState.GMAIL_AWAITING_VERIFICATION)
    await user_state.set_data(user_current_data)
    
    try:
        await bot.send_message(user_id, user_message, parse_mode="HTML", reply_markup=inline.get_gmail_verification_keyboard())
        await message.answer(f"Данные успешно отправлены пользователю {user_id}.")
    except Exception as e:
        await message.answer(f"Не удалось отправить данные пользователю {user_id}. Возможно, он заблокировал бота.")
        logger.error(e)
    await state.clear()


@router.callback_query(F.data.startswith('admin_gmail_confirm_account:'))
async def admin_confirm_gmail_account(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer("Аккаунт подтвержден. Пользователю начислены звезды.", show_alert=True)
    except TelegramBadRequest:
        pass
        
    user_id = int(callback.data.split(':')[1])
    await db_manager.update_balance(user_id, 5.0)
    await db_manager.set_platform_cooldown(user_id, "gmail", 24)
    
    await check_and_apply_promo_reward(user_id, "gmail_account", bot)
    
    try:
        await bot.send_message(user_id, "✅ Ваш аккаунт успешно прошел проверку. +5 звезд начислено на баланс.", reply_markup=reply.get_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Не удалось уведомить {user_id} о подтверждении Gmail: {e}")
    if callback.message:
        await callback.message.edit_text(f"{callback.message.text}\n\n✅ АККАУНТ ПОДТВЕРЖДЕН (админ @{callback.from_user.username})", reply_markup=None)


@router.callback_query(F.data.startswith('admin_gmail_reject_account:'))
async def admin_reject_gmail_account(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
        
    user_id = int(callback.data.split(':')[1])
    await state.update_data(
        target_user_id=user_id,
        rejection_context="gmail_account"
    )
    await state.set_state(AdminState.PROVIDE_REJECTION_REASON)
    if callback.message:
        await callback.message.edit_text(
            f"{callback.message.text}\n\n❌ АККАУНТ ОТКЛОНЕН (админ @{callback.from_user.username}).\n\n"
            f"✍️ <i>Теперь, пожалуйста, введите причину отказа следующим сообщением.</i>",
            reply_markup=None
        )