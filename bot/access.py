# -*- coding: utf-8 -*-
"""קופונים חד-פעמיים ומכסת תמונות לפי משתמש (SQLite)."""
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
# מכסה VIP — בפועל בלתי מוגבלת + פותחת את מאגר התרגילים בלי cooldown.
VIP_UNLIMITED_DAILY_QUOTA = 999
# תאימות לאחור (מכסה יומית בלבד)
VALID_TIERS = VALID_DAILY_QUOTAS
_QUOTA_SQL_LIST = ", ".join(str(q) for q in sorted(VALID_DAILY_QUOTAS))
_PERIOD_SQL_LIST = ", ".join(str(d) for d in sorted(VALID_PERIOD_DAYS))
# חלון חינמי לספריית נוסחאות: 24 שעות מ־first_seen_at (ראה ensure_user_first_seen).
FORMULAS_FREE_WINDOW_SEC = 24 * 3600


class RedeemStatus(Enum):
    OK = "ok"
    BANK_UNLOCK_OK = "bank_unlock_ok"
    NOT_FOUND = "not_found"
    ALREADY_USED = "already_used"
    USED_BY_OTHER = "used_by_other"
    INVALID_TIER = "invalid_tier"


class ImageAccessStatus(Enum):
    OK = "ok"
    NO_ENTITLEMENT = "no_entitlement"
    QUOTA_EXCEEDED = "quota_exceeded"
    TRIAL_EXHAUSTED = "trial_exhausted"
    ACCESS_EXPIRED = "access_expired"
    COOLDOWN = "cooldown"


class AccessSource(Enum):
    TRIAL = "trial"  # תאימות לאחור — זהה ל-GUEST במסלול בלי קופון
    GUEST = "guest"
    COUPON = "coupon"


@dataclass(frozen=True)
class RedeemResult:
    status: RedeemStatus
    tier: int | None = None
    period_days: int | None = None
    period_expires_at: float | None = None


@dataclass(frozen=True)
class ImageAccessResult:
    status: ImageAccessStatus
    tier_limit: int = 0
    images_used: int = 0
    images_remaining: int = 0
    window_reset_sec: float | None = None
    period_expires_sec: float | None = None
    period_days: int | None = None
    access_source: AccessSource | None = None
    cooldown_remaining_sec: float | None = None


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
        """
    )
    conn.commit()
    _migrate_coupon_period_schema(conn)
    _migrate_coupon_quota_constraints(conn)
    _migrate_last_image_at_columns(conn)
    _migrate_bank_unlock_tables(conn)
    _migrate_user_first_seen_table(conn)


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
    """יוצר טבלת first_seen (תחילת חלון 24ש' לנוסחאות) אם חסרה."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_first_seen (
            user_id INTEGER PRIMARY KEY,
            first_seen_at REAL NOT NULL
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
            "✅ הבוט פעיל.\n"
            "שלח/י תמונה 📸 של תרגיל — בלי קופון יש המתנה בין תמונות.\n"
            "לבדיקת מכסה: /quota"
        )
    return "✅ הבוט פעיל."


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


def _window_reset_in_sec(window_start: float | None, now: float) -> float | None:
    if window_start is None:
        return None
    elapsed = now - float(window_start)
    remaining = IMAGE_QUOTA_WINDOW_SEC - elapsed
    return max(0.0, remaining) if remaining > 0 else 0.0


def _cooldown_remaining_sec(
    last_image_at: float | None,
    now: float,
    *,
    cooldown_sec: float,
) -> float | None:
    if last_image_at is None or cooldown_sec <= 0:
        return None
    remaining = float(cooldown_sec) - (now - float(last_image_at))
    return remaining if remaining > 0 else None


def _vip_skips_image_cooldown(tier_limit: int) -> bool:
    return int(tier_limit) == VIP_UNLIMITED_DAILY_QUOTA


