
import logging
from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
# from apscheduler.schedulers.asyncio import AsyncIOScheduler # Временно не нужен

from states.user_states import UserState, AdminState
from keyboards import inline, reply
from config import ADMIN_ID_1, ADMIN_IDS, FINAL_CHECK_ADMIN
from database import db_manager
from references import reference_manager
from logic.admin_logic import process_add_links_logic

router = Router()
logger = logging.getLogger(__name__)

ADMINS = set(ADMIN_IDS)
TEXT_ADMIN = ADMIN_ID_1


# --- ЭТОТ БЛОК ОСТАЕТСЯ РАБОЧИМ ---

@router.message(Command("admin_refs"), F.from_user.id.in_(ADMINS))
async def admin_refs_menu(message: Message, state: FSMContext):
    """Основной обработчик, который мы тестируем."""
    # Мы не используем FSM в этом тесте, поэтому clear() не нужен,
    # но и не повредит, если машина состояний будет подключена позже.
    if state:
        await state.clear()
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())

@router.callback_query(F.data == "back_to_refs_menu", F.from_user.id.in_(ADMINS))
async def back_to_refs_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("admin_refs:add:"), F.from_user.id.in_(ADMINS))
async def admin_add_ref_start(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(':')[2]
    # Временно не используем FSM для чистоты теста
    await callback.message.edit_text(f"ТЕСТ: Отправьте ссылки для **{platform}**.", reply_markup=inline.get_back_to_admin_refs_keyboard())
    await callback.answer()


@router.message(F.text, F.from_user.id.in_(ADMINS))
async def admin_add_ref_process(message: Message, state: FSMContext):
    """
    Упрощенный обработчик для приема ссылок без состояний.
    Он будет реагировать на любое текстовое сообщение от админа.
    """
    # Для теста считаем, что любая ссылка - это google_maps
    platform = "google_maps" 
    text = message.text
    
    # Временно отключаем работу с БД для чистоты теста
    # result_text = await process_add_links_logic(text, platform)
    
    result_text = f"✅ ТЕСТ: Получен текст для добавления ссылок:\n---\n{text}\n---"
    
    await message.answer(result_text)
    await message.answer("Меню управления ссылками:", reply_markup=inline.get_admin_refs_keyboard())


# --- ВСЕ ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ВРЕМЕННО ОТКЛЮЧЕНЫ ---

@router.callback_query(F.data.startswith("admin_refs:stats:"), F.from_user.id.in_(ADMINS))
async def admin_view_refs_stats(callback: CallbackQuery):
    await callback.answer("Функция статистики временно отключена для диагностики.", show_alert=True)

@router.callback_query(F.data.startswith("admin_refs:list:"), F.from_user.id.in_(ADMINS))
async def admin_view_refs_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Функция просмотра списка временно отключена для диагностики.", show_alert=True)

@router.callback_query(F.data.startswith("admin_refs:delete:"), F.from_user.id.in_(ADMINS))
async def admin_delete_ref(callback: CallbackQuery):
    await callback.answer("Функция удаления временно отключена для диагностики.", show_alert=True)

@router.callback_query(F.data.startswith('admin_verify:'), F.from_user.id.in_(ADMINS))
async def admin_verification_handler(callback: CallbackQuery):
     await callback.answer("Функция верификации временно отключена для диагностики.", show_alert=True)

@router.message(Command("reviewhold"), F.from_user.id.in_(ADMINS))
async def admin_review_hold(message: Message):
    await message.answer("Функция просмотра холда временно отключена для диагностики.")

@router.message(Command("addstars"), F.from_user.id.in_(ADMINS))
async def admin_add_stars(message: Message):
    await message.answer("Функция добавления звезд временно отключена для диагностики.")

@router.message(Command("reset_cooldown"), F.from_user.id.in_(ADMINS))
async def reset_cooldown_handler(message: Message):
    await message.answer("Функция сброса кулдаунов временно отключена для диагностики.")

@router.message(Command("viewhold"), F.from_user.id.in_(ADMINS))
async def viewhold_handler(message: Message):
    await message.answer("Функция просмотра холда пользователя временно отключена для диагностики.")

@router.message(Command("fine"), F.from_user.id.in_(ADMINS))
async def fine_user_start(message: Message):
    await message.answer("Функция штрафов временно отключена для диагностики.")

@router.message(Command("create_promo"), F.from_user.id.in_(ADMINS))
async def create_promo_start(message: Message):
    await message.answer("Функция создания промокодов временно отключена для диагностики.")