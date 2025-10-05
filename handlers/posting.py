# file: handlers/posting.py

import asyncio
import json
import logging
import re
from math import ceil
from typing import Set, List, Dict, Any, Union, Optional
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, InputMediaPhoto, InputMediaVideo, InputMediaAnimation,
                           Message, InlineKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db_manager
from keyboards import inline
from states.user_states import AdminState
from utils.access_filters import IsSuperAdmin

router = Router()
logger = logging.getLogger(__name__)


# --- Вспомогательные функции ---

def build_post_keyboard(buttons_data: List[Dict[str, str]]) -> Optional[InlineKeyboardMarkup]:
    """Строит инлайн-клавиатуру на основе данных из состояния FSM."""
    if not buttons_data:
        return None
    builder = InlineKeyboardBuilder()
    for button in buttons_data:
        # Простая проверка URL
        url = button['url']
        if not url.startswith(('http://', 'https://', 'tg://')):
             url = f"http://{url}" # Пытаемся исправить, если протокол не указан

        builder.button(text=button['text'], url=url)
    builder.adjust(1)
    return builder.as_markup()

async def get_preview_text(state: FSMContext) -> str:
    """Генерирует текст для превью-сообщения на основе данных в FSM."""
    data = await state.get_data()
    post_text = data.get("post_text", "")
    media_list = data.get("post_media", [])
    buttons_list = data.get("post_buttons", [])

    audience_list = data.get("post_audience", [])
    audience_map = { 'all_users': 'Все пользователи', 'admins': 'Администраторы', 'super_admins': 'Главные админы', 'testers': 'Тестировщики' }
    audience_str = ", ".join([audience_map.get(a, a) for a in audience_list]) or "Не выбрана"

    media_info = []
    for i, media in enumerate(media_list, 1):
        media_info.append(f"{i}. {media['type'].capitalize()}")
    media_str = "\n".join(media_info) if media_info else "Нет"

    buttons_info = []
    for i, button in enumerate(buttons_list, 1):
        buttons_info.append(f"{i}. [{button['text']}] -> {button['url']}")
    buttons_str = "\n".join(buttons_info) if buttons_info else "Нет"

    return (
        "<b>Конструктор постов</b>\n\n"
        "<i>Ниже показано, как будет выглядеть ваш пост. Используйте кнопки для редактирования.</i>\n"
        "-------------------------------------\n"
        f"{post_text if post_text else 'Текст еще не добавлен.'}\n"
        "-------------------------------------\n"
        f"<b>Прикрепленные медиа ({len(media_list)}/10):</b>\n{media_str}\n\n"
        f"<b>Прикрепленные кнопки:</b>\n{buttons_str}\n\n"
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
        # Пытаемся построить клавиатуру для проверки ссылок
        test_keyboard = build_post_keyboard(data.get("post_buttons", []))
        
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
            # Если ошибка в кнопках, уведомляем админа
            if "BUTTON_URL_INVALID" in str(e) or "buttons" in str(e).lower():
                 await bot.send_message(chat_id, "⚠️ Ошибка в URL кнопок. Проверьте правильность ссылок.")

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

def validate_url(url: str) -> bool:
    """Простая валидация URL."""
    # Разрешаем http, https и tg ссылки
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
        r'localhost|' # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    tg_regex = re.compile(r'^tg://\S+$', re.IGNORECASE)

    return re.match(regex, url) is not None or re.match(tg_regex, url) is not None or url.startswith('/') # Разрешаем внутренние ссылки бота

# --- Основная логика ---

@router.message(Command("posts"), IsSuperAdmin())
async def start_post_constructor(message: Message, state: FSMContext):
    try: await message.delete()
    except TelegramBadRequest: pass

    await state.clear()
    await state.set_state(AdminState.POST_CONSTRUCTOR)
    initial_data = { "post_text": "", "post_media": [], "post_buttons": [], "post_audience": [] }
    await state.set_data(initial_data)
    
    preview_text = await get_preview_text(state)
    preview_msg = await message.answer(
        preview_text,
        reply_markup=inline.get_post_constructor_keyboard(initial_data),
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
            # ИСПРАВЛЕНИЕ: Указан правильный режим разметки в подсказке
            prompt_msg = await callback.message.answer("Введите новый текст для поста. Для форматирования используйте HTML.", reply_markup=inline.get_cancel_inline_keyboard("post:cancel_input"))
            await state.update_data(prompt_message_id=prompt_msg.message_id)
            await callback.answer()
    elif action == "edit_media":
        await state.update_data(awaiting_input='media')
        media_count = len(data.get("post_media", []))
        # ИСПРАВЛЕНИЕ: Лимит увеличен до 10
        prompt_msg = await callback.message.answer(f"Отправьте фото или видео. Лимит: 10 медиа. Добавлено: {media_count}.\nКогда закончите, нажмите 'Готово'.", reply_markup=inline.get_post_media_keyboard(has_media=bool(data.get('post_media'))))
        await state.update_data(prompt_message_id=prompt_msg.message_id)
        await callback.answer()
    elif action == "view_media":
        media_list = data.get("post_media", [])
        if not media_list:
            await callback.answer("Медиа не прикреплены.", show_alert=True)
            return
        await callback.message.edit_reply_markup(reply_markup=inline.get_post_media_preview_keyboard(media_list))
    elif action == "edit_buttons":
        buttons_list = data.get("post_buttons", [])
        await callback.message.edit_reply_markup(reply_markup=inline.get_post_buttons_manage_keyboard(buttons_list))
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
        
        # Проверка кнопок перед отправкой
        try:
            build_post_keyboard(data.get("post_buttons", []))
        except Exception as e:
             await callback.answer(f"❌ Ошибка в кнопках (неверные URL). Исправьте перед отправкой.", show_alert=True)
             return

        user_ids = await db_manager.get_user_ids_for_broadcast(data.get("post_audience", []))
        await callback.message.edit_text(f"Вы уверены, что хотите отправить этот пост {len(user_ids)} пользователям?", reply_markup=inline.get_post_confirm_send_keyboard())
    elif action == "show_format_help":
        await callback.answer("Отправляю инструкцию...", show_alert=False)
        # ИСПРАВЛЕНИЕ: Рабочие HTML теги
        help_text = (
            "<b>Доступные HTML теги:</b>\n\n"
            "&lt;b&gt;Жирный&lt;/b&gt; -> <b>Жирный</b>\n"
            "&lt;i&gt;Курсив&lt;/i&gt; -> <i>Курсив</i>\n"
            "&lt;u&gt;Подчеркнутый&lt;/u&gt; -> <u>Подчеркнутый</u>\n"
            "&lt;s&gt;Зачеркнутый&lt;/s&gt; -> <s>Зачеркнутый</s>\n"
            "&lt;code&gt;Моноширинный&lt;/code&gt; -> <code>Моноширинный</code>\n"
            "&lt;a href='http://google.com'&gt;Ссылка&lt;/a&gt; -> <a href='http://google.com'>Ссылка</a>\n"
            "&lt;tg-spoiler&gt;Спойлер&lt;/tg-spoiler&gt; -> <tg-spoiler>Спойлер</tg-spoiler>"
        )
        await callback.message.answer(
            help_text,
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
        # Если были в подменю, возвращаемся в него
        current_sub_menu = data.get('current_sub_menu')
        if current_sub_menu == 'buttons':
             await callback.message.edit_reply_markup(reply_markup=inline.get_post_buttons_manage_keyboard(data.get("post_buttons", [])))
        else:
             await update_preview_message(bot, callback.from_user.id, state)

    elif action == "media_done":
        await state.update_data(awaiting_input=None)
        if data.get('prompt_message_id'):
            try: await bot.delete_message(callback.from_user.id, data.get('prompt_message_id'))
            except TelegramBadRequest: pass
        await update_preview_message(bot, callback.from_user.id, state)
        await callback.answer("Медиа сохранены.")
    elif action == "back_to_constructor":
        await state.update_data(current_sub_menu=None)
        await update_preview_message(bot, callback.from_user.id, state)
        await callback.answer()

# --- Обработка медиа (удаление по одному) ---
@router.callback_query(F.data.startswith("post_media:delete:"), AdminState.POST_CONSTRUCTOR)
async def delete_single_media(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.split(":")[2])
        data = await state.get_data()
        media_list = data.get("post_media", [])
        
        if 0 <= index < len(media_list):
            deleted = media_list.pop(index)
            await state.update_data(post_media=media_list)
            await callback.answer(f"Удалено: {deleted['type']}")
            # Обновляем клавиатуру списка медиа
            if media_list:
                await callback.message.edit_reply_markup(reply_markup=inline.get_post_media_preview_keyboard(media_list))
            else:
                # Если медиа не осталось, возвращаемся в конструктор
                await update_preview_message(callback.bot, callback.from_user.id, state)
        else:
            await callback.answer("Ошибка: медиа не найдено.", show_alert=True)
            
    except (ValueError, IndexError):
        await callback.answer("Ошибка при удалении.", show_alert=True)

# --- Обработка кнопок (добавление, удаление) ---
@router.callback_query(F.data == "post_btn:add_start", AdminState.POST_CONSTRUCTOR)
async def add_button_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminState.POST_AWAITING_BUTTON_TEXT)
    await state.update_data(current_sub_menu='buttons') # Запоминаем, где мы
    prompt_msg = await callback.message.answer("Введите текст для кнопки:", reply_markup=inline.get_cancel_inline_keyboard("post:cancel_input"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.callback_query(F.data.startswith("post_btn:delete:"), AdminState.POST_CONSTRUCTOR)
async def delete_button(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.split(":")[2])
        data = await state.get_data()
        buttons_list = data.get("post_buttons", [])
        
        if 0 <= index < len(buttons_list):
            deleted = buttons_list.pop(index)
            await state.update_data(post_buttons=buttons_list)
            await callback.answer(f"Кнопка '{deleted['text']}' удалена.")
            # Обновляем клавиатуру управления кнопками
            await callback.message.edit_reply_markup(reply_markup=inline.get_post_buttons_manage_keyboard(buttons_list))
        else:
            await callback.answer("Ошибка: кнопка не найдена.", show_alert=True)
            
    except (ValueError, IndexError):
        await callback.answer("Ошибка при удалении.", show_alert=True)


# --- FSM Handlers для ввода текста/медиа/кнопок ---
@router.message(AdminState.POST_CONSTRUCTOR, F.text)
async def process_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    awaiting_input = data.get("awaiting_input")

    if awaiting_input == 'text':
        # ИСПРАВЛЕНИЕ: Используем message.html_text для сохранения форматирования
        await state.update_data(post_text=message.html_text)
        await delete_and_clear_prompt(message, state)
        await update_preview_message(bot, message.from_user.id, state)
        
    elif awaiting_input == 'save_template_name':
        template_name = message.text.strip()
        media_list = data.get("post_media", [])
        buttons_list = data.get("post_buttons", [])
        success, result_msg = await db_manager.save_post_template(
            template_name,
            data.get("post_text"),
            json.dumps(media_list),
            json.dumps(buttons_list), # Сохраняем кнопки
            message.from_user.id
        )
        await message.answer(result_msg, reply_markup=inline.get_close_post_keyboard())
        await delete_and_clear_prompt(message, state)
        await update_preview_message(bot, message.from_user.id, state)

@router.message(AdminState.POST_AWAITING_BUTTON_TEXT, F.text)
async def process_button_text(message: Message, state: FSMContext):
    """Получен текст кнопки, запрашиваем URL."""
    btn_text = message.text.strip()
    if not btn_text:
        msg = await message.answer("Текст кнопки не может быть пустым.")
        await asyncio.sleep(3)
        try: await msg.delete()
        except: pass
        return

    await state.update_data(temp_button_text=btn_text)
    await delete_and_clear_prompt(message, state)
    
    await state.set_state(AdminState.POST_AWAITING_BUTTON_URL)
    prompt_msg = await message.answer(f"Введите ссылку (URL) для кнопки '{btn_text}':", reply_markup=inline.get_cancel_inline_keyboard("post:cancel_input"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)

@router.message(AdminState.POST_AWAITING_BUTTON_URL, F.text)
async def process_button_url(message: Message, state: FSMContext, bot: Bot):
    """Получен URL кнопки, сохраняем."""
    url = message.text.strip()
    
    # Простая валидация
    if not url.startswith(('http://', 'https://', 'tg://')):
        # Пробуем добавить https
        url_with_https = f"https://{url}"
        # Можно добавить более сложную проверку, но пока так
        url = url_with_https

    data = await state.get_data()
    btn_text = data.get("temp_button_text")
    buttons_list = data.get("post_buttons", [])
    
    buttons_list.append({"text": btn_text, "url": url})
    await state.update_data(post_buttons=buttons_list, temp_button_text=None)
    
    await delete_and_clear_prompt(message, state)
    await state.set_state(AdminState.POST_CONSTRUCTOR)
    
    # Обновляем превью, которое должно быть в истории выше
    await update_preview_message(bot, message.from_user.id, state)
    
    # Возвращаем меню управления кнопками
    preview_msg_id = data.get("preview_message_id")
    if preview_msg_id:
        try:
             # Т.к. мы удалили промпт, нужно обновить клавиатуру на превью сообщении
             await bot.edit_message_reply_markup(
                 chat_id=message.chat.id,
                 message_id=preview_msg_id,
                 reply_markup=inline.get_post_buttons_manage_keyboard(buttons_list)
             )
        except Exception as e:
            logger.error(f"Could not update buttons menu: {e}")


@router.message(AdminState.POST_CONSTRUCTOR, F.photo | F.video | F.animation)
async def process_media_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if data.get("awaiting_input") != 'media':
        return

    media_list = data.get("post_media", [])
    
    new_media = None
    # ИСПРАВЛЕНИЕ: Логика для 10 медиа или 1 GIF
    has_gif = any(m['type'] == 'gif' for m in media_list)
    
    if message.animation:
        if media_list:
            msg = await message.answer("GIF можно добавить только один и без других медиа. Удалите текущие медиа сначала.")
            await asyncio.sleep(5)
            try: await msg.delete()
            except: pass
            return
        new_media = {"type": "gif", "file_id": message.animation.file_id}
    elif has_gif:
         msg = await message.answer("Нельзя добавлять другие медиа, если уже добавлен GIF.")
         await asyncio.sleep(5)
         try: await msg.delete()
         except: pass
         return
    elif len(media_list) >= 10:
        msg = await message.answer("Достигнут лимит в 10 медиа.")
        await asyncio.sleep(5)
        try: await msg.delete()
        except: pass
        return
    elif message.photo:
        new_media = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        new_media = {"type": "video", "file_id": message.video.file_id}
        
    if new_media:
        media_list.append(new_media)
        await state.update_data(post_media=media_list)
        
    try:
        await message.delete() # Удаляем сообщение с медиа от пользователя
    except TelegramBadRequest: pass

    prompt_id = data.get('prompt_message_id')
    if prompt_id:
        try:
            media_status = "GIF добавлен (лимит исчерпан)" if message.animation else f"Добавлено: {len(media_list)}/10"
            await bot.edit_message_text(
                chat_id=message.chat.id, message_id=prompt_id,
                text=f"Отправьте фото или видео. {media_status}.\nКогда закончите, нажмите 'Готово'.",
                reply_markup=inline.get_post_media_keyboard(has_media=True)
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                 logger.warning(f"Error updating media prompt: {e}")

# --- Шаблоны ---
@router.callback_query(F.data == "post_constructor:save_template", AdminState.POST_CONSTRUCTOR)
async def save_template_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(awaiting_input='save_template_name')
    prompt_msg = await callback.message.answer("Введите название для нового шаблона:", reply_markup=inline.get_cancel_inline_keyboard("post:cancel_input"))
    await state.update_data(prompt_message_id=prompt_msg.message_id)

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
        post_text=template.text or "",
        post_media=json.loads(template.media_json or "[]"),
        post_buttons=json.loads(template.buttons_json or "[]")
    )
    await update_preview_message(bot, callback.from_user.id, state)
    await callback.answer("Шаблон загружен.")

# --- Рассылка ---
@router.callback_query(F.data == "post_constructor:confirm_send", AdminState.POST_CONSTRUCTOR)
async def start_broadcasting(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text("🚀 Рассылка запущена! Вы получите отчет по завершении.")
    await callback.answer()

    data = await state.get_data()
    audience_list = data.get("post_audience", [])
    user_ids = await db_manager.get_user_ids_for_broadcast(audience_list)
    
    # Сохраняем данные перед очисткой состояния
    media_list = data.get("post_media", [])
    text = data.get("post_text", "")
    buttons_data = data.get("post_buttons", [])
    keyboard = build_post_keyboard(buttons_data)

    await state.clear() # Очищаем состояние админа
    
    success_count, error_count = 0, 0
    start_time = asyncio.get_event_loop().time()

    # ИСПРАВЛЕНИЕ: Используем HTML parse_mode, так как текст сохранен как HTML
    parse_mode = "HTML"

    for user_id in user_ids:
        try:
            if not media_list:
                await bot.send_message(user_id, text, reply_markup=keyboard, disable_web_page_preview=True, parse_mode=parse_mode)
            elif len(media_list) == 1:
                media = media_list[0]
                if media['type'] == 'photo':
                    await bot.send_photo(user_id, media['file_id'], caption=text, reply_markup=keyboard, parse_mode=parse_mode)
                elif media['type'] == 'video':
                    await bot.send_video(user_id, media['file_id'], caption=text, reply_markup=keyboard, parse_mode=parse_mode)
                elif media['type'] == 'gif':
                    await bot.send_animation(user_id, media['file_id'], caption=text, reply_markup=keyboard, parse_mode=parse_mode)
            else:
                media_group = []
                for i, media in enumerate(media_list):
                    InputMediaClass = InputMediaPhoto if media['type'] == 'photo' else InputMediaVideo
                    # Подпись только к первому медиа, parse_mode тут не нужен, он задается при отправке группы
                    media_group.append(InputMediaClass(media=media['file_id'], caption=text if i == 0 else None, parse_mode=parse_mode if i==0 else None)) 
                
                # Отправляем медиагруппу (подпись прикрепится к первому файлу)
                await bot.send_media_group(user_id, media_group)
                
                # Если есть кнопки, отправляем их отдельным сообщением
                if keyboard:
                    # Небольшая пауза, чтобы порядок сообщений не нарушился
                    await asyncio.sleep(0.05)
                    await bot.send_message(user_id, "👇", reply_markup=keyboard)

            success_count += 1
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.info(f"Broadcast skipped for user {user_id}: {e.message}")
            error_count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {user_id} with unexpected error: {e}")
            error_count += 1
        
        await asyncio.sleep(0.05) # Пауза между пользователями

    end_time = asyncio.get_event_loop().time()
    total_time = end_time - start_time
    
    report_text = (
        f"<b>Отчет о рассылке:</b>\n\n"
        f"✅ Успешно отправлено: {success_count}\n"
        f"❌ Не доставлено (блок/ошибка): {error_count}\n"
        f"⏱️ Затрачено времени: {total_time:.2f} сек."
    )
    try:
        await bot.send_message(callback.from_user.id, report_text)
    except:
        logger.error("Could not send broadcast report to admin.")

# --- Обработчики аудитории ---
@router.callback_query(F.data.startswith("post_audience:toggle:"), AdminState.POST_CONSTRUCTOR)
async def toggle_audience(callback: CallbackQuery, state: FSMContext, bot: Bot):
    audience_key = callback.data.split(":")[-1]
    data = await state.get_data()
    audience_list = data.get("post_audience", [])

    if audience_key in audience_list:
        audience_list.remove(audience_key)
    else:
        audience_list.append(audience_key)

    await state.update_data(post_audience=audience_list)
    
    # ИСПРАВЛЕНИЕ: Обновляем превью, чтобы показать изменения
    await update_preview_message(bot, callback.from_user.id, state)
    
    # Обновляем саму клавиатуру аудитории (если она была открыта)
    try:
         await callback.message.edit_reply_markup(reply_markup=inline.get_post_audience_keyboard(audience_list))
    except TelegramBadRequest:
         pass # Могло быть вызвано из другого меню

    await callback.answer()