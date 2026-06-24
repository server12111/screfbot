import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import config
from bot.database.db import Database
from bot.keyboards.inline import (
    admin_back_keyboard,
    admin_panel_keyboard,
    admin_photo_keyboard,
    admin_promos_list_keyboard,
    admin_sponsors_list_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    waiting_sponsor_id = State()
    waiting_reward_amount = State()
    waiting_bonus_amount = State()
    waiting_promo_code = State()
    waiting_promo_stars = State()
    waiting_promo_max_uses = State()
    waiting_del_promo_code = State()
    waiting_menu_photo = State()
    waiting_max_sponsors = State()
    waiting_broadcast_text = State()


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ── Admin entry points ──────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("⚙️ <b>Админ-панель</b>", reply_markup=admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Админ-панель</b>", reply_markup=admin_panel_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


# ── Sponsors ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_sponsor")
async def cb_admin_add_sponsor(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_sponsor_id)
    await callback.message.edit_text(
        "➕ <b>Добавить спонсора</b>\n\n"
        "Введите @username или числовой ID канала.\n"
        "Бот должен быть администратором в этом канале.",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_sponsor_id))
async def msg_admin_sponsor_id(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return

    if not message.text:
        await message.answer("❌ Отправьте текстовый @username или ID канала.", reply_markup=admin_back_keyboard())
        return
    raw = message.text.strip()
    try:
        if raw.lstrip("-").isdigit():
            chat = await bot.get_chat(int(raw))
        else:
            username = raw if raw.startswith("@") else f"@{raw}"
            chat = await bot.get_chat(username)
    except Exception as e:
        logger.warning("Admin add sponsor failed for input %r: %s", raw, e)
        await message.answer(
            "❌ Не удалось найти канал. Проверьте username/ID и убедитесь, что бот является администратором.",
            reply_markup=admin_back_keyboard(),
        )
        return

    channel_username = f"@{chat.username}" if chat.username else None
    await db.add_sponsor(chat.id, channel_username, chat.title or str(chat.id))
    await state.clear()
    await message.answer(
        f"✅ Спонсор добавлен: <b>{chat.title}</b> (<code>{chat.id}</code>)",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_list_sponsors")
async def cb_admin_list_sponsors(callback: CallbackQuery, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    sponsors = await db.get_all_sponsors()
    if not sponsors:
        await callback.message.edit_text(
            "📋 <b>Список спонсоров</b>\n\nСпонсоры не добавлены.",
            reply_markup=admin_back_keyboard(),
            parse_mode="HTML",
        )
    else:
        text = "📋 <b>Список спонсоров</b>\n\nНажмите на канал, чтобы удалить его:"
        await callback.message.edit_text(
            text, reply_markup=admin_sponsors_list_keyboard(sponsors), parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "admin_del_sponsor")
async def cb_admin_del_sponsor_prompt(callback: CallbackQuery, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    sponsors = await db.get_all_sponsors()
    if not sponsors:
        await callback.answer("Нет спонсоров для удаления.", show_alert=True)
        return
    await callback.message.edit_text(
        "❌ <b>Удалить спонсора</b>\n\nВыберите канал:",
        reply_markup=admin_sponsors_list_keyboard(sponsors),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_del_sponsor:"))
async def cb_admin_del_sponsor_confirm(callback: CallbackQuery, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        sponsor_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных.", show_alert=True)
        return
    await db.delete_sponsor(sponsor_id)

    sponsors = await db.get_all_sponsors()
    if sponsors:
        await callback.message.edit_text(
            "✅ Спонсор удалён.\n\n📋 <b>Оставшиеся спонсоры:</b>",
            reply_markup=admin_sponsors_list_keyboard(sponsors),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "✅ Спонсор удалён. Список спонсоров пуст.",
            reply_markup=admin_panel_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer("Удалено")


# ── Reward ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_set_reward")
async def cb_admin_set_reward(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    current = await db.get_ref_reward()
    await state.set_state(AdminStates.waiting_reward_amount)
    await callback.message.edit_text(
        f"⭐ <b>Изменить награду за реферала</b>\n\n"
        f"Текущая награда: <b>{current:.0f} ⭐ за участника</b>\n\n"
        "Введите новое значение (целое число, например: 5):",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_reward_amount))
async def msg_admin_reward(message: Message, state: FSMContext, db: Database) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        value = float(message.text.strip().replace(",", "."))
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
    await db.set_setting("ref_reward", str(value))
    await state.clear()
    await message.answer(
        f"✅ Награда за реферала изменена: <b>{value:.0f} ⭐ за участника</b>",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


# ── Bonus ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_set_bonus")
async def cb_admin_set_bonus(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    current = await db.get_bonus_amount()
    await state.set_state(AdminStates.waiting_bonus_amount)
    await callback.message.edit_text(
        f"🎁 <b>Изменить ежедневный бонус</b>\n\n"
        f"Текущий бонус: <b>{current:.0f} ⭐</b>\n\n"
        "Введите новое значение (число):",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_bonus_amount))
async def msg_admin_bonus(message: Message, state: FSMContext, db: Database) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        value = float(message.text.strip().replace(",", "."))
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
    await db.set_setting("bonus_amount", str(value))
    await state.clear()
    await message.answer(
        f"✅ Ежедневный бонус изменён: <b>{value:.0f} ⭐</b>",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


# ── Promo codes ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_create_promo")
async def cb_admin_create_promo(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_promo_code)
    await callback.message.edit_text(
        "➕ <b>Создать промокод</b>\n\n"
        "Шаг 1/3: Введите текст промокода (только буквы и цифры):",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_promo_code))
async def msg_admin_promo_code(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    code = message.text.strip().upper()
    if not code.replace("_", "").replace("-", "").isalnum() or len(code) < 3:
        await message.answer("❌ Код должен содержать минимум 3 символа (буквы/цифры).")
        return
    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.waiting_promo_stars)
    await message.answer(
        f"✅ Код: <code>{code}</code>\n\n"
        "Шаг 2/3: Введите количество звёзд за этот промокод:",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.waiting_promo_stars))
async def msg_admin_promo_stars(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        stars = float(message.text.strip().replace(",", "."))
        if stars <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
    await state.update_data(promo_stars=stars)
    await state.set_state(AdminStates.waiting_promo_max_uses)
    data = await state.get_data()
    await message.answer(
        f"✅ Код: <code>{data['promo_code']}</code> | Звёзд: <b>{stars:.0f} ⭐</b>\n\n"
        "Шаг 3/3: Введите максимальное количество использований:",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.waiting_promo_max_uses))
async def msg_admin_promo_max_uses(message: Message, state: FSMContext, db: Database) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        max_uses = int(message.text.strip())
        if max_uses <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return

    data = await state.get_data()
    code: str = data["promo_code"]
    stars: float = data["promo_stars"]

    existing = await db.get_promocode(code)
    if existing:
        await message.answer(
            f"❌ Промокод <code>{code}</code> уже существует.",
            reply_markup=admin_panel_keyboard(),
            parse_mode="HTML",
        )
        await state.clear()
        return

    await db.create_promocode(code, stars, max_uses)
    await state.clear()
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎟 Код: <code>{code}</code>\n"
        f"💰 Звёзд: <b>{stars:.0f} ⭐</b>\n"
        f"🔢 Использований: <b>{max_uses}</b>",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_list_promos")
async def cb_admin_list_promos(callback: CallbackQuery, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    promos = await db.get_all_promocodes()
    if not promos:
        await callback.message.edit_text(
            "📋 <b>Промокоды</b>\n\nПромокоды не созданы.",
            reply_markup=admin_back_keyboard(),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "📋 <b>Список промокодов</b>\n\nНажмите для удаления:",
            reply_markup=admin_promos_list_keyboard(promos),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "admin_del_promo")
async def cb_admin_del_promo_prompt(callback: CallbackQuery, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    promos = await db.get_all_promocodes()
    if not promos:
        await callback.answer("Нет промокодов для удаления.", show_alert=True)
        return
    await callback.message.edit_text(
        "❌ <b>Удалить промокод</b>\n\nВыберите промокод:",
        reply_markup=admin_promos_list_keyboard(promos),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_del_promo:"))
async def cb_admin_del_promo_confirm(callback: CallbackQuery, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        promo_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных.", show_alert=True)
        return
    await db.delete_promocode(promo_id)

    promos = await db.get_all_promocodes()
    if promos:
        await callback.message.edit_text(
            "✅ Промокод удалён.\n\n📋 <b>Оставшиеся промокоды:</b>",
            reply_markup=admin_promos_list_keyboard(promos),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "✅ Промокод удалён. Список промокодов пуст.",
            reply_markup=admin_panel_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer("Удалено")


# ── Menu photo ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_menu_photo")
async def cb_admin_menu_photo(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    photo_id = await db.get_setting("menu_photo_file_id") or ""
    has_photo = bool(photo_id)
    text = (
        "🖼 <b>Фото главного меню</b>\n\n"
        + ("✅ Фото установлено.\n\n" if has_photo else "❌ Фото не установлено.\n\n")
        + "Отправьте новое фото, чтобы установить его в главное меню."
    )
    await state.set_state(AdminStates.waiting_menu_photo)
    await callback.message.edit_text(text, reply_markup=admin_photo_keyboard(has_photo), parse_mode="HTML")
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_menu_photo), F.photo)
async def msg_admin_menu_photo(message: Message, state: FSMContext, db: Database) -> None:
    if not _is_admin(message.from_user.id):
        return
    file_id = message.photo[-1].file_id
    await db.set_setting("menu_photo_file_id", file_id)
    await state.clear()
    await message.answer("✅ Фото главного меню обновлено!", reply_markup=admin_panel_keyboard())


@router.message(StateFilter(AdminStates.waiting_menu_photo))
async def msg_admin_menu_photo_wrong(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer("❌ Пожалуйста, отправьте фото (изображение).")


@router.callback_query(F.data == "admin_set_max_sponsors")
async def cb_admin_set_max_sponsors(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    current = await db.get_max_sponsors()
    current_str = str(current) if current > 0 else "не ограничено"
    await state.set_state(AdminStates.waiting_max_sponsors)
    await callback.message.edit_text(
        f"🔢 <b>Максимальное количество спонсоров</b>\n\n"
        f"Текущее значение: <b>{current_str}</b>\n\n"
        "Введите максимальное количество кнопок спонсоров, которое будет показано пользователям.\n"
        "Введите <b>0</b> для отключения ограничения.",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_max_sponsors))
async def msg_admin_max_sponsors(message: Message, state: FSMContext, db: Database) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        value = int(message.text.strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число ≥ 0 (0 = без ограничений).")
        return
    await db.set_setting("max_sponsors", str(value))
    await state.clear()
    label = str(value) if value > 0 else "без ограничений"
    await message.answer(
        f"✅ Максимум спонсоров: <b>{label}</b>",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.message.edit_text(
        "📣 <b>Рассылка</b>\n\n"
        "Отправьте текст сообщения для рассылки всем пользователям.\n"
        "Поддерживается HTML-форматирование.",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_broadcast_text))
async def msg_broadcast_text(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение.", reply_markup=admin_back_keyboard())
        return

    text = message.text
    await state.clear()

    user_ids = await db.get_all_telegram_ids()
    total = len(user_ids)
    sent = 0
    failed = 0

    status_msg = await message.answer(f"⏳ Рассылка начата... Пользователей: {total}")

    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    try:
        await status_msg.edit_text(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"📤 Отправлено: <b>{sent}</b>\n"
            f"❌ Не доставлено: <b>{failed}</b>",
            reply_markup=admin_panel_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(
            f"✅ <b>Рассылка завершена</b>\n\nОтправлено: {sent} / Не доставлено: {failed}",
            reply_markup=admin_panel_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "admin_clear_photo")
async def cb_admin_clear_photo(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await db.set_setting("menu_photo_file_id", "")
    await state.clear()
    await callback.message.edit_text(
        "✅ Фото главного меню удалено.", reply_markup=admin_panel_keyboard(), parse_mode="HTML"
    )
    await callback.answer()
