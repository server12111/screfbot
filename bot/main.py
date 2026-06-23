import asyncio
import logging
import os
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot import config
from bot.database.db import Database
from bot.handlers import setup_routers
from bot.middlewares.user import UserMiddleware
from bot.services.botohub import BotoHubService, BotoHubViewsService
from bot.services.tgrass import TgrassService

logger = logging.getLogger(__name__)

SUBSCRIPTION_CHECK_INTERVAL = 7200  # 2 hours


async def subscription_check_loop(
    bot: Bot,
    db: Database,
    botohub: BotoHubService,
    tgrass: TgrassService,
) -> None:
    """Background task: every 2h checks if referred users are still subscribed to sponsors.
    If not — revokes the referrer's reward."""
    await asyncio.sleep(60)  # initial delay
    while True:
        try:
            records = await db.get_active_tracking_records()
            logger.info("Subscription check: %d active records", len(records))
            for record in records:
                try:
                    botohub_result = await botohub.check_tasks(record["referred_telegram_id"])
                    tgrass_result = await tgrass.check_tasks(record["referred_telegram_id"])

                    # Only revoke when API explicitly returned pending tasks.
                    # Empty tasks + completed=False means a network/API error — skip revocation.
                    bh_ok = botohub_result.get("completed", True) or not botohub_result.get("tasks")
                    tg_ok = tgrass_result.get("completed", True) or not tgrass_result.get("tasks")
                    still_ok = bh_ok and tg_ok

                    await db.update_tracking_last_checked(record["id"])

                    if not still_ok:
                        reward = record["reward_amount"]
                        referrer_id = record["referrer_db_id"]
                        referrer_tg = record["referrer_telegram_id"]

                        await db.deduct_stars(referrer_id, reward)
                        await db.revoke_tracking_reward(record["id"])

                        try:
                            await bot.send_message(
                                referrer_tg,
                                f"⚠️ Один из ваших рефералов отписался от спонсоров.\n"
                                f"<b>-{reward:.1f} ⭐</b> списано с баланса.",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                        logger.info(
                            "Revoked %.1f stars from referrer %s (referred user %s unsubscribed)",
                            reward, referrer_tg, record["referred_telegram_id"]
                        )

                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error("Error checking record id=%s: %s", record["id"], e)

        except Exception as e:
            logger.error("Subscription check loop error: %s", e)

        await asyncio.sleep(SUBSCRIPTION_CHECK_INTERVAL)


async def main() -> None:
    config.validate()
    os.makedirs(os.path.dirname(config.DATABASE_PATH) or "data", exist_ok=True)

    db = Database(config.DATABASE_PATH)
    await db.connect()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    botohub = BotoHubService(config.BOTOHUB_TOKEN)
    botohub_views = BotoHubViewsService(config.BOTOHUB_VIEWS_TOKEN)
    tgrass = TgrassService(config.TGRASS_TOKEN, config.TGRASS_ENDPOINT)

    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(setup_routers())

    dp["db"] = db
    dp["botohub"] = botohub
    dp["botohub_views"] = botohub_views
    dp["tgrass"] = tgrass

    @dp.errors()
    async def global_error_handler(event: ErrorEvent) -> bool:
        logger.error("Unhandled error: %s", event.exception, exc_info=event.exception)
        return True

    # Background subscription revocation task
    asyncio.create_task(subscription_check_loop(bot, db, botohub, tgrass))

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await botohub.close()
        await botohub_views.close()
        await tgrass.close()
        await db.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _restart_delay = 5
    while True:
        try:
            asyncio.run(main())
            break
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
            break
        except Exception as e:
            logging.error("Bot crashed: %s. Restarting in %ds...", e, _restart_delay, exc_info=True)
            time.sleep(_restart_delay)
            _restart_delay = min(_restart_delay * 2, 60)
