import asyncio
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot import config
from bot.database.db import Database
from bot.database.models import User
from bot.keyboards.inline import back_to_menu_keyboard
from bot.services.botohub import BotoHubViewsService
from bot.handlers.start import sponsor_gate, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


@router.callback_query(F.data == "top_refs")
async def cb_top_refs(
    callback: CallbackQuery,
    db: Database,
    user: User,
    botohub_views: BotoHubViewsService,
) -> None:
    if not user.sponsors_passed and callback.from_user.id not in config.ADMIN_IDS:
        await sponsor_gate(callback)
        return
    top = await db.get_top_referrers(limit=10)

    if not top:
        text = "🏅 <b>Таблица лидеров</b>\n\nПока нет участников с рефералами. Будь первым!"
    else:
        lines = ["🏅 <b>Таблица лидеров</b>\n"]
        for i, entry in enumerate(top, start=1):
            medal = MEDALS.get(i, f"{i}.")
            lines.append(
                f"{medal} {entry['name']} — <b>{entry['total_refs']}</b> чел. "
                f"· {entry['stars_balance']:.0f} ⭐"
            )
        text = "\n".join(lines)

    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))

    await safe_edit_text(callback, text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