def _trial_images_used(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT images_used FROM user_trial WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return 0
    return int(row["images_used"])


def _trial_last_image_at(conn: sqlite3.Connection, user_id: int) -> float | None:
    row = conn.execute(
        "SELECT last_image_at FROM user_trial WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None or row["last_image_at"] is None:
        return None
    return float(row["last_image_at"])


def _check_guest_access_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float | None = None
) -> ImageAccessResult:
    """בלי קופון: שליחה חופשית (בלי מכסה), עם cooldown ארוך יותר."""
    used = _trial_images_used(conn, int(user_id))
    ts = time.time() if now is None else float(now)
    cool = _cooldown_remaining_sec(
        _trial_last_image_at(conn, int(user_id)),
        ts,
        cooldown_sec=IMAGE_GUEST_COOLDOWN_SEC,
    )
    if cool is not None:
        return ImageAccessResult(
            ImageAccessStatus.COOLDOWN,
            tier_limit=0,
            images_used=used,
            images_remaining=0,
            access_source=AccessSource.GUEST,
            cooldown_remaining_sec=cool,
        )
    return ImageAccessResult(
        ImageAccessStatus.OK,
        tier_limit=0,
        images_used=used,
        images_remaining=0,
        access_source=AccessSource.GUEST,
    )


def _check_trial_access_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float | None = None
) -> ImageAccessResult:
    """תאימות לשם הישן — כעת מסלול אורח (guest)."""
    return _check_guest_access_unlocked(conn, user_id, now)


def _check_trial_access(user_id: int) -> ImageAccessResult:
    conn = _connect()
    with _db_lock:
        return _check_guest_access_unlocked(conn, int(user_id), time.time())


def _consume_guest_slot(
    conn: sqlite3.Connection, user_id: int, now: float
) -> ImageAccessResult:
    used = _trial_images_used(conn, int(user_id))
    cool = _cooldown_remaining_sec(
        _trial_last_image_at(conn, int(user_id)),
        now,
        cooldown_sec=IMAGE_GUEST_COOLDOWN_SEC,
    )
    if cool is not None:
        return ImageAccessResult(
            ImageAccessStatus.COOLDOWN,
            tier_limit=0,
            images_used=used,
            images_remaining=0,
            access_source=AccessSource.GUEST,
            cooldown_remaining_sec=cool,
        )
    used += 1
    conn.execute(
        "INSERT INTO user_trial (user_id, images_used, last_image_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "images_used = excluded.images_used, last_image_at = excluded.last_image_at",
        (int(user_id), used, now),
    )
    log.info(
        "Guest image slot user=%s used=%s cooldown_sec=%s",
        user_id,
        used,
        IMAGE_GUEST_COOLDOWN_SEC,
    )
    return ImageAccessResult(
        ImageAccessStatus.OK,
        tier_limit=0,
        images_used=used,
        images_remaining=0,
        access_source=AccessSource.GUEST,
    )


def _consume_trial_slot(
    conn: sqlite3.Connection, user_id: int, now: float
) -> ImageAccessResult:
    """תאימות לשם הישן — כעת מסלול אורח (guest)."""
    return _consume_guest_slot(conn, user_id, now)


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


def _coupon_access_result_from_row(
    row: sqlite3.Row, *, now: float, status: ImageAccessStatus
) -> ImageAccessResult:
    tier_limit = int(row["tier_limit"])
    window_start = row["window_start"]
    images_used = int(row["images_used"])
    period_expires_at = float(row["period_expires_at"])
    period_expires_sec = max(0.0, period_expires_at - now)
    period_days = None
    if period_expires_sec > 0:
        period_days = max(1, int(round(period_expires_sec / 86400)))

    if window_start is not None and now >= float(window_start) + IMAGE_QUOTA_WINDOW_SEC:
        images_used = 0
        window_start = None

    remaining = max(0, tier_limit - images_used)
    reset_sec = _window_reset_in_sec(
        float(window_start) if window_start is not None else None,
        now,
    )
    cool = None
    if not _vip_skips_image_cooldown(tier_limit):
        cool = _cooldown_remaining_sec(
            row["last_image_at"], now, cooldown_sec=IMAGE_COOLDOWN_SEC
        )
    return ImageAccessResult(
        status=status,
        tier_limit=tier_limit,
        images_used=images_used,
        images_remaining=remaining,
        window_reset_sec=reset_sec,
        period_expires_sec=period_expires_sec,
        period_days=period_days,
        access_source=AccessSource.COUPON,
        cooldown_remaining_sec=cool,
    )


