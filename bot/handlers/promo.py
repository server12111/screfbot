import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import config
from bot.database.db import Database
from bot.database.models import User
from bot.keyboards.inline import back_to_menu_keyboard, cancel_keyboard
from bot.services.botohub import BotoHubViewsService
from bot.handlers.start import sponsor_gate, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()


class PromoStates(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == "enter_promo")
async def cb_enter_promo(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    if not user.sponsors_passed and callback.from_user.id not in config.ADMIN_IDS:
        await sponsor_gate(callback)
        return
    await state.set_state(PromoStates.waiting_code)
    await safe_edit_text(
        callback,
        "🔑 <b>Активация кода</b>\n\n"
        "Введи код для получения баллов:",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(PromoStates.waiting_code))
async def msg_promo_code(
    message: Message,
    state: FSMContext,
    db: Database,
    user: User,
    botohub_views: BotoHubViewsService,
) -> None:
    if not message.text:
        await message.answer("❌ Отправь текстовый код.", reply_markup=cancel_keyboard())
        return
    code = message.text.strip().upper()

    promo = await db.get_promocode(code)

    if not promo:
        await message.answer(
            "❌ Код не найден. Проверь и попробуй снова.",
            reply_markup=cancel_keyboard(),
        )
        return

    if not promo.is_active:
        await message.answer(
            "❌ Этот код деактивирован.",
            reply_markup=cancel_keyboard(),
        )
        return

    if promo.uses_count >= promo.max_uses:
        await message.answer(
            "❌ Лимит использований исчерпан.",
            reply_markup=cancel_keyboard(),
        )
        return

    if await db.has_user_used_promocode(promo.id, user.id):
        await message.answer(
            "❌ Ты уже активировал этот код.",
            reply_markup=cancel_keyboard(),
        )
        return

    await db.use_promocode(promo.id, user.id)
    await db.add_stars(user.id, promo.stars_amount)

    updated_user = await db.get_user(message.from_user.id)
    balance = updated_user.stars_balance if updated_user else user.stars_balance + promo.stars_amount

    asyncio.create_task(botohub_views.send_ad(message.from_user.id, hi=False))

    await state.clear()
    await message.answer(
        f"✅ <b>Код активирован!</b>\n\n"
        f"🔑 Код: <code>{promo.code}</code>\n"
        f"💰 Начислено: <b>+{promo.stars_amount:.0f} ⭐</b>\n\n"
        f"⚡ Баланс: <b>{balance:.1f} ⭐</b>",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
