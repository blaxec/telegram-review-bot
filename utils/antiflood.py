from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
from cachetools import TTLCache

slow_mode_cache = TTLCache(maxsize=10_000, ttl=0.5)

class AntiFloodMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if event.from_user.id in slow_mode_cache:
            return
        
        slow_mode_cache[event.from_user.id] = None
        
        return await handler(event, data)