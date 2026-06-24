from typing import Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Sponsor, Promocode, Task


def _btn(text: str, callback_data: Optional[str] = None, url: Optional[str] = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=callback_data or "noop")


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("🚀 Пригласить друга", callback_data="earn_stars"),
        _btn("💳 Вывод", callback_data="withdraw_stars"),
    )
    builder.row(
        _btn("📊 Кабинет", callback_data="my_profile"),
        _btn("⚡ Бонус", callback_data="daily_bonus"),
    )
    builder.row(
        _btn("🔑 Промокод", callback_data="enter_promo"),
        _btn("🏅 Рейтинг", callback_data="top_refs"),
    )
    builder.row(_btn("📋 Задания", callback_data="tasks_list"))
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🏠 На главную", callback_data="main_menu"))
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("↩️ Отмена", callback_data="cancel"))
    return builder.as_markup()


def withdraw_amount_keyboard(balance: float, min_withdraw: float = 15) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    amounts = [a for a in [15, 25, 50, 100] if a >= min_withdraw and a <= balance]
    if amounts:
        buttons = [_btn(f"{a} ⭐", callback_data=f"withdraw_amount:{a}") for a in amounts]
        builder.row(*buttons)
    builder.row(_btn("💸 Канал выплат", url="https://t.me/Monk3yStars"))
    builder.row(_btn("🏠 На главную", callback_data="main_menu"))
    return builder.as_markup()


def tasks_keyboard(tasks: list[Task], completed_ids: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        if task.url:
            builder.row(_btn(f"🔗 {task.title}", url=task.url))
        if task.id in completed_ids:
            builder.row(_btn(f"✅ Получено ({task.stars_amount:.0f} ⭐)", callback_data="noop"))
        else:
            builder.row(_btn(f"💰 Получить {task.stars_amount:.0f} ⭐", callback_data=f"claim_task:{task.id}"))
    builder.row(_btn("🏠 На главную", callback_data="main_menu"))
    return builder.as_markup()


def sponsors_check_keyboard(
    botohub_tasks: list[str],
    tgrass_tasks: list[str],
    local_sponsors: list[Sponsor],
    unsubscribed_local_ids: set[int],
    max_count: int = 0,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    seen_urls: set[str] = set()
    all_urls: list[str] = []

    for url in botohub_tasks:
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_urls.append(url)

    for url in tgrass_tasks:
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_urls.append(url)

    for sponsor in local_sponsors:
        if sponsor.id not in unsubscribed_local_ids:
            continue
        url = sponsor.url
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_urls.append(url)

    if max_count > 0:
        all_urls = all_urls[:max_count]

    buttons = [
        InlineKeyboardButton(text=f"📢 Спонсор {i + 1}", url=url)
        for i, url in enumerate(all_urls)
    ]
    for i in range(0, len(buttons), 2):
        builder.row(*buttons[i:i + 2])

    builder.row(_btn("✔️ Я подписался", callback_data="check_subscription"))
    return builder.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("➕ Добавить спонсора", callback_data="admin_add_sponsor"))
    builder.row(_btn("📋 Список спонсоров", callback_data="admin_list_sponsors"))
    builder.row(_btn("❌ Удалить спонсора", callback_data="admin_del_sponsor"))
    builder.row(_btn("⭐ Изменить награду", callback_data="admin_set_reward"))
    builder.row(_btn("🎁 Изменить бонус", callback_data="admin_set_bonus"))
    builder.row(_btn("➕ Создать промокод", callback_data="admin_create_promo"))
    builder.row(_btn("📋 Список промокодов", callback_data="admin_list_promos"))
    builder.row(_btn("❌ Удалить промокод", callback_data="admin_del_promo"))
    builder.row(_btn("🖼 Фото меню", callback_data="admin_menu_photo"))
    builder.row(_btn("🔢 Макс. спонсоров", callback_data="admin_set_max_sponsors"))
    builder.row(_btn("📣 Рассылка", callback_data="admin_broadcast"))
    builder.row(_btn("📋 Управление заданиями", callback_data="admin_tasks"))
    return builder.as_markup()


def admin_tasks_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("➕ Добавить задание", callback_data="admin_add_task"))
    builder.row(_btn("📋 Список заданий", callback_data="admin_list_tasks"))
    builder.row(_btn("❌ Удалить задание", callback_data="admin_del_task"))
    builder.row(_btn("◀️ Назад", callback_data="admin_panel"))
    return builder.as_markup()


def admin_tasks_list_keyboard(tasks: list[Task]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in tasks:
        status = "✅" if t.is_active else "❌"
        builder.row(_btn(f"🗑 {status} {t.title} — {t.stars_amount:.0f}⭐", callback_data=f"admin_del_task:{t.id}"))
    builder.row(_btn("◀️ Назад", callback_data="admin_tasks"))
    return builder.as_markup()


def admin_sponsors_list_keyboard(sponsors: list[Sponsor]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sponsors:
        builder.row(_btn(f"🗑 {s.channel_title}", callback_data=f"admin_del_sponsor:{s.id}"))
    builder.row(_btn("◀️ Назад", callback_data="admin_panel"))
    return builder.as_markup()


def admin_promos_list_keyboard(promos: list[Promocode]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in promos:
        label = f"🗑 {p.code} — {p.stars_amount:.0f}⭐ [{p.uses_count}/{p.max_uses}]"
        builder.row(_btn(label, callback_data=f"admin_del_promo:{p.id}"))
    builder.row(_btn("◀️ Назад", callback_data="admin_panel"))
    return builder.as_markup()


def admin_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("◀️ Назад", callback_data="admin_panel"))
    return builder.as_markup()


def admin_photo_keyboard(has_photo: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_photo:
        builder.row(_btn("🗑 Удалить фото", callback_data="admin_clear_photo"))
    builder.row(_btn("◀️ Назад", callback_data="admin_panel"))
    return builder.as_markup()
