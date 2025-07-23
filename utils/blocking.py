# file: utils/blocking.py

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from states.user_states import UserState

# Команды, которые считаются "прерывающими", так как они начинают новый сценарий
INTERRUPTING_COMMANDS = {"/start", "Профиль", "Заработок", "Поддержка"}

class BlockingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        state = data.get("state")
        if not state:
            return await handler(event, data)

        current_state = await state.get_state()
        
        # Блокируем только если пользователь находится в активном состоянии
        if current_state and current_state != UserState.MAIN_MENU:
            is_interrupting = False
            
            # Проверяем, является ли команда прерывающей
            if isinstance(event, Message) and event.text in INTERRUPTING_COMMANDS:
                is_interrupting = True
            
            # Если команда прерывающая, блокируем ее
            if is_interrupting:
                text = "Пожалуйста, завершите или отмените текущее действие, прежде чем начинать новое."
                if isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer(text)
                return  # Прерываем дальнейшую обработку

        # Если состояние неактивное или команда не является прерывающей, пропускаем дальше
        return await handler(event, data)