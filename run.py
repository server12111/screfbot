import asyncio
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_debug.log", encoding="utf-8"),
    ],
)

_restart_delay = 5
_MAX_RESTART_DELAY = 60

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
            break  # clean shutdown
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
            break
        except Exception as e:
            logging.error("Bot crashed: %s. Restarting in %ds...", e, _restart_delay, exc_info=True)
            time.sleep(_restart_delay)
            _restart_delay = min(_restart_delay * 2, _MAX_RESTART_DELAY)
