
import asyncio
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_ID_1, ADMIN_IDS, FINAL_CHECK_ADMIN
from database import db_manager
from references import reference_manager
from logic.admin_logic import (
    process_rejection_reason_logic, 
    process_warning_reason_logic,
    send_review_text_to_user_logic,
    apply_fine_to_user,
    approve_review_to_hold_logic,
    reject_initial_review_logic,
    approve_hold_review_logic,
    reject_hold_review_logic,
    approve_withdrawal_logic,
    reject_withdrawal_logic
)

router = Router()
logger = logging.getLogger(__name__)

ADMINS = set(ADMIN_IDS)
TEXT_ADMIN = ADMIN_ID_1

# Фильтры для всех обработчиков в этом роутере
router.message.filter(F.from_user.id.in_(ADMINS))
router.callback_query.filter(F.from_user.id.in_(ADMINS))

@router.message(Command("addstars"))
async def admin_add_stars(message: Message):
    await db_manager.update_balance(message.from_user.id, 999.0)
    await message.answer("✅ На ваш баланс зачислено 999 ⭐.")


# --- БЛОК: УПРАВЛЕНИЕ ССЫЛКАМИ ---

@router.message(Command("admin_refs"), F.from_user.id == ADMIN_ID_1)
async def admin_refs_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())

@router.callback_query(F.data == "back_to_refs_menu", F.from_user.id == ADMIN_ID_1)
async def back_to_refs_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    message_ids_to_delete = data.get("link_message_ids", [])
    message_ids_to_delete.append(callback.message.message_id)
    for msg_id in set(message_ids_to_delete):
        try: await bot.delete_message(chat_id=callback.from_user.id, message_id=msg_id)
        except TelegramBadRequest: pass
    await state.clear()
    await bot.send_message(callback.from_user.id, "Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    try: await callback.answer()
    except: pass

@router.callback_query(F.data.startswith("admin_refs:add:"), F.from_user.id == ADMIN_ID_1)
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    try: await callback.answer()
    except TelegramBadRequest: pass
    platform = callback.data.split(':')[2]
    state_map = {"google_maps": AdminState.ADD_GOOGLE_REFERENCE, "yandex_maps": AdminState.ADD_YANDEX_REFERENCE}
    current_state = state_map.get(platform)
    if current_state:
        await state.set_state(current_state)
        await state.update_data(platform=platform)
        await callback.message.edit_text(f"Отправьте ссылки для **{platform}**, каждую с новой строки.", reply_markup=inline.get_back_to_admin_refs_keyboard())

@router.message(F.state.in_({AdminState.ADD_GOOGLE_REFERENCE, AdminState.ADD_YANDEX_REFERENCE}))
async def admin_add_ref_process(message: Message, state: FSMContext):
    if not message.text: return
    links = message.text.split('\n')
    added_count, skipped_count = 0, 0
    platform = (await state.get_data()).get("platform")
    for link in links:
        link = link.strip()
        if link and link.startswith("http"):
            if await reference_manager.add_reference(link, platform): added_count += 1
            else: skipped_count += 1
    await message.answer(f"Готово!\n✅ Добавлено: {added_count}\n⏭️ Пропущено: {skipped_count}")
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    await state.clear()

@router.callback_query(F.data.startswith("admin_refs:stats:"), F.from_user.id == ADMIN_ID_1)
async def admin_view_refs_stats(callback: CallbackQuery):
    try: await callback.answer("Загружаю...", show_alert=False)
    except: pass
    platform = callback.data.split(':')[2]
    all_links = await reference_manager.get_all_references(platform)
    stats = {status: len([link for link in all_links if link.status == status]) for status in ['available', 'assigned', 'used']}
    text = (f"📊 Статистика по **{platform}**:\n\n"
            f"Всего: {len(all_links)}\n"
            f"🟢 Доступно: {stats['available']}\n🟡 В работе: {stats['assigned']}\n🔴 Использовано: {stats['used']}")
    await callback.message.edit_text(text, reply_markup=inline.get_back_to_admin_refs_keyboard())

@router.callback_query(F.data.startswith("admin_refs:list:"), F.from_user.id == ADMIN_ID_1)
async def admin_view_refs_list(callback: CallbackQuery, state: FSMContext):
    try: await callback.answer("Загружаю список...")
    except: pass
    platform = callback.data.split(':')[2]
    all_links = await reference_manager.get_all_references(platform)
    await callback.message.edit_text(f"Список ссылок для **{platform}**:", reply_markup=inline.get_back_to_admin_refs_keyboard())
    if not all_links:
        await callback.message.answer("В базе нет ссылок для этой платформы.")
        return
    message_ids = []
    for link in all_links:
        icons = {"available": "🟢", "assigned": "🟡", "used": "🔴", "expired": "⚫"}
        user_info = f"-> ID: {link.assigned_to_user_id}" if link.assigned_to_user_id else ""
        text = f"{icons.get(link.status, '❓')} **ID:{link.id}** | `{link.status}` {user_info}\n🔗 `{link.url}`"
        msg = await callback.message.answer(text, reply_markup=inline.get_delete_ref_keyboard(link.id), disable_web_page_preview=True)
        message_ids.append(msg.message_id)
    await state.update_data(link_message_ids=message_ids)

@router.callback_query(F.data.startswith("admin_refs:delete:"), F.from_user.id == ADMIN_ID_1)
async def admin_delete_ref(callback: CallbackQuery, bot: Bot, dp: Dispatcher):
    link_id = int(callback.data.split(':')[2])
    success, assigned_user_id = await reference_manager.delete_reference(link_id)
    if not success:
        try: await callback.answer("Не удалось удалить ссылку.", show_alert=True)
        except: pass
        return
    await callback.message.delete()
    try: await callback.answer(f"Ссылка ID {link_id} удалена.", show_alert=True)
    except: pass
    if assigned_user_id:
        try:
            user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=assigned_user_id, chat_id=assigned_user_id))
            await user_state.clear()
            await bot.send_message(assigned_user_id, "❗️ Ссылка для вашего задания была удалена. Процесс остановлен.", reply_markup=reply.get_main_menu_keyboard())
            await user_state.set_state(UserState.MAIN_MENU)
        except Exception as e: logger.warning(f"Не удалось уведомить {assigned_user_id} об удалении ссылки: {e}")


