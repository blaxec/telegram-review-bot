# file: handlers/admin.py

import logging
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_ID_1, ADMIN_IDS, FINAL_CHECK_ADMIN
from database import db_manager
from references import reference_manager
from logic.admin_logic import *

router = Router()
logger = logging.getLogger(__name__)

ADMINS = set(ADMIN_IDS)
TEXT_ADMIN = ADMIN_ID_1

# --- ВАЖНО: Мы убрали общие фильтры с роутера и добавили их в каждый хендлер индивидуально ---

@router.message(Command("addstars"), F.from_user.id.in_(ADMINS))
async def admin_add_stars(message: Message):
    await db_manager.update_balance(message.from_user.id, 999.0)
    await message.answer("✅ На ваш баланс зачислено 999 ⭐.")


# --- БЛОК: УПРАВЛЕНИЕ ССЫЛКАМИ ---

@router.message(Command("admin_refs"), F.from_user.id.in_(ADMINS))
async def admin_refs_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())

@router.callback_query(F.data == "back_to_refs_menu", F.from_user.id.in_(ADMINS))
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

@router.callback_query(F.data.startswith("admin_refs:add:"), F.from_user.id.in_(ADMINS))
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

# ИСПРАВЛЕНИЕ: Убираем диагностический код и возвращаем рабочий обработчик
@router.message(
    F.from_user.id.in_(ADMINS),
    F.state.in_({AdminState.ADD_GOOGLE_REFERENCE, AdminState.ADD_YANDEX_REFERENCE}),
    F.text.as_("text")
)
async def admin_add_ref_process(message: Message, state: FSMContext, text: str):
    """Обрабатывает добавление ссылок с отловом ошибок."""
    try:
        data = await state.get_data()
        platform = data.get("platform")
        
        if not platform:
            await message.answer("❌ Произошла ошибка: не удалось определить платформу. Пожалуйста, начните заново.")
            await state.clear()
            return
        
        result_text = await process_add_links_logic(text, platform)
        
        await message.answer(result_text)
        # Возвращаем в главное меню админки ссылок
        await state.clear()
        await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    
    except Exception as e:
        logger.exception(f"Критическая ошибка в admin_add_ref_process для пользователя {message.from_user.id}: {e}")
        await message.answer("❌ Произошла критическая ошибка при добавлении ссылок. Обратитесь к логам.")
        await state.clear()


@router.callback_query(F.data.startswith("admin_refs:stats:"), F.from_user.id.in_(ADMINS))
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

@router.callback_query(F.data.startswith("admin_refs:list:"), F.from_user.id.in_(ADMINS))
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

@router.callback_query(F.data.startswith("admin_refs:delete:"), F.from_user.id.in_(ADMINS))
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


# --- БЛОК: МОДЕРАЦИЯ ---

@router.callback_query(F.data.startswith('admin_verify:'), F.from_user.id.in_(ADMINS))
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
        platform = "gmail" if "gmail" in context else context.split('_')[0]
        await admin_state.set_state(AdminState.PROVIDE_WARN_REASON)
        await admin_state.update_data(target_user_id=user_id, platform=platform, context=context)
        await bot.send_message(callback.from_user.id, f"✍️ Отправьте причину предупреждения для {user_id_str}.")

    elif action == "reject":
        action_text = f"❌ ОТКЛОНЕН (@{callback.from_user.username})"
        context_map = {"google_profile": "google_profile", "google_last_reviews": "google_last_reviews", "yandex_profile": "yandex_profile", "yandex_profile_screenshot": "yandex_profile", "gmail_device_model": "gmail_device_model"}
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

@router.message(AdminState.PROVIDE_WARN_REASON, F.from_user.id.in_(ADMINS))
async def process_warning_reason(message: Message, state: FSMContext, bot: Bot, dp: Dispatcher):
    if not message.text: return
    admin_data = await state.get_data()
    user_id, platform, context = admin_data.get("target_user_id"), admin_data.get("platform"), admin_data.get("context")
    if not all([user_id, platform, context]):
        await message.answer("Ошибка: не найдены данные. Состояние сброшено."); await state.clear(); return
    user_state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id))
    response = await process_warning_reason_logic(bot, user_id, platform, message.text, user_state, context)
    await message.answer(response)
    await state.clear()

@router.message(AdminState.PROVIDE_REJECTION_REASON, F.from_user.id.in_(ADMINS))
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