def check_image_access(user_id: int) -> ImageAccessResult:
    """בודק מכסה בלי לצרוך."""
    conn = _connect()
    now = time.time()
    with _db_lock:
        row = _load_coupon_access_unlocked(conn, int(user_id), now)
        if row is None:
            return _check_trial_access_unlocked(conn, int(user_id), now)

        result = _coupon_access_result_from_row(
            row, now=now, status=ImageAccessStatus.OK
        )
        if result.images_remaining <= 0:
            reset_sec = result.window_reset_sec
            if row["window_start"] is not None and now >= float(row["window_start"]) + IMAGE_QUOTA_WINDOW_SEC:
                reset_sec = 0.0
            return ImageAccessResult(
                ImageAccessStatus.QUOTA_EXCEEDED,
                tier_limit=result.tier_limit,
                images_used=result.images_used,
                images_remaining=0,
                window_reset_sec=reset_sec,
                period_expires_sec=result.period_expires_sec,
                period_days=result.period_days,
                access_source=AccessSource.COUPON,
            )
        if result.cooldown_remaining_sec is not None:
            return ImageAccessResult(
                ImageAccessStatus.COOLDOWN,
                tier_limit=result.tier_limit,
                images_used=result.images_used,
                images_remaining=result.images_remaining,
                window_reset_sec=result.window_reset_sec,
                period_expires_sec=result.period_expires_sec,
                period_days=result.period_days,
                access_source=AccessSource.COUPON,
                cooldown_remaining_sec=result.cooldown_remaining_sec,
            )
        return result


def has_active_coupon_access(user_id: int) -> bool:
    """True אם למשתמש יש חבילה/קופון פעיל (לא ניסיון חינם)."""
    conn = _connect()
    now = time.time()
    with _db_lock:
        row = _load_coupon_access_unlocked(conn, int(user_id), now)
        return row is not None


def ensure_user_first_seen(user_id: int, *, now: float | None = None) -> float:
    """
    מחזיר first_seen_at קבוע למשתמש; יוצר רשומה בפעם הראשונה.

    כלל חלון הנוסחאות החינמי: השעון מתחיל באינטראקציה הראשונה שנרשמת
    (בדרך כלל /start דרך ensure_user_first_seen, או בפתיחת נוסחאות דרך
    has_formulas_access). הערך לא משתנה אחרי יצירה.
    """
    conn = _connect()
    ts = time.time() if now is None else float(now)
    uid = int(user_id)
    with _db_lock:
        row = conn.execute(
            "SELECT first_seen_at FROM user_first_seen WHERE user_id = ?",
            (uid,),
        ).fetchone()
        if row is not None:
            return float(row["first_seen_at"])
        conn.execute(
            "INSERT INTO user_first_seen (user_id, first_seen_at) VALUES (?, ?)",
            (uid, ts),
        )
        conn.commit()
        return ts


def has_formulas_free_window(user_id: int, *, now: float | None = None) -> bool:
    """True בתוך 24 השעות הראשונות מ־first_seen_at (כולל יצירת הרשומה)."""
    ts = time.time() if now is None else float(now)
    first_seen = ensure_user_first_seen(user_id, now=ts)
    return (ts - first_seen) < FORMULAS_FREE_WINDOW_SEC


