import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from bot import config
from bot.database.db import Database
from bot.database.models import User
from bot.keyboards.inline import back_to_menu_keyboard
from bot.services.botohub import BotoHubViewsService
from bot.handlers.start import sponsor_gate, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

_bot_username_cache: str = ""


async def _get_bot_username(bot: Bot) -> str:
    global _bot_username_cache
    if not _bot_username_cache:
        me = await bot.get_me()
        _bot_username_cache = me.username or ""
    return _bot_username_cache


@router.callback_query(F.data == "earn_stars")
async def cb_earn_stars(
    callback: CallbackQuery,
    db: Database,
    user: User,
    bot: Bot,
    botohub_views: BotoHubViewsService,
) -> None:
    if not user.sponsors_passed and callback.from_user.id not in config.ADMIN_IDS:
        await sponsor_gate(callback)
        return
    bot_username = await _get_bot_username(bot)
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.ref_code}"
    ref_count = await db.get_referral_count(user.id)

    text = (
        "🚀 <b>Реферальная программа</b>\n\n"
        f"Твоя ссылка для приглашения:\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 Вознаграждение: <b>от 1 до 5 ⭐ за участника</b>\n"
        f"👤 Приглашено: <b>{ref_count}</b>\n"
        f"💎 Всего получено: <b>{user.total_earned:.1f} ⭐</b>\n"
        f"⚡ Баланс: <b>{user.stars_balance:.1f} ⭐</b>\n\n"
        "Поделись ссылкой — и зарабатывай!"
    )

    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))

    await safe_edit_text(callback, text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
