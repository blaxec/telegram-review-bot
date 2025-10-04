# file: handlers/internship.py

import logging
import asyncio
from math import ceil
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager
from config import SUPER_ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)


async def delete_and_clear_prompt(message: Message, state: FSMContext):
    """Удаляет сообщение пользователя и предыдущее сообщение-приглашение от бота."""
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
    await state.update_data(prompt_message_id=None)


# --- ГЛАВНЫЙ ОБРАБОТЧИК КНОПКИ "ВАКАНСИЯ" ---

@router.message(F.text == '💼 Вакансия', StateFilter("*"))
async def internship_entry_point(message: Message, state: FSMContext):
    """
    Высокоприоритетная точка входа в раздел стажировки.
    Проверяет статус пользователя и направляет в нужный раздел.
    """
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    current_state = await state.get_state()
    internship_states = [s.state for s in UserState if s.state and s.state.startswith("UserState:INTERNSHIP_")]
    if current_state not in internship_states:
        await state.clear()
        
    user_id = message.from_user.id
    user = await db_manager.get_user(user_id)

    if user and user.is_intern:
        await show_intern_cabinet(message, state)
        return

    application = await db_manager.get_internship_application(user_id)
    if application:
        status_messages = {
            'pending': "⏳ Ваша анкета находится на рассмотрении. Пожалуйста, ожидайте решения администратора.",
            'rejected': "К сожалению, ваша анкета была отклонена.",
            'approved': "🎉 Ваша анкета одобрена! Ожидайте назначения задания от администратора.",
            'archived_success': "Вы успешно завершили стажировку. Ваша анкета в архиве. Если появятся новые вакансии, мы сообщим."
        }
        await message.answer(status_messages.get(application.status, "Статус вашей анкеты неизвестен."))
    else:
        # --- ИСПРАВЛЕНИЕ: Вызываем правильную функцию клавиатуры ---
        await message.answer(
            "Открыта вакансия на позицию стажера!\n\n"
            "Мы ищем внимательных и ответственных людей для помощи в проверке заданий. "
            "Это отличная возможность заработать и понять, как все устроено изнутри.\n\n"
            "Готовы попробовать?",
            reply_markup=inline.get_internship_application_start_keyboard()
        )

# --- РАБОЧИЙ КАБИНЕТ СТАЖЕРА ---

async def show_intern_cabinet(message: Message, state: FSMContext):
    """Отображает рабочий кабинет активного стажера."""
    await state.set_state(UserState.MAIN_MENU)
    task = await db_manager.get_active_intern_task(message.from_user.id)
    user = await db_manager.get_user(message.from_user.id)
    
    if not task:
        await message.answer("Произошла ошибка: не найдено ваше активное задание. Обратитесь к администратору.")
        return

    salary = task.estimated_salary or 0.0
    penalty_per_error = (salary / task.goal_count) * 2 if task.goal_count > 0 else 0
    total_penalty = task.error_count * penalty_per_error
    final_salary = salary - total_penalty

    text = (
        "<b>Добро пожаловать в ваш рабочий кабинет!</b>\n\n"
        "<b>Ваше текущее задание:</b>\n"
        f" • Платформа: <code>{task.platform}</code>\n"
        f" • Тип задачи: <code>{task.task_type}</code>\n\n"
        "<b>Прогресс:</b>\n"
        f" • Выполнено: <b>{task.current_progress} / {task.goal_count}</b>\n"
        f" • Ошибок допущено: <b>{task.error_count}</b>\n\n"
        "<b>Расчетная зарплата:</b>\n"
        f" • Изначально: {salary:.2f} ⭐\n"
        f" • Штрафы: -{total_penalty:.2f} ⭐\n"
        f" • <b>К выплате: {final_salary:.2f} ⭐</b>"
    )
    await message.answer(text, reply_markup=inline.get_intern_cabinet_keyboard(is_busy=user.is_busy_intern))

@router.callback_query(F.data == "intern_cabinet:resign")
async def resign_request(callback: CallbackQuery):
    """Запрос подтверждения увольнения."""
    user = await db_manager.get_user(callback.from_user.id)
    if user.is_busy_intern:
        await callback.answer("Вы не можете уволиться, пока выполняете микро-задачу. Завершите ее и попробуйте снова.", show_alert=True)
        return
    
    await callback.message.edit_text(
        "Вы уверены, что хотите уволиться со стажировки? Весь текущий прогресс будет аннулирован.",
        reply_markup=inline.get_intern_resign_confirm_keyboard()
    )

