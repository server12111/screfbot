import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot import config
from bot.database.db import Database
from bot.database.models import User
from bot.keyboards.inline import tasks_keyboard, back_to_menu_keyboard
from bot.services.botohub import BotoHubViewsService
from bot.handlers.start import sponsor_gate, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "tasks_list")
async def cb_tasks_list(
    callback: CallbackQuery,
    db: Database,
    user: User,
    botohub_views: BotoHubViewsService,
) -> None:
    if not user.sponsors_passed and callback.from_user.id not in config.ADMIN_IDS:
        await sponsor_gate(callback)
        return

    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(user.id)

    if not tasks:
        await safe_edit_text(
            callback,
            "📋 <b>Задания</b>\n\nЗаданий пока нет. Загляни позже!",
            reply_markup=back_to_menu_keyboard(),
        )
        await callback.answer()
        return

    lines = ["📋 <b>Задания</b>\n"]
    for task in tasks:
        status = "✅" if task.id in completed_ids else "⬜"
        desc = f"\n   ↳ {task.description}" if task.description else ""
        lines.append(f"{status} <b>{task.title}</b> — {task.stars_amount:.0f} ⭐{desc}")

    text = "\n".join(lines)
    await safe_edit_text(callback, text, reply_markup=tasks_keyboard(tasks, completed_ids))
    await callback.answer()


@router.callback_query(F.data.startswith("claim_task:"))
async def cb_claim_task(
    callback: CallbackQuery,
    db: Database,
    user: User,
) -> None:
    try:
        task_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных.", show_alert=True)
        return

    if await db.has_user_completed_task(task_id, user.id):
        await callback.answer("✅ Ты уже выполнил это задание.", show_alert=True)
        return

    task = await db.get_task(task_id)
    if not task or not task.is_active:
        await callback.answer("❌ Задание недоступно.", show_alert=True)
        return

    await db.complete_task(task_id, user.id)
    await db.add_stars(user.id, task.stars_amount)

    await callback.answer(f"✅ +{task.stars_amount:.0f} ⭐ зачислено!", show_alert=True)

    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(user.id)

    lines = ["📋 <b>Задания</b>\n"]
    for t in tasks:
        status = "✅" if t.id in completed_ids else "⬜"
        desc = f"\n   ↳ {t.description}" if t.description else ""
        lines.append(f"{status} <b>{t.title}</b> — {t.stars_amount:.0f} ⭐{desc}")

    await safe_edit_text(callback, "\n".join(lines), reply_markup=tasks_keyboard(tasks, completed_ids))
