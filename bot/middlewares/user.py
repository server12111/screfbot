import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.database.db import Database

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db: Database = data.get("db")
        if not db:
            return await handler(event, data)

        from_user = None
        if isinstance(event, Message):
            from_user = event.from_user
        elif isinstance(event, CallbackQuery):
            from_user = event.from_user

        if not from_user:
            return await handler(event, data)

        user, is_new = await db.get_or_create_user(
            telegram_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name,
        )

        if user.is_banned:
            if isinstance(event, Message):
                await event.answer("🚫 Вы заблокированы в этом боте.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Вы заблокированы.", show_alert=True)
            return

        data["user"] = user
        data["is_new_user"] = is_new

        return await handler(event, data)
