from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    stars_balance: float
    ref_code: Optional[str]
    referred_by: Optional[int]
    total_refs: int
    total_earned: float
    last_bonus_at: Optional[datetime]
    is_banned: bool
    sponsors_passed: bool
    created_at: datetime

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        if self.first_name:
            return self.first_name
        return str(self.telegram_id)


@dataclass
class Sponsor:
    id: int
    channel_id: int
    channel_username: Optional[str]
    channel_title: str
    invite_link: Optional[str]
    added_at: datetime

    @property
    def url(self) -> Optional[str]:
        if self.channel_username:
            username = self.channel_username.lstrip("@")
            return f"https://t.me/{username}"
        return self.invite_link


@dataclass
class Promocode:
    id: int
    code: str
    stars_amount: float
    max_uses: int
    uses_count: int
    is_active: bool
    created_at: datetime

    @property
    def is_available(self) -> bool:
        return self.is_active and self.uses_count < self.max_uses


@dataclass
class WithdrawalRequest:
    id: int
    user_id: int
    amount: float
    wallet: Optional[str]
    status: str
    created_at: datetime


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    stars_balance REAL DEFAULT 0,
    ref_code TEXT UNIQUE,
    referred_by INTEGER,
    total_refs INTEGER DEFAULT 0,
    total_earned REAL DEFAULT 0,
    last_bonus_at DATETIME,
    is_banned INTEGER DEFAULT 0,
    sponsors_passed INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (referred_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_ref_code ON users(ref_code);
CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);

CREATE TABLE IF NOT EXISTS sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER UNIQUE NOT NULL,
    channel_username TEXT,
    channel_title TEXT NOT NULL,
    invite_link TEXT,
    added_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS promocodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    stars_amount REAL NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    uses_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code);

CREATE TABLE IF NOT EXISTS promocode_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promocode_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    used_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (promocode_id) REFERENCES promocodes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(promocode_id, user_id)
);

CREATE TABLE IF NOT EXISTS withdrawal_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    wallet TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawal_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawal_requests(status);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL,
    referred_id INTEGER NOT NULL,
    stars_amount REAL NOT NULL,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Stores sponsor count before user subscribes, used for reward calculation
CREATE TABLE IF NOT EXISTS pending_referral (
    user_id INTEGER PRIMARY KEY,
    referrer_id INTEGER NOT NULL,
    sponsor_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tracks subscription status for revocation checks
CREATE TABLE IF NOT EXISTS subscription_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    referrer_id INTEGER NOT NULL,
    reward_amount REAL NOT NULL,
    reward_revoked INTEGER DEFAULT 0,
    last_checked DATETIME DEFAULT (datetime('now')),
    created_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE
);
"""
