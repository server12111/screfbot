import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import config
from bot.database.db import Database
from bot.database.models import User
from bot.keyboards.inline import (
    back_to_menu_keyboard,
    cancel_keyboard,
    withdraw_amount_keyboard,
)
from bot.services.botohub import BotoHubViewsService
from bot.handlers.start import sponsor_gate, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()


class WithdrawStates(StatesGroup):
    waiting_wallet = State()


@router.callback_query(F.data == "withdraw_stars")
async def cb_withdraw_stars(
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

    min_withdraw = await db.get_min_withdraw()
    if fresh_user.stars_balance < min_withdraw:
        await safe_edit_text(
            callback,
            f"⚠️ <b>Недостаточно баллов</b>\n\n"
            f"Минимум для вывода: <b>{min_withdraw:.0f} ⭐</b>\n"
            f"Твой баланс: <b>{fresh_user.stars_balance:.1f} ⭐</b>\n\n"
            "Приглашай участников и накапливай баллы!",
            reply_markup=back_to_menu_keyboard(),
        )
        await callback.answer()
        return

    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))

    await safe_edit_text(
        callback,
        f"💳 <b>Вывод баллов</b>\n\n"
        f"⚡ Баланс: <b>{fresh_user.stars_balance:.1f} ⭐</b>\n"
        f"Минимум: <b>{min_withdraw:.0f} ⭐</b>\n\n"
        "Выбери сумму:",
        reply_markup=withdraw_amount_keyboard(fresh_user.stars_balance, min_withdraw),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("withdraw_amount:"))
async def cb_withdraw_amount(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    try:
        amount = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных. Попробуйте снова.", show_alert=True)
        return
    fresh_user = await db.get_user(callback.from_user.id)
    if not fresh_user:
        await callback.answer()
        return

    min_withdraw = await db.get_min_withdraw()
    if amount < min_withdraw:
        await callback.answer(f"Минимальная сумма: {min_withdraw:.0f} ⭐", show_alert=True)
        return

    if fresh_user.stars_balance < amount:
        await callback.answer(
            f"Недостаточно звёзд. Ваш баланс: {fresh_user.stars_balance:.1f} ⭐",
            show_alert=True,
        )
        return

    await state.set_state(WithdrawStates.waiting_wallet)
    await state.update_data(amount=amount)

    await safe_edit_text(
        callback,
        f"💳 <b>Вывод {amount} ⭐</b>\n\n"
        "Укажи свой Telegram username для выплаты\n"
        "(например: @username):",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(WithdrawStates.waiting_wallet))
async def msg_withdraw_wallet(
    message: Message,
    state: FSMContext,
    db: Database,
    bot: Bot,
) -> None:
    if not message.text:
        await message.answer("❌ Введите ваш Telegram username.")
        return
    username = message.text.strip().lstrip("@")
    if len(username) < 4:
        await message.answer("❌ Слишком короткий username. Попробуйте снова.")
        return
    wallet = f"@{username}"

    data = await state.get_data()
    amount: float = data.get("amount", 0)

    fresh_user = await db.get_user(message.from_user.id)
    if not fresh_user or fresh_user.stars_balance < amount:
        await message.answer("❌ Недостаточно звёзд. Возможно, баланс изменился.")
        await state.clear()
        return

    await db.deduct_stars(fresh_user.id, amount)
    req_id = await db.create_withdrawal_request(fresh_user.id, amount, wallet)

    withdrawal_text = (
        f"📌 <b>Запрос на вывод средств #{req_id}</b>\n\n"
        f"👤 Пользователь: {fresh_user.display_name} | ID <code>{fresh_user.telegram_id}</code>\n"
        f"💫 Сумма: <b>{amount:.0f} ⭐</b>\n"
        f"📲 Username: <code>{wallet}</code>"
    )

    sent = False
    if config.WITHDRAWAL_CHANNEL_ID:
        try:
            await bot.send_message(config.WITHDRAWAL_CHANNEL_ID, withdrawal_text, parse_mode="HTML")
            sent = True
        except Exception as e:
            logger.error("Failed to send withdrawal to channel: %s", e)

    if not sent and config.WITHDRAWAL_CHANNEL_ID:
        await db.add_stars(fresh_user.id, amount)
        await message.answer(
            "❌ Ошибка отправки заявки. Попробуйте позже.",
            reply_markup=back_to_menu_keyboard(),
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ <b>Заявка #{req_id} создана!</b>\n\n"
        f"💰 Сумма: <b>{amount:.0f} ⭐</b>\n"
        f"📲 Username: <code>{wallet}</code>\n\n"
        "Ожидай выплату от администратора.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    from bot.handlers.start import show_main_menu
    await show_main_menu(callback, db)
    await callback.answer()
