# file: handlers/admin_stats.py

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from database import db_manager
from keyboards import inline
from utils.access_filters import IsSuperAdmin

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("stats_admin"), IsSuperAdmin())
async def get_admin_stats(message: Message):
    """Отображает расширенную бизнес-аналитику."""
    try:
        await message.delete()
    except:
        pass

    stats = await db_manager.get_extended_admin_stats()

    text = (
        "📈 **Бизнес-Аналитика**\n\n"
        "**Выполненные отзывы:**\n"
        f" • Сегодня: `{stats['reviews_today']}`\n"
        f" • За 7 дней: `{stats['reviews_7_days']}`\n"
        f" • За 30 дней: `{stats['reviews_30_days']}`\n\n"
        "**Выплаты за отзывы:**\n"
        f" • Сегодня: `{stats['paid_today']:.2f} ⭐`\n"
        f" • За 7 дней: `{stats['paid_7_days']:.2f} ⭐`\n"
        f" • За 30 дней: `{stats['paid_30_days']:.2f} ⭐`\n\n"
        f"**Средняя награда за отзыв (30 дн):** `{stats['avg_reward']:.2f} ⭐`\n\n"
        "**🏆 Топ-5 активных пользователей (30 дн):**\n"
        f"{stats['top_5_active']}\n\n"
        "**⚠️ Пользователи 'группы риска' (30 дн):**\n"
        f"{stats['top_5_rejected']}"
    )
    await message.answer(text, reply_markup=inline.get_close_post_keyboard())

@router.message(Command("campaigns"), IsSuperAdmin())
async def list_campaigns(message: Message):
    """Показывает список кампаний для просмотра статистики."""
    try:
        await message.delete()
    except:
        pass
    
    tags = await db_manager.get_all_campaign_tags()
    if not tags:
        await message.answer("Кампании с тегами еще не создавались.", reply_markup=inline.get_close_post_keyboard())
        return

    await message.answer("Выберите кампанию для просмотра статистики:", reply_markup=inline.get_campaign_list_keyboard(tags))

@router.callback_query(F.data.startswith("campaign_stats:"))
async def show_campaign_stats(callback: CallbackQuery):
    tag = callback.data.split(":", 1)[1]
    stats = await db_manager.get_stats_for_campaign(tag)

    if not stats:
        await callback.answer("Не удалось получить статистику для этой кампании.", show_alert=True)
        return

    text = (
        f"📊 **Статистика по кампании: `{tag}`**\n\n"
        f"Всего ссылок: `{stats.get('total', 0)}`\n\n"
        f"🟢 Доступно: `{stats.get('available', 0)}`\n"
        f"🟡 В работе: `{stats.get('assigned', 0)}`\n"
        f"🔴 Использовано: `{stats.get('used', 0)}`\n"
        f"⚫ Просрочено: `{stats.get('expired', 0)}`"
    )

    await callback.message.edit_text(text, reply_markup=inline.get_back_to_campaigns_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_campaigns")
async def back_to_campaign_list(callback: CallbackQuery):
    tags = await db_manager.get_all_campaign_tags()
    await callback.message.edit_text("Выберите кампанию для просмотра статистики:", reply_markup=inline.get_campaign_list_keyboard(tags))