@router.callback_query(F.data == "intern_cabinet:resign_confirm")
async def resign_confirm(callback: CallbackQuery, bot: Bot):
    """Подтверждение увольнения."""
    await db_manager.fire_intern(callback.from_user.id, "Уволился по собственному желанию")
    await callback.message.edit_text("Вы были уволены со стажировки.", reply_markup=inline.get_back_to_main_menu_keyboard())
    await bot.send_message(SUPER_ADMIN_ID, f"❗️ Стажер @{callback.from_user.username} (ID: {callback.from_user.id}) уволился по собственному желанию.")


@router.callback_query(F.data.startswith("intern_cabinet:mistakes"))
async def show_mistakes_history(callback: CallbackQuery, state: FSMContext):
    """Показывает историю ошибок стажера."""
    page = int(callback.data.split(":")[-1]) if ":" in callback.data else 1
    
    mistakes, total = await db_manager.get_intern_mistakes(callback.from_user.id, page=page)
    total_pages = ceil(total / 5) if total > 0 else 1
    
    text = "<b>📜 История ваших ошибок:</b>\n\n"
    if not mistakes:
        text += "Ошибок не найдено. Отличная работа!"
    else:
        for mistake in mistakes:
            date_str = mistake.created_at.strftime('%d.%m.%Y')
            text += (
                f"<b>Дата:</b> {date_str} | <b>Штраф:</b> {mistake.penalty_amount:.2f} ⭐\n"
                f"<b>Причина:</b> <i>{mistake.reason}</i>\n"
                f"<i>(ID отзыва: {mistake.review_id})</i>\n\n"
            )

    await callback.message.edit_text(
        text, 
        reply_markup=inline.get_pagination_keyboard("intern_cabinet:mistakes", page, total_pages, show_close=False, back_callback="internship_main")
    )

# --- FSM ДЛЯ ПОДАЧИ АНКЕТЫ ---