# --- БЛОК: МОДЕРАЦИЯ (ВЕРИФИКАЦИЯ, ПРЕДУПРЕЖДЕНИЯ, ОТКЛОНЕНИЯ) ---

@router.callback_query(F.data.startswith('admin_verify:'))
async def admin_verification_handler(callback: CallbackQuery, state: FSMContext, bot: Bot, dp: Dispatcher):
    try: await callback.answer()
    except: pass
    _, action, context, user_id_str = callback.data.split(':')
    user_id = int(user_id_str)
    admin_state = state
    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    original_text = callback.message.text or callback.message.caption
    action_text = ""
    
    if action == "confirm":
        action_text = f"✅ ПОДТВЕРЖДЕНО (@{callback.from_user.username})"
        if context == "google_profile":
            await user_state.set_state(UserState.GOOGLE_REVIEW_LAST_REVIEWS_CHECK)
            await bot.send_message(user_id, "Профиль прошел проверку. Пришлите скриншот последних отзывов.", reply_markup=inline.get_google_last_reviews_check_keyboard())
        elif context == "google_last_reviews":
            await user_state.set_state(UserState.GOOGLE_REVIEW_READY_TO_CONTINUE)
            await bot.send_message(user_id, "Отзывы прошли проверку. Можете продолжить.", reply_markup=inline.get_google_continue_writing_keyboard())
        elif "yandex_profile" in context:
            await user_state.set_state(UserState.YANDEX_REVIEW_READY_TO_TASK)
            await bot.send_message(user_id, "Профиль Yandex прошел проверку. Можете продолжить.", reply_markup=inline.get_yandex_continue_writing_keyboard())
        elif context == "gmail_device_model":
            await admin_state.set_state(AdminState.ENTER_GMAIL_DATA)
            await admin_state.update_data(gmail_user_id=user_id)
            await bot.send_message(callback.from_user.id, "✅ Модель подтверждена.\nВведите данные для аккаунта:\nИмя\nФамилия\nПароль\nПочта (без @gmail.com)")
    
    elif action == "warn":
        action_text = f"⚠️ ВЫДАЧА ПРЕДУПРЕЖДЕНИЯ (@{callback.from_user.username})"
        await admin_state.set_state(AdminState.PROVIDE_WARN_REASON)
        await admin_state.update_data(target_user_id=user_id, platform=context.split('_')[0])
        await bot.send_message(callback.from_user.id, f"✍️ Отправьте причину предупреждения для {user_id_str}.")

    elif action == "reject":
        action_text = f"❌ ОТКЛОНЕН (@{callback.from_user.username})"
        context_map = {"google_profile": "google_profile", "google_last_reviews": "google_last_reviews", "yandex_profile": "yandex_profile", "yandex_profile_screenshot": "yandex_profile", "gmail_device_model": "gmail_data_request"}
        rejection_context = context_map.get(context)
        if rejection_context:
            await admin_state.set_state(AdminState.PROVIDE_REJECTION_REASON)
            await admin_state.update_data(target_user_id=user_id, rejection_context=rejection_context)
            await bot.send_message(callback.from_user.id, f"✍️ Отправьте причину отклонения для {user_id_str}.")
        else:
            await bot.send_message(callback.from_user.id, "Ошибка: неизвестный контекст.")
    
    try:
        if callback.message.photo: await callback.message.edit_caption(caption=f"{original_text}\n\n{action_text}", reply_markup=None)
        else: await callback.message.edit_text(f"{original_text}\n\n{action_text}", reply_markup=None)
    except TelegramBadRequest: pass