def has_formulas_access(user_id: int) -> bool:
    """True אם קופון פעיל או בתוך חלון 24 השעות החינמיות לנוסחאות."""
    if has_active_coupon_access(user_id):
        return True
    return has_formulas_free_window(user_id)


def consume_image_slot(user_id: int) -> ImageAccessResult:
    """מאשר תמונה ומגדיל מונה — קוראים לפני עיבוד vision."""
    conn = _connect()
    now = time.time()
    with _db_lock:
        row = _load_coupon_access_unlocked(conn, int(user_id), now)
        if row is None:
            result = _consume_trial_slot(conn, int(user_id), now)
            conn.commit()
            return result

        tier_limit = int(row["tier_limit"])
        period_expires_at = float(row["period_expires_at"])
        window_start = row["window_start"]
        images_used = int(row["images_used"])
        period_expires_sec = max(0.0, period_expires_at - now)

        if window_start is None or now >= float(window_start) + IMAGE_QUOTA_WINDOW_SEC:
            window_start = now
            images_used = 0

        if images_used >= tier_limit:
            reset_sec = max(
                0.0,
                float(window_start) + IMAGE_QUOTA_WINDOW_SEC - now,
            )
            return ImageAccessResult(
                ImageAccessStatus.QUOTA_EXCEEDED,
                tier_limit=tier_limit,
                images_used=images_used,
                images_remaining=0,
                window_reset_sec=reset_sec,
                period_expires_sec=period_expires_sec,
                access_source=AccessSource.COUPON,
            )

        cool = None
        if not _vip_skips_image_cooldown(tier_limit):
            cool = _cooldown_remaining_sec(
                row["last_image_at"], now, cooldown_sec=IMAGE_COOLDOWN_SEC
            )
        if cool is not None:
            return ImageAccessResult(
                ImageAccessStatus.COOLDOWN,
                tier_limit=tier_limit,
                images_used=images_used,
                images_remaining=max(0, tier_limit - images_used),
                window_reset_sec=max(
                    0.0, float(window_start) + IMAGE_QUOTA_WINDOW_SEC - now
                ),
                period_expires_sec=period_expires_sec,
                access_source=AccessSource.COUPON,
                cooldown_remaining_sec=cool,
            )

        images_used += 1
        conn.execute(
            "UPDATE user_access SET window_start = ?, images_used = ?, last_image_at = ? "
            "WHERE user_id = ?",
            (window_start, images_used, now, int(user_id)),
        )
        conn.commit()

        remaining = max(0, tier_limit - images_used)
        reset_sec = max(0.0, float(window_start) + IMAGE_QUOTA_WINDOW_SEC - now)
        log.info(
            "Image slot user=%s used=%s/%s reset_in=%.0fs period_left=%.0fs",
            user_id,
            images_used,
            tier_limit,
            reset_sec,
            period_expires_sec,
        )
        return ImageAccessResult(
            ImageAccessStatus.OK,
            tier_limit=tier_limit,
            images_used=images_used,
            images_remaining=remaining,
            window_reset_sec=reset_sec,
            period_expires_sec=period_expires_sec,
            access_source=AccessSource.COUPON,
        )


