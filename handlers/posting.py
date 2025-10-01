# file: handlers/posting.py

import asyncio
import json
import logging
from math import ceil
from typing import Set, List, Dict, Any
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter, Command
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
    post_text = data.get("post_text", "")
    media_list = data.get("post_media", [])
    
    audience_list = data.get("post_audience", [])
    audience_map = { 'all_users': 'Все пользователи', 'admins': 'Администраторы', 'super_admins': 'Главные админы', 'testers': 'Тестировщики' }
    audience_str = ", ".join([audience_map.get(a, a) for a in audience_list]) or "Не выбрана"

    media_info = []
    for i, media in enumerate(media_list, 1):
        media_info.append(f"{i}. {media['type'].capitalize()}")
    media_str = "\n".join(media_info) if media_info else "Нет"

    return (
        "<b>Конструктор постов</b>\n\n"
        "<i>Ниже показано, как будет выглядеть ваш пост. Используйте кнопки для редактирования.</i>\n"
        "-------------------------------------\n"
        f"{post_text if post_text else 'Текст еще не добавлен.'}\n"
        "-------------------------------------\n"
        f"<b>Прикрепленные медиа:</b>\n{media_str}\n\n"
        f"<b>Аудитория:</b> {audience_str}"
    )

async def update_preview_message(bot: Bot, chat_id: int, state: FSMContext):
    """Обновляет превью-сообщение, если оно существует."""
    data = await state.get_data()
    preview_message_id = data.get("preview_message_id")
    if not preview_message_id:
        return
        
    try:
        preview_text = await get_preview_text(state)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=preview_message_id,
            text=preview_text,
            reply_markup=inline.get_post_constructor_keyboard(data),
            disable_web_page_preview=True
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning(f"Error updating preview message: {e}")

