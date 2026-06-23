import ssl
import logging
from typing import Optional

import aiohttp
import certifi

logger = logging.getLogger(__name__)


class BotoHubService:
    """Checks if a user has subscribed to all BotoHub sponsor channels."""

    ENDPOINT = "https://botohub.me/get-tasks"

    def __init__(self, token: str) -> None:
        self._token = token
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
        On any error returns {"tasks": [], "completed": False}.
        """
        if not self._token:
            logger.debug("BOTOHUB_TOKEN not set, skipping BotoHub check")
            return {"tasks": [], "completed": True}
        try:
            session = self._get_session()
            async with session.post(
                self.ENDPOINT,
                json={"chat_id": user_id},
                headers={"Auth": self._token, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    logger.warning("BotoHub returned status %s for user %s", resp.status, user_id)
                    return {"tasks": [], "completed": False}
                data = await resp.json(content_type=None)
                result = {
                    "tasks": data.get("tasks", []),
                    "completed": bool(data.get("completed", False)),
                }
                logger.debug("BotoHub response for %s: completed=%s tasks_count=%s", user_id, result["completed"], len(result["tasks"]))
                return result
        except Exception as e:
            logger.error("BotoHub check_tasks error for user %s: %s", user_id, e)
            return {"tasks": [], "completed": False}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class BotoHubViewsService:
    """Sends BotoHub advertising posts to users."""

    ENDPOINT = "https://views.botohub.me/ad/SendPost"

    _RESPONSE_CODES = {
        1: "success",
        2: "invalid/revoked token",
        3: "user blocked bot",
        4: "rate limit exceeded",
        7: "ad impression limit reached",
        8: "no advertisements available",
        9: "bot disabled in settings",
    }

    def __init__(self, token: str) -> None:
        self._token = token
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def send_ad(self, user_id: int, hi: bool = False) -> int:
        """
        Sends an ad. Returns response code (1=success).
        Never raises — all errors are swallowed.
        """
        if not self._token:
            return 0
        try:
            session = self._get_session()
            async with session.post(
                self.ENDPOINT,
                json={"SendToChatId": user_id, "hi": hi},
                headers={
                    "Authorization": self._token,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    logger.debug("BotoHub Views status %s for user %s", resp.status, user_id)
                    return 0
                data = await resp.json(content_type=None)
                code = data.get("SendPostResult", 0)
                desc = self._RESPONSE_CODES.get(code, f"unknown code {code}")
                if code == 1:
                    logger.debug("BotoHub Views ad sent to %s", user_id)
                else:
                    logger.debug("BotoHub Views: %s for user %s", desc, user_id)
                return code
        except Exception as e:
            logger.debug("BotoHub Views send_ad error for user %s: %s", user_id, e)
            return 0

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