@router.callback_query(F.data.startswith("internship_app:start"))
async def start_application(callback: CallbackQuery, state: FSMContext):
    """Начало FSM или редактирование конкретного поля."""
    await callback.answer()
    field_to_edit = callback.data.split(":")[-1] if callback.data != "internship_app:start" else "age"
    
    if field_to_edit == "age":
        await state.set_state(UserState.INTERNSHIP_APP_AGE)
        prompt_msg = await callback.message.edit_text("Шаг 1/4: Укажите ваш возраст (например, 21).", reply_markup=inline.get_cancel_inline_keyboard("go_main_menu"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    elif field_to_edit == "hours":
        await state.set_state(UserState.INTERNSHIP_APP_HOURS)
        prompt_msg = await callback.message.edit_text("Шаг 2/4: Сколько часов в день вы готовы уделять работе?", reply_markup=inline.get_cancel_inline_keyboard("go_main_menu"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    elif field_to_edit == "response_time":
        await state.set_state(UserState.INTERNSHIP_APP_RESPONSE_TIME)
        prompt_msg = await callback.message.edit_text("Шаг 3/4: Насколько быстро вы обычно отвечаете на сообщения в Telegram?", reply_markup=inline.get_cancel_inline_keyboard("go_main_menu"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    elif field_to_edit == "platforms":
        await state.set_state(UserState.INTERNSHIP_APP_PLATFORMS)
        data = await state.get_data()
        selected = data.get("selected_platforms", set())
        prompt_msg = await callback.message.edit_text("Шаг 4/4: Выберите платформы.", reply_markup=inline.get_internship_platform_selection_keyboard(selected))
        await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(UserState.INTERNSHIP_APP_AGE)
async def process_age(message: Message, state: FSMContext):
    await delete_and_clear_prompt(message, state)
    
    if not message.text or not message.text.isdigit():
        msg = await message.answer("Пожалуйста, введите возраст числом.")
        await asyncio.sleep(10)
        try:
            await msg.delete()
        except TelegramBadRequest: pass
        # Повторно задаем вопрос
        prompt_msg = await message.answer("Шаг 1/4: Укажите ваш возраст (например, 21).", reply_markup=inline.get_cancel_inline_keyboard("go_main_menu"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    age = int(message.text)
    if not (15 <= age <= 60):
        msg = await message.answer("Пожалуйста, введите корректный возраст (от 15 до 60).")
        await asyncio.sleep(10)
        try:
            await msg.delete()
        except TelegramBadRequest: pass
        # Повторно задаем вопрос
        prompt_msg = await message.answer("Шаг 1/4: Укажите ваш возраст (например, 21).", reply_markup=inline.get_cancel_inline_keyboard("go_main_menu"))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        return

    await state.update_data(age=message.text)
    await state.set_state(UserState.INTERNSHIP_APP_HOURS)
    prompt_msg = await message.answer("Шаг 2/4: Сколько часов в день вы готовы уделять работе? (например, 3-4)")
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(UserState.INTERNSHIP_APP_HOURS)
async def process_hours(message: Message, state: FSMContext):
    await delete_and_clear_prompt(message, state)
    if not message.text:
        await message.answer("Пожалуйста, введите количество часов.")
        return
    await state.update_data(hours=message.text)
    await state.set_state(UserState.INTERNSHIP_APP_RESPONSE_TIME)
    prompt_msg = await message.answer("Шаг 3/4: Насколько быстро вы обычно отвечаете на сообщения в Telegram? (например, 'в течение 5 минут', 'сразу')")
    await state.update_data(prompt_message_id=prompt_msg.message_id)
    
@router.message(UserState.INTERNSHIP_APP_RESPONSE_TIME)
async def process_response_time(message: Message, state: FSMContext):
    await delete_and_clear_prompt(message, state)
    if not message.text:
        await message.answer("Пожалуйста, введите ваш ответ.")
        return
    await state.update_data(response_time=message.text)
    await state.set_state(UserState.INTERNSHIP_APP_PLATFORMS)
    
    data = await state.get_data()
    selected = data.get("selected_platforms", set())
    
    prompt_msg = await message.answer(
        "Шаг 4/4: Выберите платформы, с которыми вам было бы интересно работать. "
        "Можно выбрать несколько. Нажмите 'Далее', когда закончите.",
        reply_markup=inline.get_internship_platform_selection_keyboard(selected)
    )
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.callback_query(F.data.startswith("internship_toggle:"), UserState.INTERNSHIP_APP_PLATFORMS)
async def toggle_platform(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора платформ."""
    _, platform, platform_name = callback.data.split(":")
    data = await state.get_data()
    selected = data.get("selected_platforms", set())

    if platform_name in selected:
        selected.remove(platform_name)
    else:
        selected.add(platform_name)

    await state.update_data(selected_platforms=selected)
    
    await callback.message.edit_reply_markup(reply_markup=inline.get_internship_platform_selection_keyboard(selected))
    await callback.answer()


@router.callback_query(F.data == "internship_app:platforms_done", UserState.INTERNSHIP_APP_PLATFORMS)
async def platforms_done(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора платформ, показ анкеты на подтверждение."""
    data = await state.get_data()
    selected_platforms = data.get("selected_platforms")
    if not selected_platforms:
        await callback.answer("Пожалуйста, выберите хотя бы одну платформу.", show_alert=True)
        return
    
    await show_confirmation_screen(callback, state)

async def show_confirmation_screen(callback: CallbackQuery, state: FSMContext):
    """Отображает экран финального подтверждения анкеты."""
    await state.set_state(UserState.INTERNSHIP_APP_CONFIRM)
    data = await state.get_data()
    
    platforms_text = ", ".join(sorted(list(data.get("selected_platforms", set()))))
    
    confirmation_text = (
        "<b>Пожалуйста, проверьте вашу анкету:</b>\n\n"
        f"<b>Возраст:</b> {data.get('age')}\n"
        f"<b>Готовность работать:</b> {data.get('hours')} ч/день\n"
        f"<b>Скорость ответа:</b> {data.get('response_time')}\n"
        f"<b>Выбранные платформы:</b> {platforms_text}\n\n"
        "Все верно? Если хотите что-то изменить, нажмите на соответствующую кнопку."
    )
    
    await callback.message.edit_text(confirmation_text, reply_markup=inline.get_internship_confirmation_keyboard())


@router.callback_query(F.data == "internship_app:confirm", UserState.INTERNSHIP_APP_CONFIRM)
async def confirm_application(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Финальное подтверждение и отправка анкеты."""
    data = await state.get_data()
    
    platforms_text = ", ".join(sorted(list(data.get("selected_platforms", set()))))
    
    try:
        app = await db_manager.create_internship_application(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            age=data.get('age'),
            hours=data.get('hours'),
            response_time=data.get('response_time'),
            platforms=platforms_text
        )
        await callback.message.edit_text(
            "✅ Спасибо! Ваша анкета отправлена на рассмотрение. Мы сообщим вам о решении.",
            reply_markup=inline.get_back_to_main_menu_keyboard()
        )
        
        admin_text = (
            f"🔔 <b>Новая анкета на стажировку!</b>\n\n"
            f"От: @{callback.from_user.username} (<code>{callback.from_user.id}</code>)\n"
            f"Возраст: {data.get('age')}\n"
            f"Время: {data.get('hours')} ч/день\n"
            f"Скорость ответа: {data.get('response_time')}\n"
            f"Платформы: {platforms_text}\n\n"
            "Используйте /internships для просмотра."
        )
        await bot.send_message(SUPER_ADMIN_ID, admin_text)

    except Exception as e:
        logger.error(f"Failed to save internship application for user {callback.from_user.id}: {e}")
        await callback.message.edit_text("Произошла ошибка при сохранении анкеты. Попробуйте позже.", reply_markup=inline.get_back_to_main_menu_keyboard())
    
    await state.clear()