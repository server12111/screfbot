import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> list[int]:
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            result.append(int(part))
    return result


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: list[int] = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
WITHDRAWAL_CHANNEL_ID: int = int(os.getenv("WITHDRAWAL_CHANNEL_ID", "0"))
BOTOHUB_TOKEN: str = os.getenv("BOTOHUB_TOKEN", "")
BOTOHUB_VIEWS_TOKEN: str = os.getenv("BOTOHUB_VIEWS_TOKEN", "")
TGRASS_TOKEN: str = os.getenv("TGRASS_TOKEN", "")
TGRASS_ENDPOINT: str = os.getenv("TGRASS_ENDPOINT", "https://tgrass.space/offers")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bot.db")


def validate() -> None:
    import logging
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in .env")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS is not set in .env")
    if not WITHDRAWAL_CHANNEL_ID:
        logging.warning("WITHDRAWAL_CHANNEL_ID is not set — withdrawal requests won't be forwarded to a channel")
