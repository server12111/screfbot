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