@router.message(
    F.state.in_({AdminState.PROVIDE_GOOGLE_REVIEW_TEXT, AdminState.PROVIDE_YANDEX_REVIEW_TEXT}),
    F.from_user.id == TEXT_ADMIN
)
async def admin_process_review_text(message: Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, dp: Dispatcher):
    if not message.text: return
    data = await state.get_data()
    success, response_text = await send_review_text_to_user_logic(
        bot=bot,
        dp=dp,
        scheduler=scheduler,
        user_id=data['target_user_id'],
        link_id=data['target_link_id'],
        platform=data['platform'],
        review_text=message.text
    )
    await message.answer(response_text)
    if success: await state.clear()


# --- БЛОК: МОДЕРАЦИЯ ОТЗЫВОВ (ФИНАЛЬНАЯ И В ХОЛДЕ) ---

@router.callback_query(F.data.startswith('admin_final_approve:'), F.from_user.id.in_(ADMINS))
async def admin_final_approve(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await approve_review_to_hold_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success:
        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ В ХОЛДЕ (@{callback.from_user.username})", reply_markup=None)

@router.callback_query(F.data.startswith('admin_final_reject:'), F.from_user.id.in_(ADMINS))
async def admin_final_reject(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await reject_initial_review_logic(review_id, bot, scheduler)
    await callback.answer(message_text, show_alert=True)
    if success:
        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ ОТКЛОНЕН (@{callback.from_user.username})", reply_markup=None)

@router.message(Command("reviewhold"), F.from_user.id.in_(ADMINS))
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

@router.callback_query(F.data.startswith('admin_hold_approve:'), F.from_user.id.in_(ADMINS))
async def admin_hold_approve_handler(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await approve_hold_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        new_caption = (callback.message.caption or "") + f"\n\n✅ ОДОБРЕН (@{callback.from_user.username})"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)

@router.callback_query(F.data.startswith('admin_hold_reject:'), F.from_user.id.in_(ADMINS))
async def admin_hold_reject_handler(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split(':')[1])
    success, message_text = await reject_hold_review_logic(review_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        new_caption = (callback.message.caption or "") + f"\n\n❌ ОТКЛОНЕН (@{callback.from_user.username})"
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)


# --- БЛОК: УПРАВЛЕНИЕ ВЫВОДОМ СРЕДСТВ ---

@router.callback_query(F.data.startswith("admin_withdraw_approve:"), F.from_user.id.in_(ADMINS))
async def admin_approve_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await approve_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        try:
            new_text = callback.message.text + f"\n\n**[ ✅ ВЫПЛАЧЕНО Администратором ]**"
            await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit withdrawal message in channel: {e}")

@router.callback_query(F.data.startswith("admin_withdraw_reject:"), F.from_user.id.in_(ADMINS))
async def admin_reject_withdrawal(callback: CallbackQuery, bot: Bot):
    request_id = int(callback.data.split(":")[1])
    success, message_text, _ = await reject_withdrawal_logic(request_id, bot)
    await callback.answer(message_text, show_alert=True)
    if success:
        try:
            new_text = callback.message.text + f"\n\n**[ ❌ ОТКЛОНЕНО Администратором ]**"
            await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit withdrawal message in channel: {e}")


# --- БЛОК: ПРОЧИЕ КОМАНДЫ ---

@router.message(Command("reset_cooldown"), F.from_user.id.in_(ADMINS))
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

@router.message(Command("viewhold"), F.from_user.id.in_(ADMINS))
async def viewhold_handler(message: Message, bot: Bot):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /viewhold ID_пользователя_или_@username")
        return
    identifier = args[1]
    response_text = await get_user_hold_info_logic(identifier)
    await message.answer(response_text)

@router.message(Command("fine"), F.from_user.id.in_(ADMINS))
async def fine_user_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.FINE_USER_ID)
    await message.answer("Введите ID или @username пользователя для штрафа.", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.FINE_USER_ID, F.from_user.id.in_(ADMINS))
async def fine_user_get_id(message: Message, state: FSMContext):
    if not message.text: return
    user_id = await db_manager.find_user_by_identifier(message.text)
    if not user_id:
        await message.answer(f"❌ Пользователь `{message.text}` не найден.", reply_markup=inline.get_cancel_inline_keyboard()); return
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminState.FINE_AMOUNT)
    await message.answer(f"Введите сумму штрафа (например, 10).", reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.FINE_AMOUNT, F.from_user.id.in_(ADMINS))
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

