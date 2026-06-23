import ssl
import logging
from typing import Optional

import aiohttp
import certifi

logger = logging.getLogger(__name__)


class TgrassService:
    DEFAULT_ENDPOINT = "https://tgrass.space/offers"

    def __init__(self, token: str, endpoint: str) -> None:
        self._token = token.strip()
        self._endpoint = endpoint.strip() or self.DEFAULT_ENDPOINT
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def check_tasks(self, user_id: int) -> dict:
        """
        Returns {"tasks": [url, ...], "completed": bool}.
        - completed=True  when status is "ok" or "no_offers"
        - completed=False when status is "not_ok"; tasks = unsubscribed offer links
        On any error: {"tasks": [], "completed": True} (bypass so users aren't blocked by API issues)
        """
        if not self._token:
            logger.debug("TGRASS_TOKEN not set, bypassing Tgrass check")
            return {"tasks": [], "completed": True}

        try:
            session = self._get_session()
            async with session.post(
                self._endpoint,
                json={"tg_user_id": user_id},
                headers={"Auth": self._token, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Tgrass returned status %s for user %s — bypassing", resp.status, user_id)
                    return {"tasks": [], "completed": True}

                data = await resp.json(content_type=None)
                status = data.get("status", "")
                offers = data.get("offers", [])

                if status in ("ok", "no_offers"):
                    result = {"tasks": [], "completed": True}
                else:
                    # status == "not_ok": return only unsubscribed offer links
                    pending_links = [
                        o["link"] for o in offers
                        if not o.get("subscribed", False) and o.get("link")
                    ]
                    result = {"tasks": pending_links, "completed": False}

                logger.debug(
                    "Tgrass response for %s: status=%s offers=%d pending=%d",
                    user_id, status, len(offers), len(result["tasks"]),
                )
                return result

        except Exception as e:
            logger.error("Tgrass check_tasks error for user %s: %s", user_id, e)
            return {"tasks": [], "completed": True}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
