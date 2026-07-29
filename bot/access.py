# -*- coding: utf-8 -*-
"""קופונים, מצבי משתמש ומגבלות שימוש (SQLite)."""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from bot.config import (
    COUPON_DB_PATH,
    FREE_TRIAL_IMAGES,
    IMAGE_COOLDOWN_SEC,
    IMAGE_GUEST_COOLDOWN_SEC,
    IMAGE_QUOTA_WINDOW_SEC,
)

log = logging.getLogger("beam_telegram_bot")

_COUPON_CODE_RE = re.compile(r"^[A-Z0-9]{8,16}$")
_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

VALID_DAILY_QUOTAS = frozenset({6, 999})
VALID_PERIOD_DAYS = frozenset({100, 105})
# VIP — פותח מאגר תרגילים בלי cooldown של המאגר (לא פוטר מ־10 דק' על פתרון/תרגול).
VIP_UNLIMITED_DAILY_QUOTA = 999
# תאימות לאחור (ערכי קופון ב־DB)
VALID_TIERS = VALID_DAILY_QUOTAS
_QUOTA_SQL_LIST = ", ".join(str(q) for q in sorted(VALID_DAILY_QUOTAS))
_PERIOD_SQL_LIST = ", ".join(str(d) for d in sorted(VALID_PERIOD_DAYS))
# חלון מועדף: 24 שעות מ־first_seen_at (/start ראשון).
FORMULAS_FREE_WINDOW_SEC = 24 * 3600
# המתנה מינימלית בין שימושים בפתרון (חשב) ובתרגול — לכל המצבים.
FEATURE_COOLDOWN_SEC = float(IMAGE_COOLDOWN_SEC) if IMAGE_COOLDOWN_SEC > 0 else 600.0
# בלי קופון ואחרי חלון 24ש': פעם אחת לכל יכולת בחלון זה.
FEATURE_DAILY_LIMIT_SEC = 24 * 3600.0


class RedeemStatus(Enum):
    OK = "ok"
    BANK_UNLOCK_OK = "bank_unlock_ok"
    NOT_FOUND = "not_found"
    ALREADY_USED = "already_used"
    USED_BY_OTHER = "used_by_other"
    INVALID_TIER = "invalid_tier"


class UserAccessPhase(Enum):
    """מצב הרשאות כללי של המשתמש."""

    PRIVILEGED = "privileged"  # 24ש' ראשונות או קופון פעיל
    RESTRICTED = "restricted"  # אחרי 24ש' ובלי קופון


class FeatureKind(Enum):
    SOLVE = "solve"  # לחיצה על «חשב» בטיוטה (שליפת נתונים / פתרון)
    PRACTICE = "practice"  # תרגול


class ImageAccessStatus(Enum):
    OK = "ok"
    NO_ENTITLEMENT = "no_entitlement"
    QUOTA_EXCEEDED = "quota_exceeded"  # תאימות — ממופה ל־DAILY_LIMIT
    TRIAL_EXHAUSTED = "trial_exhausted"
    ACCESS_EXPIRED = "access_expired"
    COOLDOWN = "cooldown"
    DAILY_LIMIT = "daily_limit"


class AccessSource(Enum):
    FREE_WINDOW = "free_window"
    COUPON = "coupon"
    RESTRICTED = "restricted"
    TRIAL = "trial"  # תאימות לאחור
    GUEST = "guest"  # תאימות לאחור ≈ RESTRICTED


@dataclass(frozen=True)
class RedeemResult:
    status: RedeemStatus
    tier: int | None = None
    period_days: int | None = None
    period_expires_at: float | None = None


@dataclass(frozen=True)
class ImageAccessResult:
    """תוצאת שער ליכולת (solve/practice) — שם היסטורי Image* לתאימות."""

    status: ImageAccessStatus
    tier_limit: int = 0
    images_used: int = 0
    images_remaining: int = 0
    window_reset_sec: float | None = None
    period_expires_sec: float | None = None
    period_days: int | None = None
    access_source: AccessSource | None = None
    cooldown_remaining_sec: float | None = None
    feature: str | None = None
    phase: UserAccessPhase | None = None


def normalize_coupon_code(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (text or "").strip()).upper()


