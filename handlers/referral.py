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
    """Отображает информацию о уже выбранном реферальном пути."""
    user_id = message_or_callback.from_user.id
    user = await db_manager.get_user(user_id)
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={user_id}"
    referral_earnings = await db_manager.get_referral_earnings(user_id)

    path_description = ""
    if user.referral_path == 'google':
        path_description = f"Вы получаете <b>{Rewards.REFERRAL_GOOGLE_REVIEW} ⭐</b> за каждый одобренный отзыв вашего реферала в Google Картах."
    elif user.referral_path == 'gmail':
        path_description = f"Вы получаете <b>{Rewards.REFERRAL_GMAIL_ACCOUNT} ⭐</b> за каждый созданный и одобренный Gmail аккаунт вашего реферала."
    elif user.referral_path == 'yandex':
        if user.referral_subpath == 'with_text':
            path_description = f"Вы получаете <b>{Rewards.REFERRAL_YANDEX_WITH_TEXT} ⭐</b> за каждый одобренный отзыв вашего реферала в Яндекс.Картах (с текстом)."
        else:
            path_description = f"Вы получаете <b>{Rewards.REFERRAL_YANDEX_WITHOUT_TEXT} ⭐</b> за каждый одобренный отзыв вашего реферала в Яндекс.Картах (без текста)."

    ref_text = (
        f"🚀 <b>Ваша реферальная система</b><br><br>"
        f"<b>Ваш выбор:</b> {path_description}<br><br>"
        f"🔗 <b>Ссылка для приглашений:</b><br>"
        f"<code>{referral_link}</code><br>"
        f"(Нажмите на ссылку выше, чтобы скопировать её)<br><br>"
        f"💰 Накоплено в копилке: <b>{referral_earnings:.2f} ⭐</b>"
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
    """
    Точка входа в реферальную систему. Проверяет, сделал ли пользователь выбор.
    """
    user = await db_manager.get_user(callback.from_user.id)
    if user and user.referral_path:
        await show_selected_referral_path(callback, bot)
    else:
        await show_referral_path_selection(callback, state)

@router.callback_query(F.data == 'profile_referrals_list')
async def show_referrals_list(callback: CallbackQuery):
    """Показывает пользователю список его рефералов."""
    referrals = await db_manager.get_referrals(callback.from_user.id)
    
    if not referrals:
        text = "У вас пока нет приглашенных пользователей."
    else:
        text = "👥 <b>Ваши рефералы:</b><br><br>" + "<br>".join([f"- @{username}" for username in referrals if username])
        
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
        
    # Обновляем сообщение с меню
    await show_selected_referral_path(callback, bot)


async def show_referral_path_selection(callback: CallbackQuery, state: FSMContext):
    """Показывает меню выбора реферального пути."""
    await state.set_state(UserState.REFERRAL_PATH_SELECTION)
    selection_text = (
        "🤝 <b>Добро пожаловать в реферальную систему!</b><br><br>"
        "Выберите, как вы хотите зарабатывать звезды с приглашенных друзей. "
        "Это поможет вам получать пассивный доход!<br><br>"
        "❗️<b>ВНИМАНИЕ:</b> Вы можете выбрать путь только <b>один раз</b>. Изменить его будет невозможно."
    )
    if callback.message:
        await callback.message.edit_text(selection_text, reply_markup=inline.get_referral_path_selection_keyboard())

@router.callback_query(F.data == 'ref_path:yandex', UserState.REFERRAL_PATH_SELECTION)
async def select_yandex_subpath(callback: CallbackQuery, state: FSMContext):
    """Показывает под-меню для выбора типа Яндекс.Отзывов."""
    await state.set_state(UserState.REFERRAL_YANDEX_SUBPATH_SELECTION)
    text = (
        "Вы выбрали путь 'Яндекс.Карты'.<br><br>"
        "Теперь уточните, за какие именно отзывы вы хотите получать награду:"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=inline.get_yandex_subpath_selection_keyboard())

@router.callback_query(F.data == 'back_to_ref_path_selection', UserState.REFERRAL_YANDEX_SUBPATH_SELECTION)
async def back_to_main_selection(callback: CallbackQuery, state: FSMContext):
    """Возврат к основному меню выбора пути."""
    await show_referral_path_selection(callback, state)


@router.callback_query(F.data.startswith('confirm_ref_path:'), StateFilter(UserState.REFERRAL_PATH_SELECTION, UserState.REFERRAL_YANDEX_SUBPATH_SELECTION))
async def confirm_referral_path(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Сохраняет выбор пользователя в БД и показывает финальное сообщение."""
    await callback.answer("Ваш выбор сохранен!")
    
    parts = callback.data.split(':')
    path = parts[1]
    subpath = parts[2] if len(parts) > 2 else None

    success = await db_manager.set_user_referral_path(callback.from_user.id, path, subpath)

    if not success:
        await callback.message.edit_text("❌ Произошла ошибка. Возможно, вы уже сделали свой выбор ранее.")
        return

    await state.clear()
    await state.set_state(UserState.MAIN_MENU)
    
    # Показываем пользователю его новое реферальное меню
    await show_selected_referral_path(callback, bot)