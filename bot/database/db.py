import secrets
import logging
from datetime import datetime
from typing import Optional

import aiosqlite

from bot.database.models import SCHEMA, User, Sponsor, Promocode, WithdrawalRequest

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "ref_reward": "0.3",
    "bonus_amount": "5",
    "min_withdraw": "15",
    "menu_photo_file_id": "",
    "max_sponsors": "0",
}


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _row_to_user(row: aiosqlite.Row) -> User:
    try:
        sponsors_passed = bool(row["sponsors_passed"])
    except (IndexError, KeyError):
        sponsors_passed = False
    return User(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        stars_balance=row["stars_balance"],
        ref_code=row["ref_code"],
        referred_by=row["referred_by"],
        total_refs=row["total_refs"],
        total_earned=row["total_earned"],
        last_bonus_at=_parse_dt(row["last_bonus_at"]),
        is_banned=bool(row["is_banned"]),
        sponsors_passed=sponsors_passed,
        created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
    )


def _row_to_sponsor(row: aiosqlite.Row) -> Sponsor:
    return Sponsor(
        id=row["id"],
        channel_id=row["channel_id"],
        channel_username=row["channel_username"],
        channel_title=row["channel_title"],
        invite_link=row["invite_link"],
        added_at=_parse_dt(row["added_at"]) or datetime.utcnow(),
    )


def _row_to_promo(row: aiosqlite.Row) -> Promocode:
    return Promocode(
        id=row["id"],
        code=row["code"],
        stars_amount=row["stars_amount"],
        max_uses=row["max_uses"],
        uses_count=row["uses_count"],
        is_active=bool(row["is_active"]),
        created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
    )