async def delete_and_clear_prompt(message: Message, state: FSMContext):
    """Удаляет сообщение пользователя и предыдущее сообщение-приглашение от бота."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_message_id)
        except TelegramBadRequest: pass
    try:
        await message.delete()
    except TelegramBadRequest: pass
    await state.update_data(awaiting_input=None, prompt_message_id=None)

# --- Основная логика ---

@router.message(Command("posts"), IsSuperAdmin())
async def start_post_constructor(message: Message, state: FSMContext):
    try: await message.delete()
    except TelegramBadRequest: pass

    await state.clear()
    await state.set_state(AdminState.POST_CONSTRUCTOR)
    await state.update_data({ "post_text": "", "post_media": [], "post_audience": [] })
    
    preview_text = await get_preview_text(state)
    preview_msg = await message.answer(
        preview_text,
        reply_markup=inline.get_post_constructor_keyboard(await state.get_data()),
        disable_web_page_preview=True
    )
    await state.update_data(preview_message_id=preview_msg.message_id)

# --- Обработчики кнопок конструктора ---

@router.callback_query(F.data.startswith("post_constructor:"), AdminState.POST_CONSTRUCTOR)
async def constructor_actions(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split(":")[1]
    data = await state.get_data()

    if action == "edit_text" or action == "delete_text":
        if action == "delete_text":
            await state.update_data(post_text="")
            await update_preview_message(bot, callback.from_user.id, state)
            await callback.answer("Текст удален.")
        else:
            await state.update_data(awaiting_input='text')
            prompt_msg = await callback.message.answer("Введите новый текст для поста. Для форматирования используйте HTML-теги.", reply_markup=inline.get_cancel_inline_keyboard("post:cancel_input"))
            await state.update_data(prompt_message_id=prompt_msg.message_id)
            await callback.answer()
    elif action == "edit_media":
        await state.update_data(awaiting_input='media')
        media_count = len(data.get("post_media", []))
        prompt_msg = await callback.message.answer(f"Отправьте фото, видео или GIF. Лимит: 3 медиа (GIF = 3). Добавлено: {media_count}.\nКогда закончите, нажмите 'Готово'.", reply_markup=inline.get_post_media_keyboard())
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        await callback.answer()
    elif action == "view_media":
        media_list = data.get("post_media", [])
        if not media_list:
            await callback.answer("Медиа не прикреплены.", show_alert=True)
            return
        await callback.message.edit_reply_markup(reply_markup=inline.get_post_media_preview_keyboard(media_list))
    elif action == "edit_audience":
        audience_list = data.get("post_audience", [])
        await callback.message.edit_reply_markup(reply_markup=inline.get_post_audience_keyboard(audience_list))
    elif action == "send":
        if not data.get("post_audience"):
            await callback.answer("❌ Сначала выберите аудиторию!", show_alert=True)
            return
        if not data.get("post_text") and not data.get("post_media"):
            await callback.answer("❌ Нельзя отправить пустой пост!", show_alert=True)
            return
        user_ids = await db_manager.get_user_ids_for_broadcast(data.get("post_audience", []))
        await callback.message.edit_text(f"Вы уверены, что хотите отправить этот пост {len(user_ids)} пользователям?", reply_markup=inline.get_post_confirm_send_keyboard())
    elif action == "show_format_help":
        await callback.answer("Отправляю инструкцию...", show_alert=False)
        await callback.message.answer(
            "<b>HTML теги для форматирования:</b>\n"
            "<code>&lt;b&gt;<b>Жирный</b>&lt;/b&gt;</code>\n"
            "<code>&lt;i&gt;<i>Курсив</i>&lt;/i&gt;</code>\n"
            "<code>&lt;u&gt;<u>Подчеркнутый</u>&lt;/u&gt;</code>\n"
            "<code>&lt;s&gt;<s>Зачеркнутый</s>&lt;/s&gt;</code>\n"
            "<code>&lt;code&gt;Моноширинный текст&lt;/code&gt;</code>\n"
            "<code>&lt;a href='https://t.me'&gt;Ссылка в тексте&lt;/a&gt;</code>\n",
            reply_markup=inline.get_close_post_keyboard()
        )

@router.callback_query(F.data.startswith("post:"), AdminState.POST_CONSTRUCTOR)
async def constructor_sub_actions(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split(":")[1]
    data = await state.get_data()

    if action == "cancel_input":
        await state.update_data(awaiting_input=None)
        if data.get('prompt_message_id'):
            try: await bot.delete_message(callback.from_user.id, data.get('prompt_message_id'))
            except TelegramBadRequest: pass
        await callback.answer("Ввод отменен.")
    elif action == "media_done":
        await state.update_data(awaiting_input=None)
        if data.get('prompt_message_id'):
            try: await bot.delete_message(callback.from_user.id, data.get('prompt_message_id'))
            except TelegramBadRequest: pass
        await update_preview_message(bot, callback.from_user.id, state)
        await callback.answer("Медиа добавлены.")
    elif action == "back_to_constructor":
        await update_preview_message(bot, callback.from_user.id, state)
        await callback.answer()

# --- FSM Handlers ---
@router.message(AdminState.POST_CONSTRUCTOR, F.text)
async def process_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    awaiting_input = data.get("awaiting_input")

    if awaiting_input == 'text':
        await state.update_data(post_text=message.html_text)
        await delete_and_clear_prompt(message, state)
        await update_preview_message(bot, message.from_user.id, state)
    elif awaiting_input == 'save_template_name':
        template_name = message.text.strip()
        media_list = data.get("post_media", [])
        success, result_msg = await db_manager.save_post_template(template_name, data.get("post_text"), json.dumps(media_list), message.from_user.id)
        await message.answer(result_msg, reply_markup=inline.get_close_post_keyboard())
        await delete_and_clear_prompt(message, state)
        await update_preview_message(bot, message.from_user.id, state)

@router.message(AdminState.POST_CONSTRUCTOR, F.photo | F.video | F.animation)
async def process_media_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if data.get("awaiting_input") != 'media':
        return

    media_list = data.get("post_media", [])
    current_weight = sum(m.get('weight', 1) for m in media_list)
    
    new_media = None
    if message.animation:
        if current_weight > 0:
            await message.answer("GIF можно добавить только о и он займет все 3 слота.")
            return
        new_media = {"type": "gif", "file_id": message.animation.file_id, "weight": 3}
    elif current_weight >= 3:
        await message.answer("Достигнут лимит в 3 медиа.")
        return
    elif message.photo:
        new_media = {"type": "photo", "file_id": message.photo[-1].file_id, "weight": 1}
    elif message.video:
        new_media = {"type": "video", "file_id": message.video.file_id, "weight": 1}
        
    if new_media:
        media_list.append(new_media)
        await state.update_data(post_media=media_list)
        await message.delete()

        prompt_id = data.get('prompt_message_id')
        if prompt_id:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id, message_id=prompt_id,
                    text=f"Отправьте фото, видео или GIF. Лимит: 3 медиа (GIF = 3). Добавлено: {len(media_list)}.\nКогда закончите, нажмите 'Готово'.",
                    reply_markup=inline.get_post_media_keyboard()
                )
            except TelegramBadRequest: pass

# --- Шаблоны ---
@router.callback_query(F.data == "post_constructor:load_template", AdminState.POST_CONSTRUCTOR)
async def show_templates(callback: CallbackQuery, state: FSMContext):
    templates = await db_manager.get_all_post_templates()
    await callback.message.edit_reply_markup(reply_markup=inline.get_post_template_list_keyboard(templates))
    await callback.answer()

@router.callback_query(F.data.startswith("post_template:load:"), AdminState.POST_CONSTRUCTOR)
async def load_template(callback: CallbackQuery, state: FSMContext, bot: Bot):
    template_id = int(callback.data.split(":")[-1])
    template = await db_manager.get_post_template_by_id(template_id)
    if not template:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    
    await state.update_data(
        post_text=template.text,
        post_media=json.loads(template.media_json or "[]")
    )
    await update_preview_message(bot, callback.from_user.id, state)
    await callback.answer("Шаблон загружен.")

# ... (остальные обработчики: удаление, отправка, и т.д. остаются похожими, но используют новые функции)

@router.callback_query(F.data == "post_constructor:confirm_send", AdminState.POST_CONSTRUCTOR)
async def start_broadcasting(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text("🚀 Рассылка запущена! Вы получите отчет по завершении.")
    await callback.answer()

    data = await state.get_data()
    audience_list = data.get("post_audience", [])
    user_ids = await db_manager.get_user_ids_for_broadcast(audience_list)
    
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
                elif media['type'] == 'gif':
                    await bot.send_animation(user_id, media['file_id'], caption=text, reply_markup=inline.get_close_post_keyboard())
            else:
                media_group = []
                for i, media in enumerate(media_list):
                    InputMediaClass = InputMediaPhoto if media['type'] == 'photo' else InputMediaVideo
                    media_group.append(InputMediaClass(media=media['file_id'], caption=text if i == 0 else None))
                await bot.send_media_group(user_id, media_group)
                # Отправляем отдельное сообщение, чтобы прикрепить кнопку
                await bot.send_message(user_id, "⠀", reply_markup=inline.get_close_post_keyboard())

            success_count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            logger.warning(f"Broadcast failed for user {user_id}: bot blocked or chat not found.")
            error_count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {user_id} with unexpected error: {e}")
            error_count += 1
        
        await asyncio.sleep(0.1) 

    end_time = asyncio.get_event_loop().time()
    total_time = end_time - start_time
    
    report_text = (
        f"<b>Отчет о рассылке:</b>\n\n"
        f"✅ Успешно отправлено: {success_count}\n"
        f"❌ Ошибок: {error_count}\n"
        f"⏱️ Затрачено времени: {total_time:.2f} сек."
    )
    await bot.send_message(callback.from_user.id, report_text)