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


@router.callback_query(F.data == "my_profile")
async def cb_my_profile(
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

    ref_count = await db.get_referral_count(fresh_user.id)
    join_date = fresh_user.created_at.strftime("%d.%m.%Y")

    username_line = f"@{fresh_user.username}" if fresh_user.username else "—"

    text = (
        "📊 <b>Личный кабинет</b>\n\n"
        f"🔹 ID: <code>{fresh_user.telegram_id}</code>\n"
        f"🔹 Имя: {fresh_user.first_name or '—'}\n"
        f"🔹 Ник: {username_line}\n\n"
        f"⚡ Баланс: <b>{fresh_user.stars_balance:.1f} ⭐</b>\n"
        f"🚀 Приглашено: <b>{ref_count}</b>\n"
        f"💎 Заработано всего: <b>{fresh_user.total_earned:.1f} ⭐</b>\n\n"
        f"📅 Регистрация: {join_date}"
    )

    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))

    await safe_edit_text(callback, text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
