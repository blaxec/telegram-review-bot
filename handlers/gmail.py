# file: handlers/gmail.py

import datetime
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from database import db_manager
from config import FINAL_CHECK_ADMIN

router = Router()
logger = logging.getLogger(__name__)

# --- ХЭНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ДЛЯ СОЗДАНИЯ GMAIL ---

@router.callback_query(F.data == 'earning_create_gmail')
async def initiate_gmail_creation(callback: CallbackQuery, state: FSMContext):
    user = await db_manager.get_user(callback.from_user.id)
    if user and user.blocked_until and user.blocked_until > datetime.datetime.utcnow():
        await callback.answer("Создание аккаунтов для вас временно заблокировано.", show_alert=True)
        return
    await state.set_state(UserState.GMAIL_ACCOUNT_INIT)
    await callback.message.edit_text(
        "За создание аккаунта выдается 5 звезд.",
        reply_markup=inline.get_gmail_init_keyboard()
    )

@router.callback_query(
    F.data == 'gmail_how_to_create',
    F.state.in_({UserState.GMAIL_ACCOUNT_INIT, UserState.GMAIL_AWAITING_VERIFICATION})
)
async def show_gmail_creation_instructions(callback: CallbackQuery, state: FSMContext):
    text = (
        "Чтобы начать создание, перейдите по [ссылке](https://myaccount.google.com/?tab=kk) или создайте аккаунт через Gmail, Google, Chrome и другие браузеры.\n\n"
        "**Общие шаги:**\n"
        "1. Найдите аватарку в правом верхнем углу.\n"
        "2. Нажмите на стрелку (если есть список аккаунтов) и выберите \"Добавить аккаунт\".\n"
        "3. Если у вас только один аккаунт, также найдите опцию \"Добавить аккаунт\".\n\n"
        "Прекрасно, теперь вы можете начать создавать аккаунты!"
    )
    
    current_state = await state.get_state()
    reply_markup = None
    if current_state == UserState.GMAIL_ACCOUNT_INIT:
        reply_markup = inline.get_gmail_init_keyboard()
    elif current_state == UserState.GMAIL_AWAITING_VERIFICATION:
        reply_markup = inline.get_gmail_verification_keyboard()

    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown", disable_web_page_preview=True)

