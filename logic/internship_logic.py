# file: logic/internship_logic.py

import re
import logging
from math import ceil
from typing import Tuple, Dict, Optional, List, Union # <<< ИСПРАВЛЕНИЕ: Добавлен импорт

from database.models import InternshipApplication, InternshipTask

logger = logging.getLogger(__name__)

# --- Функции форматирования для админ-панели ---

def format_applications_page(apps: List[InternshipApplication], page: int, total_pages: int) -> str:
    """Форматирует страницу со списком анкет."""
    if not apps:
        return "📝 <b>Анкеты на рассмотрении:</b>\n\nНовых анкет нет."
        
    text = "📝 <b>Анкеты на рассмотрении (нажмите для просмотра):</b>\n\n"
    for app in apps:
        date_str = app.created_at.strftime('%d.%m.%Y')
        text += f"• /view_app_{app.id} от @{app.username} ({date_str})\n"
        
    text += f"\nСтраница {page}/{total_pages}"
    return text

def format_single_application(app: InternshipApplication) -> str:
    """Форматирует текст для просмотра одной анкеты."""
    text = (
        f"<b>Анкета кандидата @{app.username}</b> (ID: <code>{app.user_id}</code>)\n\n"
        f"<b>Возраст:</b> {app.age}\n"
        f"<b>Готовность работать:</b> {app.hours_per_day} ч/день\n"
        f"<b>Желаемые платформы:</b> {app.platforms}\n"
        f"<b>Дата подачи:</b> {app.created_at.strftime('%d.%m.%Y %H:%M')} UTC"
    )
    return text

def format_candidates_page(candidates: List[InternshipApplication], page: int, total_pages: int) -> str:
    """Форматирует страницу со списком кандидатов."""
    if not candidates:
        return "🧑‍🎓 <b>Кандидаты (ожидают задания):</b>\n\nНет одобренных кандидатов."
    
    text = "🧑‍🎓 <b>Кандидаты (нажмите для назначения задания):</b>\n\n"
    for cand in candidates:
        text += f"• /assign_task_{cand.user_id} (@{cand.username})\n"
        
    text += f"\nСтраница {page}/{total_pages}"
    return text

def format_interns_page(interns: List[InternshipTask], page: int, total_pages: int) -> str:
    """Форматирует страницу со списком активных стажеров."""
    if not interns:
        return "👨‍💻 <b>Активные стажёры:</b>\n\nНет стажеров на задании."
        
    text = "👨‍💻 <b>Активные стажёры (нажмите для просмотра):</b>\n\n"
    for task in interns:
        username = f"@{task.intern.username}" if task.intern and task.intern.username else f"ID {task.intern_id}"
        text += f"• /view_intern_{task.intern_id} ({username}) - {task.platform}\n"
        
    text += f"\nСтраница {page}/{total_pages}"
    return text