# --- БЛОК: ОБРАБОТКА ТЕКСТОВЫХ ВВОДОВ ОТ АДМИНА ---

@router.message(AdminState.PROVIDE_WARN_REASON)
async def process_warning_reason(message: Message, state: FSMContext, bot: Bot, dp: Dispatcher):
    if not message.text: return
    admin_data = await state.get_data()
    user_id, platform = admin_data.get("target_user_id"), admin_data.get("platform")
    if not user_id or not platform:
        await message.answer("Ошибка: не найдены данные. Состояние сброшено."); await state.clear(); return
    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    response = await process_warning_reason_logic(bot, user_id, platform, message.text, user_state)
    await message.answer(response)
    await state.clear()

@router.message(AdminState.PROVIDE_REJECTION_REASON)
async def process_rejection_reason(message: Message, state: FSMContext, bot: Bot, dp: Dispatcher):
    if not message.text: return
    admin_data = await state.get_data()
    user_id, context = admin_data.get("target_user_id"), admin_data.get("rejection_context")
    if not user_id:
        await message.answer("Ошибка: не найден ID. Состояние сброшено."); await state.clear(); return
    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    response = await process_rejection_reason_logic(bot, user_id, message.text, context, user_state)
    await message.answer(response)
    await state.clear()

@router.callback_query(F.data.startswith('admin_provide_text:'), F.from_user.id == TEXT_ADMIN)
async def admin_start_providing_text(callback: CallbackQuery, state: FSMContext):
    try:
        _, platform, user_id_str, link_id_str = callback.data.split(':')
        state_map = {'google': AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, 'yandex': AdminState.PROVIDE_YANDEX_REVIEW_TEXT}
        if platform not in state_map: await callback.answer("Ошибка платформы."); return
        await state.set_state(state_map[platform])
        await state.update_data(target_user_id=int(user_id_str), target_link_id=int(link_id_str), platform=platform)
        
        edit_text = f"✍️ Введите текст отзыва для ID: {user_id_str}"
        new_content = f"{(callback.message.caption or callback.message.text)}\n\n{edit_text}"
        if callback.message.photo: await callback.message.edit_caption(caption=new_content, reply_markup=None)
        else: await callback.message.edit_text(new_content, reply_markup=None)
    except Exception as e: logger.warning(f"Error in admin_start_providing_text: {e}")

@router.message(F.state.in_({AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, AdminState.PROVIDE_YANDEX_REVIEW_TEXT}))
async def admin_process_review_text(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, dp: Dispatcher):
    if not message.text: return
    data = await state.get_data()
    success, response_text = await send_review_text_to_user_logic(bot, dp, scheduler, **data, review_text=message.text)
    await message.answer(response_text)
    if success: await state.clear()


# --- БЛОК: МОДЕРАЦИЯ ОТЗЫВОВ (ФИНАЛЬНАЯ И В ХОЛДЕ) ---

