# file: references/reference_manager.py

import datetime
from database import db_manager
from database.models import Link
import logging

logger = logging.getLogger(__name__)

active_assignments = {}

async def assign_reference_to_user(user_id: int, platform: str) -> Link | None:
    link = await db_manager.db_get_available_reference(platform)
    
    if not link:
        return None

    await db_manager.db_update_link_status(link.id, 'assigned', user_id=user_id)

    active_assignments[user_id] = link.id
    
    link.status = 'assigned'
    link.assigned_to_user_id = user_id
    link.assigned_at = datetime.datetime.utcnow()
    
    return link


async def release_reference_from_user(user_id: int, final_status: str):
    if user_id not in active_assignments:
        return

    link_id = active_assignments.pop(user_id)
    await db_manager.db_update_link_status(link_id, final_status, user_id=None)


async def get_user_active_link_id(user_id: int) -> int | None:
    return active_assignments.get(user_id)


async def get_link_status(link_id: int) -> str | None:
    link = await db_manager.db_get_link_by_id(link_id)
    return link.status if link else None
    
async def get_link_assigned_user(link_id: int) -> int | None:
    link = await db_manager.db_get_link_by_id(link_id)
    return link.assigned_to_user_id if link else None

# --- Функции для администраторов ---

async def add_reference(url: str, platform: str) -> bool:
    return await db_manager.db_add_reference(url, platform)


async def get_all_references(platform: str) -> list[Link]:
    return await db_manager.db_get_all_references(platform)


async def delete_reference(link_id: int) -> tuple[bool, int | None]:
    link = await db_manager.db_get_link_by_id(link_id)
    if not link:
        return False, None
        
    assigned_user_id = link.assigned_to_user_id
    
    if assigned_user_id and assigned_user_id in active_assignments:
        if active_assignments[assigned_user_id] == link_id:
            active_assignments.pop(assigned_user_id)
            
    await db_manager.db_delete_reference(link_id)
    return True, assigned_user_id

async def force_release_reference(link_id: int) -> tuple[bool, int | None]:
    """Принудительно возвращает ссылку в статус 'available'."""
    link = await db_manager.db_get_link_by_id(link_id)
    if not link or link.status != 'assigned':
        logger.warning(f"Admin tried to force-release link {link_id}, but its status was not 'assigned'.")
        return False, None
    
    assigned_user_id = link.assigned_to_user_id
    
    # Удаляем из кэша активных заданий, если есть
    if assigned_user_id and assigned_user_id in active_assignments:
        if active_assignments[assigned_user_id] == link_id:
            active_assignments.pop(assigned_user_id)
    
    # Обновляем статус в БД
    await db_manager.db_update_link_status(link.id, 'available', user_id=None)
    logger.info(f"Admin force-released link {link_id} from user {assigned_user_id}.")
    return True, assigned_user_id


async def has_available_references(platform: str) -> bool:
    link = await db_manager.db_get_available_reference(platform)
    return link is not None