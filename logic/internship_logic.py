# file: logic/internship_logic.py

import re
import logging
from math import ceil
from typing import Tuple, Dict, Optional, List, Union

from database.models import InternshipApplication, InternshipTask, User

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

def format_interns_page(interns: List[User], page: int, total_pages: int) -> str:
    """Форматирует страницу со списком активных стажеров."""
    if not interns:
        return "👨‍💻 <b>Активные стажёры:</b>\n\nНет стажеров на задании."
        
    text = "👨‍💻 <b>Активные стажёры (нажмите для просмотра):</b>\n\n"
    for intern in interns:
        username = f"@{intern.username}" if intern.username else f"ID {intern.id}"
        task_info = " (Нет активной задачи)"
        if intern.internship_tasks:
            active_task = next((t for t in intern.internship_tasks if t.status == 'active'), None)
            if active_task:
                task_info = f" - {active_task.platform} ({active_task.current_progress}/{active_task.goal_count})"

        text += f"• /view_intern_{intern.id} ({username}){task_info}\n"
        
    text += f"\nСтраница {page}/{total_pages}"
    return text

def format_single_intern(intern: User) -> str:
    """Форматирует детальную информацию по одному стажеру."""
    active_task = next((t for t in intern.internship_tasks if t.status == 'active'), None)

    text = (
        f"<b>Карточка стажера @{intern.username}</b> (ID: <code>{intern.id}</code>)\n\n"
    )

    if not active_task:
        text += "<i>Нет активного задания.</i>"
        return text

    salary = active_task.estimated_salary or 0.0
    penalty_per_error = (salary / active_task.goal_count) * 2 if active_task.goal_count > 0 else 0
    total_penalty = active_task.error_count * penalty_per_error
    final_salary = salary - total_penalty

    text += (
        "<b>Активное задание:</b>\n"
        f" • Платформа: <code>{active_task.platform}</code>\n"
        f" • Тип: <code>{active_task.task_type}</code>\n"
        f" • Прогресс: <b>{active_task.current_progress} / {active_task.goal_count}</b>\n"
        f" • Ошибок: <b>{active_task.error_count}</b>\n\n"
        "<b>Финансы:</b>\n"
        f" • Зарплата: {salary:.2f} ⭐\n"
        f" • Штрафы: -{total_penalty:.2f} ⭐\n"
        f" • <b>К выплате: {final_salary:.2f} ⭐</b>"
    )
    return text