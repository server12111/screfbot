import asyncio
import logging
from typing import Optional, Union

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import config
from bot.database.db import Database
from bot.database.models import User, Sponsor
from bot.keyboards.inline import main_menu_keyboard, sponsors_check_keyboard
from bot.services.botohub import BotoHubService, BotoHubViewsService
from bot.services.tgrass import TgrassService

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "🔥 <b>Добро пожаловать в систему!</b>\n\n"
    "Зарабатывай баллы ⭐ за привлечение новых участников.\n\n"
    "Приводи → копи → выводи!\n\n"
    "📌 Выбери раздел:"
)


async def safe_edit_text(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
) -> None:
    """Edit message text. If message is a photo, deletes it and sends a new text message."""
    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


# ── Sponsor gate (used by all feature handlers) ──────────────────────────────────

async def sponsor_gate(callback: CallbackQuery) -> None:
    """Show a redirect screen when user hasn't passed sponsor check yet."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔓 Подписаться и разблокировать", callback_data="check_subscription"))
    await safe_edit_text(
        callback,
        "🔒 <b>Доступ закрыт</b>\n\n"
        "Для доступа к боту подпишись на наших партнёров.\n"
        "Это займёт меньше минуты!",
        reply_markup=builder.as_markup(),
    )
    await callback.answer("🔒 Сначала подпишитесь на партнёров!", show_alert=True)


# ── Sponsor check ────────────────────────────────────────────────────────────────

async def _check_all_sponsors(
    bot: Bot,
    user_id: int,
    db: Database,
    botohub: BotoHubService,
    tgrass: TgrassService,
) -> tuple[bool, dict, dict, list[Sponsor], set[int]]:
    botohub_result, tgrass_result, local_sponsors = await asyncio.gather(
        botohub.check_tasks(user_id),
        tgrass.check_tasks(user_id),
        db.get_all_sponsors(),
    )

    unsubscribed_local_ids: set[int] = set()
    for sponsor in local_sponsors:
        try:
            member = await bot.get_chat_member(sponsor.channel_id, user_id)
            if member.status in ("left", "kicked", "restricted"):
                unsubscribed_local_ids.add(sponsor.id)
        except Exception:
            unsubscribed_local_ids.add(sponsor.id)

    all_ok = (
        botohub_result.get("completed", False)
        and tgrass_result.get("completed", False)
        and len(unsubscribed_local_ids) == 0
    )
    return all_ok, botohub_result, tgrass_result, local_sponsors, unsubscribed_local_ids


def _count_unique_pending(
    botohub_tasks: list[str],
    tgrass_tasks: list[str],
    local_sponsors: list[Sponsor],
    unsubscribed_local_ids: set[int],
) -> int:
    seen: set[str] = set()
    count = 0
    for url in botohub_tasks:
        if url and url not in seen:
            seen.add(url)
            count += 1
    for url in tgrass_tasks:
        if url and url not in seen:
            seen.add(url)
            count += 1
    for sponsor in local_sponsors:
        if sponsor.id not in unsubscribed_local_ids:
            continue
        url = sponsor.url
        if url and url not in seen:
            seen.add(url)
            count += 1
        elif not url:
            count += 1
    return count


# ── Reward helpers ────────────────────────────────────────────────────────────────

async def _on_first_sponsor_screen(
    bot: Bot,
    db: Database,
    user: User,
    botohub_tasks: list[str],
    tgrass_tasks: list[str],
    local_sponsors: list[Sponsor],
    unsubscribed_local_ids: set[int],
) -> Optional[float]:
    if not user.referred_by:
        return None
    if await db.has_subscription_tracking(user.id):
        return None

    existing = await db.get_pending_referral(user.id)
    if existing:
        return await db.calculate_ref_reward(existing["sponsor_count"])

    total = _count_unique_pending(botohub_tasks, tgrass_tasks, local_sponsors, unsubscribed_local_ids)
    if total <= 0:
        return None

    await db.upsert_pending_referral(user.id, user.referred_by, total)
    reward = await db.calculate_ref_reward(total)

    referrer = await db.get_user_by_id(user.referred_by)
    if referrer:
        try:
            await bot.send_message(
                referrer.telegram_id,
                f"🔔 По вашей ссылке зарегистрировался новый участник!\n"
                f"Он выполняет условия доступа.\n\n"
                f"Вы получите <b>{reward:.1f} ⭐</b> после его подтверждения.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    return reward


async def _get_stored_reward(db: Database, user: User) -> Optional[float]:
    if not user.referred_by:
        return None
    existing = await db.get_pending_referral(user.id)
    if existing:
        return await db.calculate_ref_reward(existing["sponsor_count"])
    return None


async def _credit_both_and_notify(bot: Bot, db: Database, user: User) -> Optional[float]:
    if not user.referred_by:
        return None
    if await db.has_subscription_tracking(user.id):
        return None

    pending = await db.get_pending_referral(user.id)
    if not pending:
        return None

    reward = await db.calculate_ref_reward(pending["sponsor_count"])
    if reward <= 0:
        return None

    referrer = await db.get_user_by_id(user.referred_by)
    if not referrer:
        return None

    await db.add_stars(referrer.id, reward)
    await db.add_total_earned(referrer.id, reward)
    await db.increment_ref_count(referrer.id)
    await db.log_ref_event(referrer.id, user.id, reward)
    await db.add_stars(user.id, reward)
    await db.create_subscription_tracking(user.id, referrer.id, reward)
    await db.delete_pending_referral(user.id)

    try:
        await bot.send_message(
            referrer.telegram_id,
            f"🎯 Участник по вашей ссылке выполнил условие!\n"
            f"Вам начислено <b>{reward:.1f} ⭐</b>.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    return reward


# ── Main menu helper ─────────────────────────────────────────────────────────────

async def show_main_menu(
    target: Union[Message, CallbackQuery],
    db: Database,
    text: str = WELCOME_TEXT,
) -> None:
    kb = main_menu_keyboard()
    photo_id = await db.get_setting("menu_photo_file_id") or ""

    if isinstance(target, CallbackQuery):
        message = target.message
        try:
            if photo_id:
                if message.photo:
                    await message.edit_media(
                        InputMediaPhoto(media=photo_id, caption=text, parse_mode="HTML"),
                        reply_markup=kb,
                    )
                else:
                    await message.delete()
                    await message.answer_photo(photo_id, caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                if message.photo:
                    await message.delete()
                    await message.answer(text, reply_markup=kb, parse_mode="HTML")
                else:
                    await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            try:
                if photo_id:
                    await message.answer_photo(photo_id, caption=text, reply_markup=kb, parse_mode="HTML")
                else:
                    await message.answer(text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
    else:
        if photo_id:
            await target.answer_photo(photo_id, caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")


def _sponsor_screen_text(total: int, predicted_reward: Optional[float]) -> str:
    reward_line = (
        f"\n💡 <b>Тебе начислится {predicted_reward:.1f} ⭐</b> после подписки!\n"
        if predicted_reward
        else ""
    )
    return (
        f"🔒 <b>Доступ временно ограничен</b>\n\n"
        f"Подпишись на <b>{total}</b> канал(а) наших партнёров.\n"
        f"{reward_line}\n"
        "Нажми кнопки ниже, подпишись и нажми «Я подписался»:"
    )


# ── /start ───────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    db: Database,
    botohub: BotoHubService,
    tgrass: TgrassService,
    botohub_views: BotoHubViewsService,
    user: User,
    is_new_user: bool,
    bot: Bot,
) -> None:
    await state.clear()

    args = message.text.split(maxsplit=1)
    ref_arg = args[1].strip() if len(args) > 1 else ""
    if is_new_user and ref_arg.startswith("ref_"):
        ref_code = ref_arg[4:]
        if ref_code and ref_code != user.ref_code:
            referrer = await db.get_user_by_ref_code(ref_code)
            if referrer and referrer.telegram_id != message.from_user.id:
                await db.set_referred_by(user.id, referrer.id)
                user = await db.get_user(message.from_user.id) or user

    # Admin and already-passed users skip the sponsor check
    is_admin = message.from_user.id in config.ADMIN_IDS
    if user.sponsors_passed or is_admin:
        asyncio.create_task(botohub_views.send_ad(message.from_user.id, hi=is_new_user))
        await show_main_menu(message, db)
        return

    checking_msg = await message.answer("⏳ Проверяем...")

    all_ok, botohub_result, tgrass_result, local_sponsors, unsubscribed_ids = (
        await _check_all_sponsors(bot, message.from_user.id, db, botohub, tgrass)
    )

    try:
        await checking_msg.delete()
    except Exception:
        pass

    bh_tasks = botohub_result.get("tasks", [])
    tg_tasks = tgrass_result.get("tasks", [])
    total = _count_unique_pending(bh_tasks, tg_tasks, local_sponsors, unsubscribed_ids)

    if not all_ok and total == 0:
        all_ok = True

    if not all_ok:
        predicted_reward = await _on_first_sponsor_screen(
            bot, db, user, bh_tasks, tg_tasks, local_sponsors, unsubscribed_ids,
        )
        max_count = await db.get_max_sponsors()
        kb = sponsors_check_keyboard(bh_tasks, tg_tasks, local_sponsors, unsubscribed_ids, max_count)
        await message.answer(
            _sponsor_screen_text(total, predicted_reward),
            reply_markup=kb,
            parse_mode="HTML",
        )
        return

    await db.set_sponsors_passed(user.id)
    reward = await _credit_both_and_notify(bot, db, user)
    asyncio.create_task(botohub_views.send_ad(message.from_user.id, hi=is_new_user))

    if reward:
        await message.answer(
            f"✅ <b>Начислено {reward:.1f} ⭐</b> за подписку на партнёров!",
            parse_mode="HTML",
        )

    await show_main_menu(message, db)


# ── check_subscription ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(
    callback: CallbackQuery,
    db: Database,
    user: User,
    bot: Bot,
    botohub: BotoHubService,
    tgrass: TgrassService,
    botohub_views: BotoHubViewsService,
) -> None:
    await callback.answer("⏳ Проверяем...")
    await safe_edit_text(callback, "⏳ Проверяем...")

    all_ok, botohub_result, tgrass_result, local_sponsors, unsubscribed_ids = (
        await _check_all_sponsors(bot, callback.from_user.id, db, botohub, tgrass)
    )

    bh_tasks = botohub_result.get("tasks", [])
    tg_tasks = tgrass_result.get("tasks", [])
    total = _count_unique_pending(bh_tasks, tg_tasks, local_sponsors, unsubscribed_ids)

    if not all_ok and total == 0:
        all_ok = True

    if not all_ok:
        await _on_first_sponsor_screen(
            bot, db, user, bh_tasks, tg_tasks, local_sponsors, unsubscribed_ids,
        )
        predicted_reward = await _get_stored_reward(db, user)
        max_count = await db.get_max_sponsors()
        kb = sponsors_check_keyboard(bh_tasks, tg_tasks, local_sponsors, unsubscribed_ids, max_count)
        await safe_edit_text(
            callback,
            _sponsor_screen_text(total, predicted_reward),
            reply_markup=kb,
        )
        return

    await db.set_sponsors_passed(user.id)
    reward = await _credit_both_and_notify(bot, db, user)
    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))

    if reward:
        try:
            await safe_edit_text(
                callback,
                f"✅ <b>Начислено {reward:.1f} ⭐</b> за подписку на партнёров!",
            )
        except Exception:
            pass
        await asyncio.sleep(1.5)

    await show_main_menu(callback, db)


# ── main_menu callback ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    botohub_views: BotoHubViewsService,
) -> None:
    await state.clear()
    asyncio.create_task(botohub_views.send_ad(callback.from_user.id, hi=False))
    await show_main_menu(callback, db)
    await callback.answer()