def looks_like_coupon_code(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or " " in raw:
        return False
    if not re.fullmatch(r"[A-Z0-9]+", raw):
        return False
    return bool(_COUPON_CODE_RE.fullmatch(raw))


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY,
            daily_quota INTEGER NOT NULL CHECK (daily_quota IN ({_QUOTA_SQL_LIST})),
            period_days INTEGER NOT NULL CHECK (period_days IN ({_PERIOD_SQL_LIST})),
            redeemed_by INTEGER,
            redeemed_at REAL
        );
        CREATE TABLE IF NOT EXISTS user_access (
            user_id INTEGER PRIMARY KEY,
            tier_limit INTEGER NOT NULL CHECK (tier_limit IN ({_QUOTA_SQL_LIST})),
            period_expires_at REAL NOT NULL,
            window_start REAL,
            images_used INTEGER NOT NULL DEFAULT 0,
            last_image_at REAL
        );
        CREATE TABLE IF NOT EXISTS user_trial (
            user_id INTEGER PRIMARY KEY,
            images_used INTEGER NOT NULL DEFAULT 0,
            last_image_at REAL
        );
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            daily_quota INTEGER NOT NULL,
            period_days INTEGER NOT NULL,
            price_ils INTEGER NOT NULL,
            package_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bank_unlock_coupons (
            code TEXT PRIMARY KEY,
            redeemed_by INTEGER,
            redeemed_at REAL
        );
        CREATE TABLE IF NOT EXISTS user_bank_unlock (
            user_id INTEGER PRIMARY KEY,
            unlocked_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_first_seen (
            user_id INTEGER PRIMARY KEY,
            first_seen_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_feature_usage (
            user_id INTEGER NOT NULL,
            feature TEXT NOT NULL,
            last_used_at REAL NOT NULL,
            PRIMARY KEY (user_id, feature)
        );
        """
    )
    conn.commit()
    _migrate_coupon_period_schema(conn)
    _migrate_coupon_quota_constraints(conn)
    _migrate_last_image_at_columns(conn)
    _migrate_bank_unlock_tables(conn)
    _migrate_user_first_seen_table(conn)
    _migrate_user_feature_usage_table(conn)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _migrate_bank_unlock_tables(conn: sqlite3.Connection) -> None:
    """יוצר טבלאות פטור מ-cooldown של מאגר התרגילים אם חסרות."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bank_unlock_coupons (
            code TEXT PRIMARY KEY,
            redeemed_by INTEGER,
            redeemed_at REAL
        );
        CREATE TABLE IF NOT EXISTS user_bank_unlock (
            user_id INTEGER PRIMARY KEY,
            unlocked_at REAL NOT NULL
        );
        """
    )
    conn.commit()


def _migrate_user_first_seen_table(conn: sqlite3.Connection) -> None:
    """יוצר טבלת first_seen (תחילת חלון 24ש' מועדף) אם חסרה."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_first_seen (
            user_id INTEGER PRIMARY KEY,
            first_seen_at REAL NOT NULL
        );
        """
    )
    conn.commit()


def _migrate_user_feature_usage_table(conn: sqlite3.Connection) -> None:
    """יוצר טבלת שימוש אחרון לפתרון/תרגול אם חסרה."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_feature_usage (
            user_id INTEGER NOT NULL,
            feature TEXT NOT NULL,
            last_used_at REAL NOT NULL,
            PRIMARY KEY (user_id, feature)
        );
        """
    )
    conn.commit()


def _migrate_last_image_at_columns(conn: sqlite3.Connection) -> None:
    """מוסיף last_image_at לטבלאות קיימות שלא נבנו איתו."""
    access_cols = _table_columns(conn, "user_access")
    if access_cols and "last_image_at" not in access_cols:
        with _db_lock:
            conn.execute("ALTER TABLE user_access ADD COLUMN last_image_at REAL")
            conn.commit()
            log.info("user_access migrated with last_image_at")
    trial_cols = _table_columns(conn, "user_trial")
    if trial_cols and "last_image_at" not in trial_cols:
        with _db_lock:
            conn.execute("ALTER TABLE user_trial ADD COLUMN last_image_at REAL")
            conn.commit()
            log.info("user_trial migrated with last_image_at")


def _migrate_coupon_period_schema(conn: sqlite3.Connection) -> None:
    """מעבר מסכימת tier בלבד לסכימה עם daily_quota + period_days + תפוגה."""
    coupon_cols = _table_columns(conn, "coupons")
    if coupon_cols and "period_days" not in coupon_cols:
        with _db_lock:
            conn.executescript(
                f"""
                CREATE TABLE coupons_new (
                    code TEXT PRIMARY KEY,
                    daily_quota INTEGER NOT NULL CHECK (daily_quota IN ({_QUOTA_SQL_LIST})),
                    period_days INTEGER NOT NULL CHECK (period_days IN ({_PERIOD_SQL_LIST})),
                    redeemed_by INTEGER,
                    redeemed_at REAL
                );
                INSERT INTO coupons_new (code, daily_quota, period_days, redeemed_by, redeemed_at)
                SELECT code,
                       CASE WHEN tier IN (2, 5, 10) THEN tier ELSE 2 END,
                       30,
                       redeemed_by,
                       redeemed_at
                FROM coupons;
                DROP TABLE coupons;
                ALTER TABLE coupons_new RENAME TO coupons;
                """
            )
            conn.commit()
            log.info("Coupons table migrated to daily_quota + period_days")

    access_cols = _table_columns(conn, "user_access")
    if access_cols and "period_expires_at" not in access_cols:
        with _db_lock:
            far_future = time.time() + 30 * 86400
            conn.execute(
                "ALTER TABLE user_access ADD COLUMN period_expires_at REAL"
            )
            conn.execute(
                "UPDATE user_access SET period_expires_at = ? "
                "WHERE period_expires_at IS NULL",
                (far_future,),
            )
            conn.commit()
            log.info("user_access migrated with period_expires_at")


def _quota_check_satisfied(ddl: str) -> bool:
    normalized = ddl.replace(" ", "")
    return all(f"{q}" in normalized for q in sorted(VALID_DAILY_QUOTAS))


def _period_check_satisfied(ddl: str) -> bool:
    normalized = ddl.replace(" ", "")
    return all(f"{d}" in normalized for d in sorted(VALID_PERIOD_DAYS))


def _migrate_coupon_quota_constraints(conn: sqlite3.Connection) -> None:
    """מרחיב CHECK constraints לטבלאות coupons/user_access כשמתווספות מכסות/תקופות."""
    coupon_cols = _table_columns(conn, "coupons")
    access_cols = _table_columns(conn, "user_access")
    if not coupon_cols or not access_cols:
        return

    coupon_ddl_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='coupons'"
    ).fetchone()
    access_ddl_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_access'"
    ).fetchone()
    coupon_ddl = str(coupon_ddl_row[0] or "") if coupon_ddl_row is not None else ""
    access_ddl = str(access_ddl_row[0] or "") if access_ddl_row is not None else ""

    coupon_ok = _quota_check_satisfied(coupon_ddl) and _period_check_satisfied(coupon_ddl)
    access_ok = _quota_check_satisfied(access_ddl)
    if coupon_ok and access_ok:
        return

    with _db_lock:
        access_has_last = "last_image_at" in access_cols
        last_select = "last_image_at" if access_has_last else "NULL"
        conn.executescript(
            f"""
            CREATE TABLE coupons_new (
                code TEXT PRIMARY KEY,
                daily_quota INTEGER NOT NULL CHECK (daily_quota IN ({_QUOTA_SQL_LIST})),
                period_days INTEGER NOT NULL CHECK (period_days IN ({_PERIOD_SQL_LIST})),
                redeemed_by INTEGER,
                redeemed_at REAL
            );
            INSERT INTO coupons_new (code, daily_quota, period_days, redeemed_by, redeemed_at)
            SELECT code, daily_quota, period_days, redeemed_by, redeemed_at
            FROM coupons
            WHERE daily_quota IN ({_QUOTA_SQL_LIST})
              AND period_days IN ({_PERIOD_SQL_LIST});
            DROP TABLE coupons;
            ALTER TABLE coupons_new RENAME TO coupons;

            CREATE TABLE user_access_new (
                user_id INTEGER PRIMARY KEY,
                tier_limit INTEGER NOT NULL CHECK (tier_limit IN ({_QUOTA_SQL_LIST})),
                period_expires_at REAL NOT NULL,
                window_start REAL,
                images_used INTEGER NOT NULL DEFAULT 0,
                last_image_at REAL
            );
            INSERT INTO user_access_new (
                user_id, tier_limit, period_expires_at, window_start, images_used, last_image_at
            )
            SELECT user_id, tier_limit, period_expires_at, window_start, images_used, {last_select}
            FROM user_access
            WHERE tier_limit IN ({_QUOTA_SQL_LIST});
            DROP TABLE user_access;
            ALTER TABLE user_access_new RENAME TO user_access;
            """
        )
        conn.commit()
        log.info("Coupons/user_access constraints migrated (quota/period expanded)")


def _migrate_tier_schema(conn: sqlite3.Connection) -> None:
    """Legacy no-op — נשמר לתאימות קריאות ישנות."""
    _migrate_coupon_period_schema(conn)


@dataclass(frozen=True)
class PurchaseRequest:
    id: int
    user_id: int
    chat_id: int
    daily_quota: int
    period_days: int
    price_ils: int
    package_label: str
    status: str
    created_at: float


def create_purchase_request(
    *,
    user_id: int,
    chat_id: int,
    daily_quota: int,
    period_days: int,
    price_ils: int,
    package_label: str,
) -> PurchaseRequest:
    if daily_quota not in VALID_DAILY_QUOTAS:
        raise ValueError(f"daily_quota must be one of {sorted(VALID_DAILY_QUOTAS)}")
    conn = _connect()
    now = time.time()
    with _db_lock:
        cur = conn.execute(
            """
            INSERT INTO purchase_requests (
                user_id, chat_id, daily_quota, period_days, price_ils,
                package_label, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                int(user_id),
                int(chat_id),
                int(daily_quota),
                int(period_days),
                int(price_ils),
                package_label,
                now,
            ),
        )
        conn.commit()
        row_id = int(cur.lastrowid)
    log.info(
        "Purchase request #%s user=%s quota=%s days=%s price=%s",
        row_id,
        user_id,
        daily_quota,
        period_days,
        price_ils,
    )
    return PurchaseRequest(
        id=row_id,
        user_id=int(user_id),
        chat_id=int(chat_id),
        daily_quota=int(daily_quota),
        period_days=int(period_days),
        price_ils=int(price_ils),
        package_label=package_label,
        status="pending",
        created_at=now,
    )


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = Path(COUPON_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def init_access_db() -> None:
    """אתחול DB בהפעלת הבוט — מבטיח שהטבלאות קיימות."""
    _connect()


def close_access_db() -> None:
    """סגירת חיבור DB — לשימוש בטסטים בלבד."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def access_status_summary() -> str:
    from bot.config import COUPON_ACCESS_ENABLED, COUPON_DB_PATH, COUPON_GATE_VERSION

    conn = _connect()
    with _db_lock:
        coupon_count = int(conn.execute("SELECT COUNT(*) FROM coupons").fetchone()[0])
        active_users = int(
            conn.execute("SELECT COUNT(*) FROM user_access").fetchone()[0]
        )
    enabled = "on" if COUPON_ACCESS_ENABLED else "off"
    return (
        f"pong | coupon_gate={COUPON_GATE_VERSION} {enabled} | "
        f"db={COUPON_DB_PATH.name} | codes={coupon_count} | users={active_users}"
    )


def ping_reply_hebrew() -> str:
    """תשובה ידידותית ל-/ping (לא דיבוג טכני)."""
    from bot.config import COUPON_ACCESS_ENABLED

    if COUPON_ACCESS_ENABLED:
        return (
            "הבוט פעיל.\n"
            "שלח/י תמונה של תרגיל — בלי קופון יש המתנה בין תמונות.\n"
            "לבדיקת מכסה: /quota"
        )
    return "הבוט פעיל."


def insert_coupon_codes(
    codes: list[str],
    *,
    daily_quota: int,
    period_days: int,
) -> int:
    """מוסיף קודים חדשים. מחזיר כמה נוספו בפועל."""
    if daily_quota not in VALID_DAILY_QUOTAS:
        raise ValueError(
            f"daily_quota must be one of {sorted(VALID_DAILY_QUOTAS)}, got {daily_quota}"
        )
    if period_days not in VALID_PERIOD_DAYS:
        raise ValueError(
            f"period_days must be one of {sorted(VALID_PERIOD_DAYS)}, got {period_days}"
        )
    conn = _connect()
    added = 0
    with _db_lock:
        for raw in codes:
            code = normalize_coupon_code(raw)
            if not _COUPON_CODE_RE.fullmatch(code):
                continue
            try:
                conn.execute(
                    "INSERT INTO coupons (code, daily_quota, period_days) VALUES (?, ?, ?)",
                    (code, int(daily_quota), int(period_days)),
                )
                added += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    return added


def insert_bank_unlock_codes(codes: list[str]) -> int:
    """מוסיף קודי פטור מ-cooldown של מאגר התרגילים. מחזיר כמה נוספו."""
    conn = _connect()
    added = 0
    with _db_lock:
        for raw in codes:
            code = normalize_coupon_code(raw)
            if not _COUPON_CODE_RE.fullmatch(code):
                continue
            exists = conn.execute(
                "SELECT 1 FROM coupons WHERE code = ?", (code,)
            ).fetchone()
            if exists is not None:
                continue
            try:
                conn.execute(
                    "INSERT INTO bank_unlock_coupons (code) VALUES (?)",
                    (code,),
                )
                added += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    return added


def user_has_bank_unlock(user_id: int) -> bool:
    """True אם למשתמש פטור מ-cooldown של מאגר התרגילים."""
    conn = _connect()
    with _db_lock:
        row = conn.execute(
            "SELECT 1 FROM user_bank_unlock WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
    return row is not None


def _redeem_bank_unlock_coupon(
    conn: sqlite3.Connection, code: str, user_id: int
) -> RedeemResult:
    row = conn.execute(
        "SELECT code, redeemed_by FROM bank_unlock_coupons WHERE code = ?",
        (code,),
    ).fetchone()
    if row is None:
        return RedeemResult(RedeemStatus.NOT_FOUND)

    redeemed_by = row["redeemed_by"]
    if redeemed_by is not None:
        if int(redeemed_by) == int(user_id):
            return RedeemResult(RedeemStatus.ALREADY_USED)
        return RedeemResult(RedeemStatus.USED_BY_OTHER)

    now = time.time()
    conn.execute(
        "UPDATE bank_unlock_coupons SET redeemed_by = ?, redeemed_at = ? WHERE code = ?",
        (int(user_id), now, code),
    )
    conn.execute(
        """
        INSERT INTO user_bank_unlock (user_id, unlocked_at) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET unlocked_at = excluded.unlocked_at
        """,
        (int(user_id), now),
    )
    conn.commit()
    log.info("Bank-unlock coupon %s redeemed by user %s", code, user_id)
    return RedeemResult(RedeemStatus.BANK_UNLOCK_OK)


def _period_seconds(period_days: int) -> float:
    return float(int(period_days) * 86400)


def _format_duration_hebrew(seconds: float) -> str:
    secs = max(0, int(seconds))
    days = secs // 86400
    if days >= 2:
        return f"{days} ימים"
    if days == 1:
        return "יום אחד"
    hours = secs // 3600
    if hours >= 2:
        return f"{hours} שעות"
    if hours == 1:
        return "שעה אחת"
    mins = max(1, secs // 60)
    if mins == 1:
        return "דקה אחת"
    return f"{mins} דקות"


def _period_label_hebrew(period_days: int) -> str:
    from bot.purchase import _period_label

    return _period_label(period_days)


def _clear_expired_access_unlocked(
    conn: sqlite3.Connection, user_id: int, period_expires_at: float | None, now: float
) -> bool:
    if period_expires_at is None:
        return False
    if now < float(period_expires_at):
        return False
    conn.execute("DELETE FROM user_access WHERE user_id = ?", (int(user_id),))
    return True


def redeem_coupon(code: str, user_id: int) -> RedeemResult:
    normalized = normalize_coupon_code(code)
    if not _COUPON_CODE_RE.fullmatch(normalized):
        return RedeemResult(RedeemStatus.NOT_FOUND)

    conn = _connect()
    now = time.time()
    with _db_lock:
        row = conn.execute(
            "SELECT code, daily_quota, period_days, redeemed_by FROM coupons WHERE code = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            return _redeem_bank_unlock_coupon(conn, normalized, user_id)

        daily_quota = int(row["daily_quota"])
        period_days = int(row["period_days"])
        if daily_quota not in VALID_DAILY_QUOTAS:
            return RedeemResult(RedeemStatus.INVALID_TIER)
        if period_days not in VALID_PERIOD_DAYS:
            return RedeemResult(RedeemStatus.INVALID_TIER)

        redeemed_by = row["redeemed_by"]
        if redeemed_by is not None:
            if int(redeemed_by) == int(user_id):
                access = conn.execute(
                    "SELECT period_expires_at FROM user_access WHERE user_id = ?",
                    (int(user_id),),
                ).fetchone()
                expires = (
                    float(access["period_expires_at"])
                    if access is not None
                    else None
                )
                return RedeemResult(
                    RedeemStatus.ALREADY_USED,
                    tier=daily_quota,
                    period_days=period_days,
                    period_expires_at=expires,
                )
            return RedeemResult(
                RedeemStatus.USED_BY_OTHER,
                tier=daily_quota,
                period_days=period_days,
            )

        period_expires_at = now + _period_seconds(period_days)
        conn.execute(
            "UPDATE coupons SET redeemed_by = ?, redeemed_at = ? WHERE code = ?",
            (int(user_id), now, normalized),
        )
        conn.execute(
            """
            INSERT INTO user_access (
                user_id, tier_limit, period_expires_at, window_start, images_used
            ) VALUES (?, ?, ?, NULL, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                tier_limit = excluded.tier_limit,
                period_expires_at = excluded.period_expires_at,
                window_start = NULL,
                images_used = 0
            """,
            (int(user_id), daily_quota, period_expires_at),
        )
        if daily_quota == VIP_UNLIMITED_DAILY_QUOTA:
            conn.execute(
                """
                INSERT INTO user_bank_unlock (user_id, unlocked_at) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET unlocked_at = excluded.unlocked_at
                """,
                (int(user_id), now),
            )
        conn.commit()
        log.info(
            "Coupon %s redeemed by user %s (quota=%s days=%s expires=%s)",
            normalized,
            user_id,
            daily_quota,
            period_days,
            period_expires_at,
        )
        return RedeemResult(
            RedeemStatus.OK,
            tier=daily_quota,
            period_days=period_days,
            period_expires_at=period_expires_at,
        )


def _load_coupon_access_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT tier_limit, period_expires_at, window_start, images_used, last_image_at "
        "FROM user_access WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    if _clear_expired_access_unlocked(
        conn, user_id, row["period_expires_at"], now
    ):
        return None
    return row


def _cooldown_remaining_sec(
    last_used_at: float | None,
    now: float,
    *,
    cooldown_sec: float,
) -> float | None:
    if last_used_at is None or cooldown_sec <= 0:
        return None
    remaining = float(cooldown_sec) - (now - float(last_used_at))
    return remaining if remaining > 0 else None


def _period_left_for_user(
    conn: sqlite3.Connection, user_id: int, now: float
) -> tuple[float | None, int | None]:
    row = _load_coupon_access_unlocked(conn, int(user_id), now)
    if row is None:
        return None, None
    period_expires_at = float(row["period_expires_at"])
    period_expires_sec = max(0.0, period_expires_at - now)
    period_days = (
        max(1, int(round(period_expires_sec / 86400))) if period_expires_sec > 0 else None
    )
    return period_expires_sec, period_days


def _access_source_for_phase(
    phase: UserAccessPhase, *, has_coupon: bool
) -> AccessSource:
    if phase == UserAccessPhase.PRIVILEGED:
        return AccessSource.COUPON if has_coupon else AccessSource.FREE_WINDOW
    return AccessSource.RESTRICTED


def _ensure_user_first_seen_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> float:
    uid = int(user_id)
    row = conn.execute(
        "SELECT first_seen_at FROM user_first_seen WHERE user_id = ?",
        (uid,),
    ).fetchone()
    if row is not None:
        return float(row["first_seen_at"])
    conn.execute(
        "INSERT INTO user_first_seen (user_id, first_seen_at) VALUES (?, ?)",
        (uid, now),
    )
    conn.commit()
    return float(now)


def _has_free_window_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> bool:
    first_seen = _ensure_user_first_seen_unlocked(conn, user_id, now)
    return (now - first_seen) < FORMULAS_FREE_WINDOW_SEC


def _phase_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> tuple[UserAccessPhase, bool]:
    has_coupon = _load_coupon_access_unlocked(conn, int(user_id), now) is not None
    if has_coupon or _has_free_window_unlocked(conn, int(user_id), now):
        return UserAccessPhase.PRIVILEGED, has_coupon
    return UserAccessPhase.RESTRICTED, False


def get_user_access_phase(user_id: int, *, now: float | None = None) -> UserAccessPhase:
    """PRIVILEGED = קופון פעיל או חלון 24ש'; אחרת RESTRICTED."""
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        phase, _ = _phase_unlocked(conn, int(user_id), ts)
        return phase


def is_privileged_access(user_id: int, *, now: float | None = None) -> bool:
    return get_user_access_phase(user_id, now=now) == UserAccessPhase.PRIVILEGED


def _feature_key(feature: FeatureKind | str) -> str:
    if isinstance(feature, FeatureKind):
        return feature.value
    key = str(feature).strip().lower()
    if key in (FeatureKind.SOLVE.value, FeatureKind.PRACTICE.value):
        return key
    raise ValueError(f"unknown feature: {feature!r}")


def _load_feature_last_used_unlocked(
    conn: sqlite3.Connection, user_id: int, feature: str
) -> float | None:
    row = conn.execute(
        "SELECT last_used_at FROM user_feature_usage WHERE user_id = ? AND feature = ?",
        (int(user_id), feature),
    ).fetchone()
    if row is None or row["last_used_at"] is None:
        return None
    return float(row["last_used_at"])


def _evaluate_feature_access(
    *,
    phase: UserAccessPhase,
    last_used_at: float | None,
    now: float,
    access_source: AccessSource,
    period_expires_sec: float | None,
    period_days: int | None,
    feature: str,
) -> ImageAccessResult:
    base = dict(
        tier_limit=0,
        images_used=0,
        images_remaining=0,
        period_expires_sec=period_expires_sec,
        period_days=period_days,
        access_source=access_source,
        feature=feature,
        phase=phase,
    )
    if last_used_at is not None and phase == UserAccessPhase.RESTRICTED:
        daily_left = _cooldown_remaining_sec(
            last_used_at, now, cooldown_sec=FEATURE_DAILY_LIMIT_SEC
        )
        if daily_left is not None:
            return ImageAccessResult(
                status=ImageAccessStatus.DAILY_LIMIT,
                window_reset_sec=daily_left,
                cooldown_remaining_sec=daily_left,
                **base,
            )
    cool = _cooldown_remaining_sec(
        last_used_at, now, cooldown_sec=FEATURE_COOLDOWN_SEC
    )
    if cool is not None:
        return ImageAccessResult(
            status=ImageAccessStatus.COOLDOWN,
            cooldown_remaining_sec=cool,
            **base,
        )
    return ImageAccessResult(status=ImageAccessStatus.OK, **base)


def check_feature_access(
    user_id: int,
    feature: FeatureKind | str,
    *,
    now: float | None = None,
) -> ImageAccessResult:
    """בודק מגבלות ליכולת בלי לצרוך."""
    key = _feature_key(feature)
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        phase, has_coupon = _phase_unlocked(conn, int(user_id), ts)
        period_expires_sec, period_days = _period_left_for_user(conn, int(user_id), ts)
        last_used = _load_feature_last_used_unlocked(conn, int(user_id), key)
        return _evaluate_feature_access(
            phase=phase,
            last_used_at=last_used,
            now=ts,
            access_source=_access_source_for_phase(phase, has_coupon=has_coupon),
            period_expires_sec=period_expires_sec,
            period_days=period_days,
            feature=key,
        )


def consume_feature_slot(
    user_id: int,
    feature: FeatureKind | str,
    *,
    now: float | None = None,
) -> ImageAccessResult:
    """מאשר שימוש ומעדכן last_used_at ליכולת."""
    key = _feature_key(feature)
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        phase, has_coupon = _phase_unlocked(conn, int(user_id), ts)
        period_expires_sec, period_days = _period_left_for_user(conn, int(user_id), ts)
        last_used = _load_feature_last_used_unlocked(conn, int(user_id), key)
        result = _evaluate_feature_access(
            phase=phase,
            last_used_at=last_used,
            now=ts,
            access_source=_access_source_for_phase(phase, has_coupon=has_coupon),
            period_expires_sec=period_expires_sec,
            period_days=period_days,
            feature=key,
        )
        if result.status != ImageAccessStatus.OK:
            return result
        conn.execute(
            "INSERT INTO user_feature_usage (user_id, feature, last_used_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, feature) DO UPDATE SET last_used_at = excluded.last_used_at",
            (int(user_id), key, ts),
        )
        conn.commit()
        log.info(
            "Feature slot user=%s feature=%s phase=%s",
            user_id,
            key,
            phase.value,
        )
        return result


def check_image_access(user_id: int) -> ImageAccessResult:
    """תאימות: שער פתרון (בלי צריכה)."""
    return check_feature_access(user_id, FeatureKind.SOLVE)


def check_solve_access(user_id: int) -> ImageAccessResult:
    return check_feature_access(user_id, FeatureKind.SOLVE)


def check_practice_feature_access(user_id: int) -> ImageAccessResult:
    return check_feature_access(user_id, FeatureKind.PRACTICE)


def consume_image_slot(user_id: int) -> ImageAccessResult:
    """תאימות: צריכת פתרון — עדיף לקרוא בלחיצת «חשב»."""
    return consume_feature_slot(user_id, FeatureKind.SOLVE)


def consume_solve_slot(user_id: int) -> ImageAccessResult:
    return consume_feature_slot(user_id, FeatureKind.SOLVE)


def consume_practice_slot(user_id: int) -> ImageAccessResult:
    return consume_feature_slot(user_id, FeatureKind.PRACTICE)


def has_active_coupon_access(user_id: int) -> bool:
    """True אם למשתמש יש חבילה/קופון פעיל."""
    conn = _connect()
    now = time.time()
    with _db_lock:
        row = _load_coupon_access_unlocked(conn, int(user_id), now)
        return row is not None


def ensure_user_first_seen(user_id: int, *, now: float | None = None) -> float:
    """
    מחזיר first_seen_at קבוע למשתמש; יוצר רשומה בפעם הראשונה.

    שעון חלון 24ש' המועדף מתחיל באינטראקציה הראשונה (בדרך כלל /start).
    """
    conn = _connect()
    ts = time.time() if now is None else float(now)
    with _db_lock:
        return _ensure_user_first_seen_unlocked(conn, int(user_id), ts)


def list_users_first_seen() -> list[tuple[int, float]]:
    """כל משתמשי /start: (user_id, first_seen_at) לפי סדר הופעה."""
    conn = _connect()
    with _db_lock:
        rows = conn.execute(
            "SELECT user_id, first_seen_at FROM user_first_seen "
            "ORDER BY first_seen_at ASC, user_id ASC"
        ).fetchall()
        return [(int(r["user_id"]), float(r["first_seen_at"])) for r in rows]


def has_formulas_free_window(user_id: int, *, now: float | None = None) -> bool:
    """True בתוך 24 השעות הראשונות מ־first_seen_at."""
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        return _has_free_window_unlocked(conn, int(user_id), ts)


def has_formulas_access(user_id: int) -> bool:
    """נוסחאות פתוחות תמיד."""
    return True


def has_practice_access(user_id: int) -> bool:
    """True אם מותר להתחיל תרגול עכשיו (בלי לצרוך)."""
    return (
        check_feature_access(user_id, FeatureKind.PRACTICE).status
        == ImageAccessStatus.OK
    )


def redeem_reply_hebrew(result: RedeemResult) -> str:
    tier = result.tier or 0
    period_days = result.period_days or 0
    period_label = _period_label_hebrew(period_days) if period_days else ""
    if result.status == RedeemStatus.BANK_UNLOCK_OK:
        return (
            "הקוד הופעל.\n"
            "מאגר התרגילים פתוח לך בלי הגבלת זמן בין תרגילים."
        )
    if result.status == RedeemStatus.OK:
        period_timer = ""
        if result.period_expires_at is not None:
            left = max(0.0, float(result.period_expires_at) - time.time())
            period_timer = (
                f"\nהמנוי פעיל לעוד *{_format_duration_hebrew(left)}* ({period_label})."
            )
        body = (
            f"הקופון הופעל.\n"
            f"גישה מועדפת לפתרון ותרגול למשך {period_label} "
            f"(המתנה של 10 דקות בין שימושים)."
            f"{period_timer}\n"
        )
        if tier == VIP_UNLIMITED_DAILY_QUOTA:
            body += "מאגר התרגילים פתוח לך בלי הגבלת זמן בין תרגילים.\n"
        body += "שלח/י עכשיו תמונה של התרגיל."
        return body
    if result.status == RedeemStatus.ALREADY_USED:
        if result.tier is None and result.period_days is None:
            return "קוד זה כבר מופעל בחשבון שלך (מאגר תרגילים ללא הגבלה)."
        timer = ""
        if result.period_expires_at is not None:
            left = max(0.0, float(result.period_expires_at) - time.time())
            if left > 0:
                timer = f" המנוי פעיל עוד {_format_duration_hebrew(left)}."
        return f"קוד זה כבר מופעל בחשבון שלך.{timer}"
    if result.status == RedeemStatus.USED_BY_OTHER:
        return "קוד הקופון כבר נוצל בחשבון אחר."
    if result.status == RedeemStatus.INVALID_TIER:
        return "קוד הקופון לא תקין או לא זמין."
    if result.status == RedeemStatus.NOT_FOUND:
        return "קוד הקופון לא תקין או לא זמין."
    return "קוד הקופון לא תקין או לא זמין."


def _feature_label_hebrew(feature: str | None) -> str:
    if feature == FeatureKind.PRACTICE.value:
        return "תרגול"
    return "פתרון"


def image_access_reply_hebrew(result: ImageAccessResult) -> str:
    label = _feature_label_hebrew(result.feature)
    if result.status == ImageAccessStatus.COOLDOWN:
        secs = result.cooldown_remaining_sec or 0.0
        mins = max(1, int((secs + 59) // 60))
        wait_mins = (
            max(1, int(FEATURE_COOLDOWN_SEC // 60)) if FEATURE_COOLDOWN_SEC > 0 else 0
        )
        wait_label = f"{wait_mins} דקות" if wait_mins > 0 else "כמה רגעים"
        return (
            f"אפשר להשתמש ב«{label}» שוב בעוד כ-{mins} דקות "
            f"(המתנה של {wait_label} בין שימושים)."
        )
    if result.status in (
        ImageAccessStatus.DAILY_LIMIT,
        ImageAccessStatus.QUOTA_EXCEEDED,
    ):
        secs = result.cooldown_remaining_sec or result.window_reset_sec or 0.0
        if secs > 3600:
            hours = max(1, int((secs + 3599) // 3600))
            wait = f"כ-{hours} שעות"
        else:
            mins = max(1, int((secs + 59) // 60))
            wait = f"כ-{mins} דקות"
        return (
            f"בלי קוד קופון אפשר להשתמש ב«{label}» פעם אחת ביממה.\n"
            f"נסה/י שוב בעוד {wait}, או הפעיל/י קוד קופון — /coupon"
        )
    if result.status == ImageAccessStatus.ACCESS_EXPIRED:
        return (
            "תקופת המנוי שלך הסתיימה.\n"
            "כדי להמשיך — הפעיל/י קוד קופון חדש או רכש/י חבילה (/coupon)."
        )
    if result.status == ImageAccessStatus.TRIAL_EXHAUSTED:
        return (
            "הגעת למגבלת השימוש.\n"
            "כדי להמשיך, בחר/י אחת מהאפשרויות למטה:"
        )
    if result.status == ImageAccessStatus.NO_ENTITLEMENT:
        return (
            "כדי להמשיך צריך קוד קופון פעיל.\n"
            "שלח/י את הקוד כהודעת טקסט לבוט, או רכש/י חבילה — /coupon."
        )
    return ""


def coupon_prompt_text_hebrew() -> str:
    return (
        "*הזנת קוד קופון*\n\n"
        "שלח/י את הקוד בטקסט (8–16 תווים, אותיות ומספרים בלבד).\n"
        "כל קוד פותח גישה מועדפת לפתרון ותרגול לתקופת המנוי "
        "(המתנה של 10 דקות בין שימושים).\n\n"
        "לבדיקת סטטוס: /quota"
    )


def _period_timer_line(result: ImageAccessResult) -> str:
    if result.period_expires_sec is None or result.period_expires_sec <= 0:
        return ""
    return f"המנוי פעיל לעוד {_format_duration_hebrew(result.period_expires_sec)}."


def _status_line_hebrew(label: str, res: ImageAccessResult) -> str:
    if res.status == ImageAccessStatus.COOLDOWN:
        secs = res.cooldown_remaining_sec or 0.0
        mins = max(1, int((secs + 59) // 60))
        return f"{label}: זמין שוב בעוד כ-{mins} דקות."
    if res.status in (
        ImageAccessStatus.DAILY_LIMIT,
        ImageAccessStatus.QUOTA_EXCEEDED,
    ):
        secs = res.cooldown_remaining_sec or res.window_reset_sec or 0.0
        mins = max(1, int((secs + 59) // 60))
        return f"{label}: נעשה שימוש היום — זמין שוב בעוד כ-{mins} דקות."
    return f"{label}: זמין עכשיו."


def quota_status_reply_hebrew(result: ImageAccessResult) -> str:
    """סטטוס לפי תוצאת שער פתרון (תאימות ל־/quota הישן)."""
    phase = result.phase
    if phase is None:
        if result.access_source in (AccessSource.COUPON, AccessSource.FREE_WINDOW):
            phase = UserAccessPhase.PRIVILEGED
        else:
            phase = UserAccessPhase.RESTRICTED
    lines: list[str] = []
    if phase == UserAccessPhase.PRIVILEGED:
        if result.access_source == AccessSource.COUPON:
            lines.append("מצב: מנוי פעיל (גישה מועדפת).")
            period_line = _period_timer_line(result)
            if period_line:
                lines.append(period_line)
        else:
            lines.append("מצב: 24 השעות הראשונות (גישה מועדפת).")
        lines.append("פתרון ותרגול: המתנה של 10 דקות בין שימושים.")
    else:
        lines.append("מצב: ללא קופון (אחרי 24 השעות הראשונות).")
        lines.append(
            "פתרון ותרגול: פעם אחת ביממה לכל יכולת, "
            "ובנוסף המתנה של 10 דקות בין שימושים."
        )
        lines.append("לשדרוג — הפעיל/י קוד קופון: /coupon")
    lines.append(_status_line_hebrew("פתרון", result))
    return "\n".join(lines)


def quota_status_for_user(user_id: int) -> str:
    """סטטוס מלא למשתמש — פתרון + תרגול."""
    solve = check_feature_access(user_id, FeatureKind.SOLVE)
    practice = check_feature_access(user_id, FeatureKind.PRACTICE)
    base_lines = quota_status_reply_hebrew(solve).split("\n")
    lines = [ln for ln in base_lines if not ln.startswith("פתרון:")]
    lines.append(_status_line_hebrew("פתרון", solve))
    lines.append(_status_line_hebrew("תרגול", practice))
    return "\n".join(lines)
