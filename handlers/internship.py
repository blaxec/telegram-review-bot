# file: handlers/internship.py

import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder # <<< ИСПРАВЛЕНИЕ: Добавлен импорт

from states.user_states import UserState
from keyboards import inline, reply
from database import db_manager
from config import SUPER_ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)

# --- ГЛАВНЫЙ ОБРАБОТЧИК КНОПКИ "ВАКАНСИЯ" ---

@router.message(F.text == '💼 Вакансия', StateFilter("*"))
async def internship_entry_point(message: Message, state: FSMContext):
    """
    Высокоприоритетная точка входа в раздел стажировки.
    Проверяет статус пользователя и направляет в нужный раздел.
    """
    await state.clear() # Сбрасываем любое предыдущее состояние
    user_id = message.from_user.id
    user = await db_manager.get_user(user_id)

    # 1. Если пользователь - активный стажер
    if user and user.is_intern:
        await show_intern_cabinet(message)
        return

    # 2. Проверяем анкету
    application = await db_manager.get_internship_application(user_id)
    if application:
        if application.status == 'pending':
            await message.answer("⏳ Ваша анкета находится на рассмотрении. Пожалуйста, ожидайте решения администратора.")
        elif application.status == 'rejected':
            await message.answer("К сожалению, ваша анкета была отклонена.")
        elif application.status == 'approved':
            await message.answer("🎉 Ваша анкета одобрена! Ожидайте назначения задания от администратора.")
        elif application.status == 'archived_success':
             await message.answer("Вы успешно завершили стажировку. Ваша анкета в архиве. Если появятся новые вакансии, мы сообщим.")
    # 3. Если анкеты нет - предлагаем заполнить
    else:
        await message.answer(
            "Открыта вакансия на позицию стажера!\n\n"
            "Мы ищем внимательных и ответственных людей для помощи в проверке заданий. "
            "Это отличная возможность заработать и понять, как все устроено изнутри.\n\n"
            "Готовы попробовать?",
            reply_markup=inline.get_internship_application_start_keyboard()
        )

# --- РАБОЧИЙ КАБИНЕТ СТАЖЕРА ---

async def show_intern_cabinet(message: Message):
    """Отображает рабочий кабинет активного стажера."""
    task = await db_manager.get_active_intern_task(message.from_user.id)
    if not task:
        await message.answer("Произошла ошибка: не найдено ваше активное задание. Обратитесь к администратору.")
        return

    salary = task.estimated_salary
    penalty = task.error_count * (task.estimated_salary / task.goal_count) * 2 # Двойной штраф
    final_salary = salary - penalty

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
        f" • Штрафы: -{penalty:.2f} ⭐\n"
        f" • <b>К выплате: {final_salary:.2f} ⭐</b>"
    )

    await message.answer(text, reply_markup=inline.get_intern_cabinet_keyboard())

# --- FSM ДЛЯ ПОДАЧИ АНКЕТЫ ---

@router.callback_query(F.data == "internship_app:start")
async def start_application(callback: CallbackQuery, state: FSMContext):
    """Начало FSM: Запрос возраста."""
    await state.set_state(UserState.INTERNSHIP_APP_AGE)
    await callback.message.edit_text("Шаг 1/3: Укажите ваш возраст (например, 21).", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(UserState.INTERNSHIP_APP_AGE)
async def process_age(message: Message, state: FSMContext):
    """Обработка возраста и запрос часов."""
    if not message.text or not message.text.isdigit() or not (16 <= int(message.text) <= 60):
        await message.answer("Пожалуйста, введите корректный возраст (число от 16 до 60).")
        return
    await state.update_data(age=message.text)
    await state.set_state(UserState.INTERNSHIP_APP_HOURS)
    await message.answer("Шаг 2/3: Сколько часов в день вы готовы уделять работе? (например, 3-4)")

@router.message(UserState.INTERNSHIP_APP_HOURS)
async def process_hours(message: Message, state: FSMContext):
    """Обработка часов и запрос платформ."""
    if not message.text:
        await message.answer("Пожалуйста, введите количество часов.")
        return
    await state.update_data(hours=message.text)
    await state.set_state(UserState.INTERNSHIP_APP_PLATFORMS)
    await state.update_data(selected_platforms=set())
    await message.answer(
        "Шаг 3/3: Выберите платформы, с которыми вам было бы интересно работать. "
        "Можно выбрать несколько. Нажмите 'Далее', когда закончите.",
        reply_markup=inline.get_internship_platform_selection_keyboard()
    )

@router.callback_query(F.data.startswith("internship_toggle:"), UserState.INTERNSHIP_APP_PLATFORMS)
async def toggle_platform(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора платформ."""
    _, platform, platform_text = callback.data.split(":")
    data = await state.get_data()
    selected = data.get("selected_platforms", set())

    if platform in selected:
        selected.remove(platform)
    else:
        selected.add(platform)

    await state.update_data(selected_platforms=selected)

    # Обновляем клавиатуру, помечая выбранные элементы
    builder = InlineKeyboardBuilder()
    platforms_map = {
        "google": "Google Карты",
        "yandex_text": "Яндекс (с текстом)",
        "yandex_no_text": "Яндекс (без текста)"
    }
    for p_key, p_text in platforms_map.items():
        text = f"✅ {p_text}" if p_key in selected else p_text
        builder.button(text=text, callback_data=f"internship_toggle:{p_key}:{p_text}")
    
    builder.button(text="✅ Далее", callback_data="internship_app:platforms_done")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1)
    
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "internship_app:platforms_done", UserState.INTERNSHIP_APP_PLATFORMS)
async def platforms_done(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора платформ, показ анкеты на подтверждение."""
    data = await state.get_data()
    selected_platforms = data.get("selected_platforms")
    if not selected_platforms:
        await callback.answer("Пожалуйста, выберите хотя бы одну платформу.", show_alert=True)
        return
    
    await state.set_state(UserState.INTERNSHIP_APP_CONFIRM)
    
    platforms_text = ", ".join(sorted(list(selected_platforms)))
    
    confirmation_text = (
        "<b>Пожалуйста, проверьте вашу анкету:</b>\n\n"
        f"<b>Возраст:</b> {data.get('age')}\n"
        f"<b>Готовность работать:</b> {data.get('hours')} ч/день\n"
        f"<b>Выбранные платформы:</b> {platforms_text}\n\n"
        "Все верно?"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, отправить", callback_data="internship_app:confirm")
    builder.button(text="✏️ Начать заново", callback_data="internship_app:start")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1)
    
    await callback.message.edit_text(confirmation_text, reply_markup=builder.as_markup())


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
            platforms=platforms_text
        )
        await callback.message.edit_text(
            "✅ Спасибо! Ваша анкета отправлена на рассмотрение. Мы сообщим вам о решении.",
            reply_markup=inline.get_back_to_main_menu_keyboard()
        )
        
        # Уведомление админу
        admin_text = (
            f"🔔 <b>Новая анкета на стажировку!</b>\n\n"
            f"От: @{callback.from_user.username} (<code>{callback.from_user.id}</code>)\n"
            f"Возраст: {data.get('age')}\n"
            f"Время: {data.get('hours')} ч/день\n"
            f"Платформы: {platforms_text}\n\n"
            "Используйте /internships для просмотра."
        )
        await bot.send_message(SUPER_ADMIN_ID, admin_text)

    except Exception as e:
        logger.error(f"Failed to save internship application for user {callback.from_user.id}: {e}")
        await callback.message.edit_text("Произошла ошибка при сохранении анкеты. Попробуйте позже.", reply_markup=inline.get_back_to_main_menu_keyboard())
    
    await state.clear()