@router.message(AdminState.FINE_REASON, F.from_user.id.in_(ADMINS))
async def fine_user_get_reason(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Введите причину.", reply_markup=inline.get_cancel_inline_keyboard()); return
    data = await state.get_data()
    result_text = await apply_fine_to_user(data.get("target_user_id"), message.from_user.id, data.get("fine_amount"), message.text, bot)
    await message.answer(result_text)
    await state.clear()

# --- БЛОК: СОЗДАНИЕ ПРОМОКОДОВ ---

@router.message(Command("create_promo"), F.from_user.id.in_(ADMINS))
async def create_promo_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.PROMO_CODE_NAME)
    await message.answer("Введите название для нового промокода (например, `NEWYEAR2025`). Оно должно быть уникальным.",
                         reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.PROMO_CODE_NAME, F.from_user.id.in_(ADMINS))
async def promo_name_entered(message: Message, state: FSMContext):
    if not message.text: return
    promo_name = message.text.strip().upper()
    
    existing_promo = await db_manager.get_promo_by_code(promo_name)
    if existing_promo:
        await message.answer("❌ Промокод с таким названием уже существует. Пожалуйста, придумайте другое название.",
                             reply_markup=inline.get_cancel_inline_keyboard())
        return
        
    await state.update_data(promo_name=promo_name)
    await state.set_state(AdminState.PROMO_USES)
    await message.answer("Отлично. Теперь введите количество активаций (сколько раз пользователи смогут использовать этот промокод).",
                         reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.PROMO_USES, F.from_user.id.in_(ADMINS))
async def promo_uses_entered(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите целое число.", reply_markup=inline.get_cancel_inline_keyboard())
        return
    
    uses = int(message.text)
    if uses <= 0:
        await message.answer("❌ Количество активаций должно быть больше нуля.", reply_markup=inline.get_cancel_inline_keyboard())
        return

    await state.update_data(promo_uses=uses)
    await state.set_state(AdminState.PROMO_REWARD)
    await message.answer(f"Принято. Количество активаций: {uses}.\n\nТеперь введите сумму вознаграждения в звездах (например, `25`).",
                         reply_markup=inline.get_cancel_inline_keyboard())

@router.message(AdminState.PROMO_REWARD, F.from_user.id.in_(ADMINS))
async def promo_reward_entered(message: Message, state: FSMContext):
    try:
        reward = float(message.text)
        if reward <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Пожалуйста, введите положительное число (можно дробное, например `10.5`).",
                             reply_markup=inline.get_cancel_inline_keyboard())
        return
    
    await state.update_data(promo_reward=reward)
    await state.set_state(AdminState.PROMO_CONDITION)
    await message.answer(f"Принято. Награда: {reward} ⭐.\n\nТеперь выберите обязательное условие для получения награды.",
                         reply_markup=inline.get_promo_condition_keyboard())

@router.callback_query(F.data.startswith("promo_cond:"), AdminState.PROMO_CONDITION, F.from_user.id.in_(ADMINS))
async def promo_condition_selected(callback: CallbackQuery, state: FSMContext):
    condition = callback.data.split(":")[1]
    data = await state.get_data()
    
    new_promo = await db_manager.create_promo_code(
        code=data['promo_name'],
        total_uses=data['promo_uses'],
        reward=data['promo_reward'],
        condition=condition
    )
    
    if new_promo:
        await callback.message.edit_text(f"✅ Промокод `{new_promo.code}` успешно создан!")
    else:
        await callback.message.edit_text("❌ Произошла ошибка при создании промокода.")
        
    await state.clear()


# <<< ОБЫЧНЫЕ ДИАГНОСТИЧЕСКИЕ ОБРАБОТЧИКИ (можно оставить или удалить) >>>

@router.message(Command("testadmin"), F.from_user.id.in_(ADMINS))
async def admin_test_handler(message: Message):
    """Простейший обработчик для проверки, регистрируется ли роутер."""
    await message.answer("✅ Тест пройден! Роутер администратора работает.")

@router.message(Command("whatstate"))
async def get_current_state(message: Message, state: FSMContext):
    """Команда для получения текущего состояния FSM."""
    current_state = await state.get_state()
    await message.answer(f"Ваше текущее состояние: `{current_state}`")