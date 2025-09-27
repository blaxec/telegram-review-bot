# file: handlers/posting.py

import asyncio
import json
import logging
from math import ceil
from typing import Set

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, InputMediaPhoto, InputMediaVideo,
                           Message)

from database import db_manager
from keyboards import inline
from states.user_states import AdminState
from utils.access_filters import IsSuperAdmin

router = Router()
logger = logging.getLogger(__name__)

# --- Вспомогательные функции ---

async def get_preview_text(state: FSMContext) -> str:
    """Генерирует текст для превью-сообщения на основе данных в FSM."""
    data = await state.get_data()
    post_text = data.get("post_text", "Текст еще не добавлен.")
    media_list = data.get("post_media", [])
    audience_set = data.get("post_audience", set())

    audience_map = {
        'all_users': 'Все пользователи',
        'admins': 'Администраторы',
        'super_admins': 'Главные админы',
        'testers': 'Тестировщики'
    }
    audience_str = ", ".join([audience_map.get(a, a) for a in audience_set]) or "Не выбрана"

    return (
        "<b>Конструктор постов</b>\n\n"
        "<i>Ниже показано, как будет выглядеть ваш пост. Используйте кнопки для редактирования.</i>\n"
        "-------------------------------------\n"
        f"{post_text}\n"
        "-------------------------------------\n"
        f"<i>Прикреплено медиа: {len(media_list)}</i>\n"
        f"<i>Аудитория: {audience_str}</i>"
    )

async def update_preview_message(message: Message, state: FSMContext):
    """Обновляет превью-сообщение, если оно существует."""
    if not message:
        return
    try:
        preview_text = await get_preview_text(state)
        await message.edit_text(
            preview_text,
            reply_markup=inline.get_post_constructor_keyboard(),
            disable_web_page_preview=True
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning(f"Error updating preview message: {e}")

# --- Основная логика ---

@router.message(F.text == '/posts', IsSuperAdmin())
async def start_post_constructor(message: Message, state: FSMContext):
    """Запускает FSM для создания поста."""
    await state.clear()
    await state.set_data({
        "post_text": "<b>Ваш пост.</b>\n\nВы можете использовать <b>HTML</b>-теги и ссылки: [Пример ссылки](https://google.com)",
        "post_media": [],
        "post_audience": set()
    })
    
    preview_text = await get_preview_text(state)
    preview_msg = await message.answer(
        preview_text,
        reply_markup=inline.get_post_constructor_keyboard(),
        disable_web_page_preview=True
    )
    await state.update_data(preview_message_id=preview_msg.message_id)

# --- Обработчики кнопок конструктора ---

@router.callback_query(F.data == "post_constructor:edit_text", IsSuperAdmin())
async def ask_for_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.POST_CONSTRUCTOR_AWAIT_TEXT)
    prompt_msg = await callback.message.answer(
        "Введите новый текст для поста. Для форматирования используйте HTML-теги или Markdown-ссылки вида `[текст](url)`.",
        reply_markup=inline.get_cancel_inline_keyboard("post_constructor:cancel_input")
    )
    await state.update_data(text_prompt_id=prompt_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "post_constructor:edit_media", IsSuperAdmin())
async def ask_for_media(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.POST_CONSTRUCTOR_AWAIT_MEDIA)
    data = await state.get_data()
    media_count = len(data.get("post_media", []))
    prompt_msg = await callback.message.answer(
        f"Отправьте фото, видео или GIF (до 10 файлов). Уже добавлено: {media_count}.\n"
        "Когда закончите, нажмите 'Готово'.",
        reply_markup=inline.get_post_media_keyboard()
    )
    await state.update_data(media_prompt_id=prompt_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "post_constructor:edit_audience", IsSuperAdmin())
async def show_audience_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    audience_set = data.get("post_audience", set())
    await callback.message.edit_reply_markup(
        reply_markup=inline.get_post_audience_keyboard(audience_set)
    )
    await callback.answer()

@router.callback_query(F.data == "post_constructor:send", IsSuperAdmin())
async def confirm_and_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("post_audience"):
        await callback.answer("❌ Сначала выберите аудиторию для рассылки!", show_alert=True)
        return
    if not data.get("post_text") and not data.get("post_media"):
        await callback.answer("❌ Нельзя отправить пустой пост!", show_alert=True)
        return

    user_ids = await db_manager.get_user_ids_for_broadcast(data["post_audience"])
    if not user_ids:
        await callback.answer("❌ В выбранной аудитории нет пользователей для рассылки.", show_alert=True)
        return

    await callback.message.edit_text(
        f"Вы уверены, что хотите отправить этот пост {len(user_ids)} пользователям?",
        reply_markup=inline.get_post_confirm_send_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "post_constructor:confirm_send", IsSuperAdmin())
