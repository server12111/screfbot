import asyncio
import logging
from datetime import datetime, timedelta

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


@router.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(
    callback: CallbackQuery,
    db: Database,
    user: User,
    botohub_views: BotoHubViewsService,
) -> None:
    if not user.sponsors_passed and callback.from_user.id not in config.ADMIN_IDS:
        await sponsor_gate(callback)
        return

    fresh_user = await db.get_user(callback.from_user.id)
    if not fresh_user:
        await callback.answer()
        return

    now = datetime.utcnow()

    if fresh_user.last_bonus_at:
        next_bonus_at = fresh_user.last_bonus_at + timedelta(hours=24)
        if now < next_bonus_at:
            remaining = next_bonus_at - now
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            await callback.answer(
                f"⏳ Следующий бонус через {hours}ч {minutes}мин",
                show_alert=True,
            )
            return

    bonus_amount = await db.get_bonus_amount()
    await db.add_stars(fresh_user.id, bonus_amount)
    await db.update_last_bonus(fresh_user.id, now)

    updated_user = await db.get_user(callback.from_user.id)
    balance = updated_user.stars_balance if updated_user else fresh_user.stars_balance + bonus_amount

    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))

    await safe_edit_text(
        callback,
        f"🎁 <b>Ежедневный бонус получен!</b>\n\n"
        f"<b>+{bonus_amount:.0f} ⭐</b> начислено на баланс.\n\n"
        f"💼 Текущий баланс: <b>{balance:.1f} ⭐</b>\n\n"
        "Возвращайтесь завтра за новым бонусом!",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer("✅ Бонус получен!")