@router.callback_query(F.data.startswith('admin_final_approve:'))
async def admin_final_approve(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    try: await callback.answer()
    except: pass
    review_id = int(callback.data.split(':')[1])
    success, message_text = await approve_review_to_hold_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success:
        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ В ХОЛДЕ (@{callback.from_user.username})", reply_markup=None)

@router.callback_query(F.data.startswith('admin_final_reject:'))
async def admin_final_reject(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    try: await callback.answer()
    except: pass
    review_id = int(callback.data.split(':')[1])
    success, message_text = await reject_initial_review_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success:
        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ ОТКЛОНЕН (@{callback.from_user.username})", reply_markup=None)

@router.message(Command("reviewhold"))
async def admin_review_hold(message: Message, bot: Bot):
    await message.answer("⏳ Загружаю отзывы в холде...")
    hold_reviews = await db_manager.get_all_hold_reviews()
    if not hold_reviews:
        await message.answer("В холде нет отзывов."); return
    await message.answer(f"Найдено отзывов: {len(hold_reviews)}")
    for review in hold_reviews:
        link_url = review.link.url if review.link else "Ссылка удалена"
        info_text = (f"ID: `{review.id}` | User: `{review.user_id}`\nПлатформа: `{review.platform}` | Сумма: `{review.amount}` ⭐\n"
                     f"Ссылка: `{link_url}`\nТекст: «_{review.review_text}_»")
        try:
            if review.admin_message_id:
                await bot.copy_message(message.chat.id, FINAL_CHECK_ADMIN, review.admin_message_id, caption=info_text, reply_markup=inline.get_admin_hold_review_keyboard(review.id))
            else:
                await message.answer(info_text, reply_markup=inline.get_admin_hold_review_keyboard(review.id))
        except Exception as e:
            await message.answer(f"Ошибка обработки отзыва {review.id}: {e}\n\n{info_text}", reply_markup=inline.get_admin_hold_review_keyboard(review.id))

@router.callback_query(F.data.startswith('admin_hold_approve:'))
async def admin_hold_approve_handler(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await approve_hold_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        new_caption = (callback.message.caption or "") + f"\n\n✅ ОДОБРЕН (@{callback.from_user.username})"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)

@router.callback_query(F.data.startswith('admin_hold_reject:'))
async def admin_hold_reject_handler(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await reject_hold_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        new_caption = (callback.message.caption or "") + f"\n\n❌ ОТКЛОНЕН (@{callback.from_user.username})"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)


# --- БЛОК: УПРАВЛЕНИЕ ВЫВОДОМ СРЕДСТВ ---

@router.callback_query(F.data.startswith("admin_withdraw_approve:"))
async def admin_approve_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await approve_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        new_text = callback.message.text + f"\n\n**[ ✅ ПОДТВЕРЖДЕНО @{callback.from_user.username} ]**"
        await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)

@router.callback_query(F.data.startswith("admin_withdraw_reject:"))
async def admin_reject_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await reject_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        new_text = callback.message.text + f"\n\n**[ ❌ ОТКЛОНЕНО @{callback.from_user.username} ]**"
        await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)


# --- БЛОК: ПРОЧИЕ КОМАНДЫ (/reset_cooldown, /fine) ---

@router.message(Command("reset_cooldown"), F.from_user.id == ADMIN_ID_1)
async def reset_cooldown_handler(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используйте: `/reset_cooldown ID_или_@username`"); return
    user_id = await db_manager.find_user_by_identifier(args[1])
    if not user_id:
        await message.answer(f"❌ Пользователь `{args[1]}` не найден."); return
    if await db_manager.reset_user_cooldowns(user_id):
        user = await db_manager.get_user(user_id)
        username = f"@{user.username}" if user.username else f"ID: {user_id}"
        await message.answer(f"✅ Кулдауны для **{username}** сброшены.")
    else: await message.answer(f"❌ Ошибка при сбросе кулдаунов для `{args[1]}`.")

@router.message(Command("fine"))
async def fine_user_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.FINE_USER_ID)
    await message.answer("Введите ID или @username пользователя для штрафа.", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.FINE_USER_ID)
async def fine_user_get_id(message: Message, state: FSMContext):
    if not message.text: return
    user_id = await db_manager.find_user_by_identifier(message.text)
    if not user_id:
        await message.answer(f"❌ Пользователь `{message.text}` не найден.", reply_markup=inline.get_cancel_inline_keyboard()); return
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminState.FINE_AMOUNT)
    await message.answer(f"Введите сумму штрафа (например, 10).", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.FINE_AMOUNT)
async def fine_user_get_amount(message: Message, state: FSMContext):
    if not message.text: return
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Введите положительное число.", reply_markup=inline.get_cancel_inline_keyboard()); return
    await state.update_data(fine_amount=amount)
    await state.set_state(AdminState.FINE_REASON)
    await message.answer("Введите причину штрафа.", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.FINE_REASON)
async def fine_user_get_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Введите причину.", reply_markup=inline.get_cancel_inline_keyboard()); return
    data = await state.get_data()
    result_text = await apply_fine_to_user(data.get("target_user_id"), message.from_user.id, data.get("fine_amount"), message.text, bot)
    await message.answer(result_text)
    await state.clear()