def redeem_reply_hebrew(result: RedeemResult) -> str:
    tier = result.tier or 0
    period_days = result.period_days or 0
    period_label = _period_label_hebrew(period_days) if period_days else ""
    if result.status == RedeemStatus.BANK_UNLOCK_OK:
        return (
            "✅ הקוד הופעל.\n"
            "מאגר התרגילים פתוח לך בלי הגבלת זמן בין תרגילים."
        )
    if result.status == RedeemStatus.OK:
        period_timer = ""
        if result.period_expires_at is not None:
            left = max(0.0, float(result.period_expires_at) - time.time())
            period_timer = f"\n⏳ המנוי פעיל לעוד *{_format_duration_hebrew(left)}* ({period_label})."
        if tier == VIP_UNLIMITED_DAILY_QUOTA:
            return (
                f"✅ הקופון הופעל.\n"
                f"גישה חופשית לתמונות (בלי מגבלת מכסה/המתנה) למשך {period_label}."
                f"{period_timer}\n"
                "מאגר התרגילים פתוח לך בלי הגבלת זמן בין תרגילים.\n"
                "שלח/י עכשיו תמונה של התרגיל."
            )
        return (
            f"✅ הקופון הופעל.\n"
            f"מכסה: עד {tier} תמונות ביום (חלון 24 שעות).{period_timer}\n"
            "שלח/י עכשיו תמונה של התרגיל."
        )
    if result.status == RedeemStatus.ALREADY_USED:
        if result.tier is None and result.period_days is None:
            return "קוד זה כבר מופעל בחשבון שלך (מאגר תרגילים ללא הגבלה)."
        timer = ""
        if result.period_expires_at is not None:
            left = max(0.0, float(result.period_expires_at) - time.time())
            if left > 0:
                timer = f" המנוי פעיל לעוד {_format_duration_hebrew(left)}."
        return (
            f"קוד זה כבר מופעל בחשבון שלך "
            f"(מכסה: {tier} תמונות ליום).{timer}"
        )
    if result.status == RedeemStatus.USED_BY_OTHER:
        return "קוד הקופון כבר נוצל בחשבון אחר."
    if result.status == RedeemStatus.NOT_FOUND:
        return "קוד הקופון לא תקין או לא זמין."
    return "קוד הקופון לא תקין או לא זמין."


