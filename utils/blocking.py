# file: utils/blocking.py

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from states.user_states import UserState
from config import ADMIN_IDS # Импортируем список ID администраторов

# Команды, которые считаются "прерывающими", так как они начинают новый сценарий
INTERRUPTING_COMMANDS = {"/start", "Профиль", "Заработок", "Поддержка", "Статистика"}

class BlockingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        state = data.get("state")
        user = data.get("event_from_user")

        if not state or not user:
            return await handler(event, data)
            
        # ИЗМЕНЕНО: Если ID пользователя есть в списке админов, немедленно пропускаем его.
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        # Эта логика теперь применяется только к обычным пользователям
        current_state = await state.get_state()
        
        if current_state and current_state != UserState.MAIN_MENU:
            is_interrupting = False
            
            if isinstance(event, Message) and event.text in INTERRUPTING_COMMANDS:
                is_interrupting = True
            
            if is_interrupting:
                text = "Пожалуйста, завершите или отмените текущее действие, прежде чем начинать новое."
                if isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer(text)
                return

        return await handler(event, data)