@router.callback_query(F.data == 'gmail_request_data', UserState.GMAIL_ACCOUNT_INIT)
async def request_gmail_data_from_admin(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    await callback.message.edit_text("Запрашиваю данные у администратора... Ожидайте.")
    await state.set_state(UserState.GMAIL_AWAITING_DATA)
    admin_notification = (
        f"❗️ Пользователь @{callback.from_user.username} (ID: `{user_id}`) "
        "запрашивает данные для регистрации аккаунта Gmail."
    )
    try:
        await bot.send_message(
            FINAL_CHECK_ADMIN,
            admin_notification,
            reply_markup=inline.get_admin_gmail_data_request_keyboard(user_id)
        )
    except Exception as e:
        await callback.message.answer("Не удалось отправить запрос администратору. Попробуйте позже.")
        await state.clear()
        print(f"Ошибка отправки запроса на Gmail данные админу {FINAL_CHECK_ADMIN}: {e}")

@router.callback_query(F.data == 'gmail_send_for_verification', UserState.GMAIL_AWAITING_VERIFICATION)
async def send_gmail_for_verification(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    current_state = await state.get_state()
    logger.info(f"Handler 'send_gmail_for_verification' triggered for user {user_id}. Current state: {current_state}")

    await callback.answer()
    await callback.message.edit_text("Ваш аккаунт отправлен на проверку. Ожидайте.")
    user_data = await state.get_data()
    gmail_details = user_data.get('gmail_details')
    
    if not gmail_details:
        logger.error(f"Critical error for user {user_id}: gmail_details not found in state data.")
        await callback.message.answer("Произошла ошибка, не найдены данные вашего аккаунта. Начните заново.", reply_markup=reply.get_main_menu_keyboard())
        await state.clear()
        await state.set_state(UserState.MAIN_MENU)
        return

    admin_notification = (
        f"🚨 Проверка созданного Gmail аккаунта 🚨\n\n"
        f"Пользователь: @{callback.from_user.username} (ID: `{user_id}`)\n\n"
        f"**Данные:**\n"
        f"Имя: {gmail_details['name']}\n"
        f"Фамилия: {gmail_details['surname']}\n"
        f"Почта: {gmail_details['email']}\n"
        f"Пароль: `{gmail_details['password']}`"
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


# --- ХЭНДЛЕРЫ АДМИНА ДЛЯ УПРАВЛЕНИЯ GMAIL ---

@router.callback_query(F.data.startswith('admin_gmail_reject_request:'), F.from_user.id == FINAL_CHECK_ADMIN)
async def admin_reject_gmail_data_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split(':')[1])
    original_text = callback.message.text
    
    logger.info(f"Admin {callback.from_user.id} is rejecting Gmail data request for user {user_id}. Setting state to REJECT_REASON_GMAIL_DATA_REQUEST.")
    await state.set_state(AdminState.REJECT_REASON_GMAIL_DATA_REQUEST)
    await state.update_data(target_user_id=user_id)

    await callback.message.edit_text(
        f"{original_text}\n\n❌ ЗАПРОС ОТКЛОНЕН (админ @{callback.from_user.username}).\n\n"
        f"✍️ **Теперь, пожалуйста, отправьте причину отказа следующим сообщением.**",
        reply_markup=None
    )


@router.callback_query(F.data.startswith('admin_gmail_send_data:'), F.from_user.id == FINAL_CHECK_ADMIN)
async def admin_send_gmail_data_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split(':')[1])
    await state.update_data(gmail_user_id=user_id)
    await state.set_state(AdminState.ENTER_GMAIL_DATA)
    await callback.message.edit_text(
        "Введите данные для создания аккаунта в формате:\n"
        "Имя\nФамилия\nПароль\nПочта (без @gmail.com)",
        reply_markup=None
    )


@router.message(AdminState.ENTER_GMAIL_DATA, F.from_user.id == FINAL_CHECK_ADMIN)
async def process_admin_gmail_data(message: Message, state: FSMContext, bot: Bot):
    admin_data = await state.get_data()
    user_id = admin_data.get('gmail_user_id')
    data_lines = message.text.strip().split('\n')
    if len(data_lines) != 4:
        await message.answer("Неверный формат. Нужно 4 строки: Имя, Фамилия, Пароль, Почта. Попробуйте снова.")
        return
    name, surname, password, email = data_lines
    full_email = f"{email}@gmail.com"
    user_message = (
        "Ваши данные для создания аккаунта:\n"
        'Не знаете как создать аккаунт? Прочитайте информацию, нажав на "Как создать аккаунт".\n\n'
        "<b>Данные для создания:</b>\n"
        f"Имя: <code>{name}</code>\n"
        f"Фамилия: <code>{surname}</code>\n"
        f"Пароль: <code>{password}</code>\n"
        f"Почта: <code>{full_email}</code>"
    )
    user_state = FSMContext(storage=state.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    
    logger.info(f"Admin {message.from_user.id} is sending data to user {user_id}. Setting user state to GMAIL_AWAITING_VERIFICATION.")
    await user_state.set_state(UserState.GMAIL_AWAITING_VERIFICATION)
    await user_state.update_data(gmail_details={"name": name, "surname": surname, "password": password, "email": full_email})
    try:
        await bot.send_message(user_id, user_message, parse_mode="HTML", reply_markup=inline.get_gmail_verification_keyboard())
        await message.answer(f"Данные успешно отправлены пользователю {user_id}.")
    except Exception as e:
        await message.answer(f"Не удалось отправить данные пользователю {user_id}. Возможно, он заблокировал бота.")
        print(e)
    await state.clear()


@router.callback_query(F.data.startswith('admin_gmail_confirm_account:'), F.from_user.id == FINAL_CHECK_ADMIN)
async def admin_confirm_gmail_account(callback: CallbackQuery, bot: Bot):
    await callback.answer("Аккаунт подтвержден. Пользователю начислены звезды.", show_alert=True)
    user_id = int(callback.data.split(':')[1])
    await db_manager.update_balance(user_id, 5.0)
    try:
        await bot.send_message(user_id, "✅ Ваш аккаунт успешно прошел проверку. +5 звезд начислено на баланс.", reply_markup=reply.get_main_menu_keyboard())
    except Exception as e:
        print(f"Не удалось уведомить {user_id} о подтверждении Gmail: {e}")
    await callback.message.edit_text(f"{callback.message.text}\n\n✅ АККАУНТ ПОДТВЕРЖДЕН (админ @{callback.from_user.username})", reply_markup=None)


@router.callback_query(F.data.startswith('admin_gmail_reject_account:'), F.from_user.id == FINAL_CHECK_ADMIN)
async def admin_reject_gmail_account(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split(':')[1])
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminState.REJECT_REASON_GMAIL_ACCOUNT)
    await callback.message.edit_text(
        f"{callback.message.text}\n\n❌ АККАУНТ ОТКЛОНЕН (админ @{callback.from_user.username}).\n\n"
        f"✍️ **Теперь, пожалуйста, введите причину отказа следующим сообщением.**",
        reply_markup=None
    )