def image_access_reply_hebrew(result: ImageAccessResult) -> str:
    from bot.config import FREE_TRIAL_IMAGES

    if result.status == ImageAccessStatus.TRIAL_EXHAUSTED:
        return (
            f"השתמשת ב-{FREE_TRIAL_IMAGES} תמונות הניסיון החינמיות.\n"
            "כדי להמשיך, בחר/י אחת מהאפשרויות למטה:"
        )
    if result.status == ImageAccessStatus.ACCESS_EXPIRED:
        return (
            "⏱️ תקופת המנוי שלך הסתיימה.\n"
            "כדי להמשיך — הפעיל/י קוד קופון חדש או רכש/י חבילה (/coupon)."
        )
    if result.status == ImageAccessStatus.NO_ENTITLEMENT:
        return (
            "כדי לפענח תמונה צריך קוד קופון פעיל.\n"
            "לחץ/י «🎟️ הזן קוד קופון» בתפריט (/start) או שלח/י /coupon."
        )
    if result.status == ImageAccessStatus.COOLDOWN:
        secs = result.cooldown_remaining_sec or 0.0
        mins = max(1, int((secs + 59) // 60))
        wait_total = (
            int(IMAGE_GUEST_COOLDOWN_SEC // 60)
            if result.access_source == AccessSource.GUEST
            else int(IMAGE_COOLDOWN_SEC // 60)
        )
        wait_label = f"{wait_total} דקות" if wait_total > 0 else "כמה רגעים"
        return (
            f"אפשר לשלוח תמונה נוספת בעוד כ-{mins} דקות "
            f"(המתנה של {wait_label} בין תמונות)."
        )
    if result.status == ImageAccessStatus.QUOTA_EXCEEDED:
        hours = int(IMAGE_QUOTA_WINDOW_SEC // 3600)
        if result.window_reset_sec is not None and result.window_reset_sec > 60:
            mins = int(result.window_reset_sec // 60)
            return (
                f"הגעת למכסת התמונות לחלון הנוכחי "
                f"({result.tier_limit} תמונות ל-{hours} שעות).\n"
                f"נסה/י שוב בעוד כ-{mins} דקות."
            )
        return (
            f"הגעת למכסת התמונות לחלון הנוכחי "
            f"({result.tier_limit} תמונות ל-{hours} שעות).\n"
            "נסה/י שוב מאוחר יותר."
        )
    return ""


def coupon_prompt_text_hebrew() -> str:
    return (
        "🎟️ *הזנת קוד קופון*\n\n"
        "שלח/י את הקוד בטקסט (8–16 תווים, אותיות ומספרים בלבד).\n"
        "כל קוד כולל מכסה יומית ותקופת מנוי (חודש או 3.5 חודשים).\n"
        "לאחר הפעלה תוכל/י לשלוח תמונות לפי המכסה.\n\n"
        "לבדיקת מכסה וטיימר: /quota"
    )


def _period_timer_line(result: ImageAccessResult) -> str:
    if result.period_expires_sec is None or result.period_expires_sec <= 0:
        return ""
    return (
        f"⏳ המנוי פעיל לעוד {_format_duration_hebrew(result.period_expires_sec)}."
    )


def quota_status_reply_hebrew(result: ImageAccessResult) -> str:
    hours = int(IMAGE_QUOTA_WINDOW_SEC // 3600)
    if result.status == ImageAccessStatus.ACCESS_EXPIRED:
        return (
            "⏱️ תקופת המנוי הסתיימה.\n"
            "הפעיל/י קוד קופון חדש או רכש/י חבילה — /coupon"
        )
    if result.status == ImageAccessStatus.TRIAL_EXHAUSTED:
        return (
            "אין כרגע גישה פתוחה לתמונות.\n"
            "אפשר להפעיל קוד קופון — /coupon"
        )
    if result.access_source in (AccessSource.GUEST, AccessSource.TRIAL):
        guest_mins = max(1, int(IMAGE_GUEST_COOLDOWN_SEC // 60)) if IMAGE_GUEST_COOLDOWN_SEC > 0 else 0
        if result.status == ImageAccessStatus.COOLDOWN:
            secs = result.cooldown_remaining_sec or 0.0
            left = max(1, int((secs + 59) // 60))
            return (
                f"📷 גישה חופשית לתמונות (בלי מכסה יומית).\n"
                f"המתנה בין תמונות: {guest_mins} דקות.\n"
                f"אפשר לשלוח תמונה נוספת בעוד כ-{left} דקות.\n"
                "למכסה מהירה יותר — הפעיל/י קוד קופון: /coupon"
            )
        return (
            f"📷 גישה חופשית לתמונות (בלי מכסה יומית).\n"
            f"המתנה בין תמונות: {guest_mins} דקות.\n"
            f"נשלחו עד כה {result.images_used} תמונות.\n"
            "למכסה מהירה יותר — הפעיל/י קוד קופון: /coupon"
        )
    if result.status == ImageAccessStatus.NO_ENTITLEMENT:
        return (
            "📷 גישה חופשית לתמונות (בלי מכסה יומית).\n"
            "שלח/י תמונה של תרגיל כדי להתחיל."
        )
    if result.status == ImageAccessStatus.QUOTA_EXCEEDED:
        reset_line = "המכסה היומית תתאפס בקרוב."
        if result.window_reset_sec is not None and result.window_reset_sec > 60:
            mins = int(result.window_reset_sec // 60)
            reset_line = f"המכסה היומית מתאפסת בעוד כ-{mins} דקות."
        period_line = _period_timer_line(result)
        lines = [
            f"מכסה יומית: {result.images_used}/{result.tier_limit} תמונות ל-{hours} שעות.",
            reset_line,
        ]
        if period_line:
            lines.append(period_line)
        lines.append("אפשר לשדרג עם קוד קופון נוסף — /coupon")
        return "\n".join(lines)
    lines = [
        f"✅ מנוי פעיל — נותרו {result.images_remaining} מתוך {result.tier_limit} "
        f"תמונות היום (חלון {hours} שעות).",
    ]
    period_line = _period_timer_line(result)
    if period_line:
        lines.append(period_line)
    if result.images_used == 0:
        lines.append("(החלון היומי יתחיל מהתמונה הראשונה שתשלח/י.)")
    return "\n".join(lines)