def _row_to_withdrawal(row: aiosqlite.Row) -> WithdrawalRequest:
    return WithdrawalRequest(
        id=row["id"],
        user_id=row["user_id"],
        amount=row["amount"],
        wallet=row["wallet"],
        status=row["status"],
        created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
    )


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._settings_cache: dict[str, str] = {}
        self._sponsors_cache: Optional[list[Sponsor]] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        for stmt in SCHEMA.split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._conn.execute(stmt)
        await self._conn.commit()
        # Migration: add sponsors_passed if missing (existing DBs)
        try:
            await self._conn.execute("ALTER TABLE users ADD COLUMN sponsors_passed INTEGER DEFAULT 0")
            await self._conn.commit()
        except Exception:
            pass
        for key, val in DEFAULT_SETTINGS.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val)
            )
        await self._conn.commit()
        logger.info("Database connected: %s", self._path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── Users ──────────────────────────────────────────────────────────────────

    async def get_or_create_user(
        self, telegram_id: int, username: Optional[str], first_name: Optional[str]
    ) -> tuple[User, bool]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()

        if row:
            user = _row_to_user(row)
            if user.username != username:
                await self._conn.execute(
                    "UPDATE users SET username = ? WHERE telegram_id = ?",
                    (username, telegram_id),
                )
                await self._conn.commit()
                user.username = username
            return user, False

        ref_code = secrets.token_urlsafe(6)
        await self._conn.execute(
            """INSERT INTO users (telegram_id, username, first_name, ref_code)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, username, first_name, ref_code),
        )
        await self._conn.commit()
        async with self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row), True

    async def get_user(self, telegram_id: int) -> Optional[User]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def get_user_by_ref_code(self, ref_code: str) -> Optional[User]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE ref_code = ?", (ref_code,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def get_user_by_id(self, db_id: int) -> Optional[User]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (db_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def set_referred_by(self, user_id: int, referrer_id: int) -> None:
        await self._conn.execute(
            "UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL",
            (referrer_id, user_id),
        )
        await self._conn.commit()

    async def add_stars(self, user_id: int, amount: float) -> None:
        await self._conn.execute(
            "UPDATE users SET stars_balance = stars_balance + ? WHERE id = ?",
            (amount, user_id),
        )
        await self._conn.commit()

    async def deduct_stars(self, user_id: int, amount: float) -> None:
        await self._conn.execute(
            "UPDATE users SET stars_balance = MAX(0, stars_balance - ?) WHERE id = ?",
            (amount, user_id),
        )
        await self._conn.commit()

    async def add_total_earned(self, user_id: int, amount: float) -> None:
        await self._conn.execute(
            "UPDATE users SET total_earned = total_earned + ? WHERE id = ?",
            (amount, user_id),
        )
        await self._conn.commit()

    async def increment_ref_count(self, user_id: int) -> None:
        await self._conn.execute(
            "UPDATE users SET total_refs = total_refs + 1 WHERE id = ?", (user_id,)
        )
        await self._conn.commit()

    async def update_last_bonus(self, user_id: int, dt: datetime) -> None:
        await self._conn.execute(
            "UPDATE users SET last_bonus_at = ? WHERE id = ?",
            (dt.strftime("%Y-%m-%d %H:%M:%S"), user_id),
        )
        await self._conn.commit()

    async def get_referral_count(self, user_id: int) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def get_top_referrers(self, limit: int = 10) -> list[dict]:
        async with self._conn.execute(
            """SELECT username, first_name, telegram_id, total_refs, stars_balance
               FROM users
               WHERE total_refs > 0
               ORDER BY total_refs DESC
               LIMIT ?""",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for row in rows:
            name = f"@{row['username']}" if row["username"] else (row["first_name"] or str(row["telegram_id"]))
            result.append(
                {
                    "name": name,
                    "total_refs": row["total_refs"],
                    "stars_balance": row["stars_balance"],
                }
            )
        return result

    async def set_sponsors_passed(self, user_id: int, passed: bool = True) -> None:
        await self._conn.execute(
            "UPDATE users SET sponsors_passed = ? WHERE id = ?",
            (int(passed), user_id),
        )
        await self._conn.commit()

    async def set_user_banned(self, telegram_id: int, is_banned: bool) -> None:
        await self._conn.execute(
            "UPDATE users SET is_banned = ? WHERE telegram_id = ?",
            (int(is_banned), telegram_id),
        )
        await self._conn.commit()

    async def get_all_telegram_ids(self) -> list[int]:
        async with self._conn.execute(
            "SELECT telegram_id FROM users WHERE is_banned = 0"
        ) as cur:
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    # ── Settings ────────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        if key in self._settings_cache:
            return self._settings_cache[key]
        async with self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        val = row["value"] if row else None
        if val is not None:
            self._settings_cache[key] = val
        return val

    async def set_setting(self, key: str, value: str) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await self._conn.commit()
        self._settings_cache[key] = value

    async def get_ref_reward(self) -> float:
        val = await self.get_setting("ref_reward")
        return float(val) if val else 10.0

    async def get_bonus_amount(self) -> float:
        val = await self.get_setting("bonus_amount")
        return float(val) if val else 5.0

    async def get_min_withdraw(self) -> float:
        val = await self.get_setting("min_withdraw")
        return float(val) if val else 15.0

    async def get_max_sponsors(self) -> int:
        val = await self.get_setting("max_sponsors")
        try:
            return max(0, int(val)) if val else 0
        except (ValueError, TypeError):
            return 0

    async def get_reward_per_sponsor(self) -> float:
        val = await self.get_setting("ref_reward")
        return float(val) if val else 0.3

    async def calculate_ref_reward(self, sponsor_count: int) -> float:
        """sponsors * per_sponsor_rate, capped [1, 5]. Returns 0 if no sponsors."""
        if sponsor_count <= 0:
            return 0.0
        per = await self.get_reward_per_sponsor()
        raw = sponsor_count * per
        return max(min(round(raw, 2), 5.0), 1.0)

    # ── Sponsors ────────────────────────────────────────────────────────────────

    async def get_all_sponsors(self) -> list[Sponsor]:
        if self._sponsors_cache is not None:
            return self._sponsors_cache
        async with self._conn.execute("SELECT * FROM sponsors ORDER BY added_at") as cur:
            rows = await cur.fetchall()
        self._sponsors_cache = [_row_to_sponsor(r) for r in rows]
        return self._sponsors_cache

    async def add_sponsor(
        self,
        channel_id: int,
        channel_username: Optional[str],
        channel_title: str,
        invite_link: Optional[str] = None,
    ) -> int:
        async with self._conn.execute(
            """INSERT OR IGNORE INTO sponsors (channel_id, channel_username, channel_title, invite_link)
               VALUES (?, ?, ?, ?)""",
            (channel_id, channel_username, channel_title, invite_link),
        ) as cur:
            last_id = cur.lastrowid
        await self._conn.commit()
        self._sponsors_cache = None
        return last_id or 0

    async def delete_sponsor(self, sponsor_id: int) -> None:
        await self._conn.execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
        await self._conn.commit()
        self._sponsors_cache = None

    async def get_sponsor_by_channel_id(self, channel_id: int) -> Optional[Sponsor]:
        async with self._conn.execute(
            "SELECT * FROM sponsors WHERE channel_id = ?", (channel_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_sponsor(row) if row else None

    # ── Promocodes ──────────────────────────────────────────────────────────────

    async def create_promocode(self, code: str, stars_amount: float, max_uses: int) -> int:
        async with self._conn.execute(
            "INSERT INTO promocodes (code, stars_amount, max_uses) VALUES (?, ?, ?)",
            (code.upper(), stars_amount, max_uses),
        ) as cur:
            last_id = cur.lastrowid
        await self._conn.commit()
        return last_id or 0

    async def get_promocode(self, code: str) -> Optional[Promocode]:
        async with self._conn.execute(
            "SELECT * FROM promocodes WHERE code = ?", (code.upper(),)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_promo(row) if row else None

    async def has_user_used_promocode(self, promocode_id: int, user_id: int) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM promocode_uses WHERE promocode_id = ? AND user_id = ?",
            (promocode_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return row is not None

    async def use_promocode(self, promocode_id: int, user_id: int) -> None:
        await self._conn.execute(
            "INSERT INTO promocode_uses (promocode_id, user_id) VALUES (?, ?)",
            (promocode_id, user_id),
        )
        await self._conn.execute(
            "UPDATE promocodes SET uses_count = uses_count + 1 WHERE id = ?",
            (promocode_id,),
        )
        await self._conn.commit()

    async def get_all_promocodes(self) -> list[Promocode]:
        async with self._conn.execute(
            "SELECT * FROM promocodes ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_promo(r) for r in rows]

    async def delete_promocode(self, promocode_id: int) -> None:
        await self._conn.execute("DELETE FROM promocodes WHERE id = ?", (promocode_id,))
        await self._conn.commit()

    # ── Withdrawals ─────────────────────────────────────────────────────────────

    async def create_withdrawal_request(
        self, user_id: int, amount: float, wallet: str
    ) -> int:
        async with self._conn.execute(
            "INSERT INTO withdrawal_requests (user_id, amount, wallet) VALUES (?, ?, ?)",
            (user_id, amount, wallet),
        ) as cur:
            last_id = cur.lastrowid
        await self._conn.commit()
        return last_id or 0

    async def get_withdrawal_requests(
        self, status: Optional[str] = None
    ) -> list[WithdrawalRequest]:
        if status:
            async with self._conn.execute(
                "SELECT * FROM withdrawal_requests WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self._conn.execute(
                "SELECT * FROM withdrawal_requests ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_withdrawal(r) for r in rows]

    # ── Ref events ──────────────────────────────────────────────────────────────

    async def log_ref_event(
        self, referrer_id: int, referred_id: int, amount: float
    ) -> None:
        await self._conn.execute(
            "INSERT INTO ref_events (referrer_id, referred_id, stars_amount) VALUES (?, ?, ?)",
            (referrer_id, referred_id, amount),
        )
        await self._conn.commit()

    # ── Pending referral (before first sponsor completion) ──────────────────────

    async def upsert_pending_referral(
        self, user_id: int, referrer_id: int, sponsor_count: int
    ) -> None:
        await self._conn.execute(
            """INSERT INTO pending_referral (user_id, referrer_id, sponsor_count)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO NOTHING""",
            (user_id, referrer_id, sponsor_count),
        )
        await self._conn.commit()

    async def get_pending_referral(self, user_id: int) -> Optional[dict]:
        async with self._conn.execute(
            "SELECT * FROM pending_referral WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {"user_id": row["user_id"], "referrer_id": row["referrer_id"], "sponsor_count": row["sponsor_count"]}

    async def delete_pending_referral(self, user_id: int) -> None:
        await self._conn.execute("DELETE FROM pending_referral WHERE user_id = ?", (user_id,))
        await self._conn.commit()

    # ── Subscription tracking (for revocation) ──────────────────────────────────

    async def create_subscription_tracking(
        self, user_id: int, referrer_id: int, reward_amount: float
    ) -> None:
        await self._conn.execute(
            """INSERT OR IGNORE INTO subscription_tracking
               (user_id, referrer_id, reward_amount)
               VALUES (?, ?, ?)""",
            (user_id, referrer_id, reward_amount),
        )
        await self._conn.commit()

    async def get_active_tracking_records(self) -> list[dict]:
        async with self._conn.execute(
            """SELECT st.id, st.user_id, st.referrer_id, st.reward_amount,
                      u.telegram_id as referred_telegram_id,
                      r.telegram_id as referrer_telegram_id,
                      r.id as referrer_db_id,
                      r.stars_balance as referrer_balance
               FROM subscription_tracking st
               JOIN users u ON u.id = st.user_id
               JOIN users r ON r.id = st.referrer_id
               WHERE st.reward_revoked = 0"""
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def revoke_tracking_reward(self, tracking_id: int) -> None:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await self._conn.execute(
            "UPDATE subscription_tracking SET reward_revoked = 1, last_checked = ? WHERE id = ?",
            (now, tracking_id),
        )
        await self._conn.commit()

    async def update_tracking_last_checked(self, tracking_id: int) -> None:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await self._conn.execute(
            "UPDATE subscription_tracking SET last_checked = ? WHERE id = ?",
            (now, tracking_id),
        )
        await self._conn.commit()

    async def has_subscription_tracking(self, user_id: int) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM subscription_tracking WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row is not None