async def start_broadcasting(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text("🚀 Рассылка запущена! Вы получите отчет по завершении.")
    await callback.answer()

    data = await state.get_data()
    user_ids = await db_manager.get_user_ids_for_broadcast(data.get("post_audience", set()))
    
    await state.clear()
    
    success_count, error_count = 0, 0
    start_time = asyncio.get_event_loop().time()

    for user_id in user_ids:
        try:
            media_list = data.get("post_media", [])
            text = data.get("post_text", "")
            
            if not media_list:
                await bot.send_message(user_id, text, reply_markup=inline.get_close_post_keyboard(), disable_web_page_preview=True)
            elif len(media_list) == 1:
                media = media_list[0]
                if media['type'] == 'photo':
                    await bot.send_photo(user_id, media['file_id'], caption=text, reply_markup=inline.get_close_post_keyboard())
                elif media['type'] == 'video':
                    await bot.send_video(user_id, media['file_id'], caption=text, reply_markup=inline.get_close_post_keyboard())
            else:
                media_group = []
                for i, media in enumerate(media_list):
                    InputMediaClass = InputMediaPhoto if media['type'] == 'photo' else InputMediaVideo
                    media_group.append(InputMediaClass(media=media['file_id'], caption=text if i == 0 else None))
                await bot.send_media_group(user_id, media_group)
                # Кнопку "закрыть" отправляем отдельным сообщением
                await bot.send_message(user_id, "...", reply_markup=inline.get_close_post_keyboard())

            success_count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            logger.warning(f"Broadcast failed for user {user_id}: bot blocked or chat not found.")
            error_count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {user_id} with unexpected error: {e}")
            error_count += 1
        
        await asyncio.sleep(0.1) # Пауза для избежания лимитов

    end_time = asyncio.get_event_loop().time()
    total_time = end_time - start_time
    
    report_text = (
        f"<b>Отчет о рассылке:</b>\n\n"
        f"✅ Успешно отправлено: {success_count}\n"
        f"❌ Ошибок: {error_count}\n"
        f"⏱️ Затрачено времени: {total_time:.2f} сек."
    )
    await bot.send_message(callback.from_user.id, report_text)

# --- Обработчики FSM ---

@router.message(AdminState.POST_CONSTRUCTOR_AWAIT_TEXT, F.text)
async def process_post_text(message: Message, state: FSMContext):
    await state.update_data(post_text=message.html_text) # Сохраняем с форматированием
    await state.set_state(None)

    data = await state.get_data()
    preview_msg = await bot.send_message(chat_id=message.chat.id, text="Обновляю превью...")
    await update_preview_message(preview_msg, state)

    # Удаляем старые сообщения
    try:
        await message.delete()
        if data.get('text_prompt_id'):
            await bot.delete_message(message.chat.id, data['text_prompt_id'])
        if data.get('preview_message_id'):
            await bot.delete_message(message.chat.id, data['preview_message_id'])
    except TelegramBadRequest:
        pass
    
    await state.update_data(preview_message_id=preview_msg.message_id)


@router.message(AdminState.POST_CONSTRUCTOR_AWAIT_MEDIA, F.photo | F.video)
async def process_post_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get("post_media", [])
    
    if len(media_list) >= 10:
        await message.answer("Достигнут лимит в 10 медиафайлов.")
        return

    if message.photo:
        media_list.append({"type": "photo", "file_id": message.photo[-1].file_id})
    elif message.video:
        media_list.append({"type": "video", "file_id": message.video.file_id})
    
    await state.update_data(post_media=media_list)
    await message.delete()
    # Обновляем сообщение с кнопками
    try:
        if data.get('media_prompt_id'):
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=data['media_prompt_id'],
                text=f"Отправьте фото, видео или GIF (до 10 файлов). Уже добавлено: {len(media_list)}.\nКогда закончите, нажмите 'Готово'.",
                reply_markup=inline.get_post_media_keyboard(has_media=True)
            )
    except TelegramBadRequest:
        pass

# --- Другие колбэки ---

@router.callback_query(F.data == "close_post")
async def close_post_handler(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        await callback.answer("Не удалось удалить сообщение.", show_alert=True)

@router.callback_query(F.data.startswith("post_audience:toggle:"), IsSuperAdmin())
async def toggle_audience(callback: CallbackQuery, state: FSMContext):
    audience = callback.data.split(":")[-1]
    data = await state.get_data()
    audience_set: Set[str] = data.get("post_audience", set())

    if audience in audience_set:
        audience_set.remove(audience)
    else:
        audience_set.add(audience)

    await state.update_data(post_audience=audience_set)
    await callback.message.edit_reply_markup(
        reply_markup=inline.get_post_audience_keyboard(audience_set)
    )
    await callback.answer()

@router.callback_query(F.data == "post_audience:back", IsSuperAdmin())
async def back_to_constructor(callback: CallbackQuery, state: FSMContext):
    await update_preview_message(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "post_constructor:cancel_input", StateFilter("*"), IsSuperAdmin())
async def cancel_text_input(callback: CallbackQuery, state: FSMContext):
    """Отменяет ввод текста/медиа и возвращает к конструктору."""
    await state.set_state(None)
    data = await state.get_data()
    # Удаляем сообщение с просьбой ввести данные
    prompt_id = data.get('text_prompt_id') or data.get('media_prompt_id')
    if prompt_id:
        try:
            await bot.delete_message(callback.message.chat.id, prompt_id)
        except TelegramBadRequest:
            pass
    # Обновляем главное превью
    preview_msg = await bot.send_message(chat_id=callback.message.chat.id, text="Обновляю превью...")
    await update_preview_message(preview_msg, state)
    # Удаляем старое превью
    if data.get('preview_message_id'):
        try:
            await bot.delete_message(callback.message.chat.id, data.get('preview_message_id'))
        except TelegramBadRequest: pass
    await state.update_data(preview_message_id=preview_msg.message_id)
    await callback.answer()