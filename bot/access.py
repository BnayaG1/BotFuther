# -*- coding: utf-8 -*-
"""מצבי משתמש ומגבלות שימוש (SQLite)."""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from bot.config import (
    APP_DIR,
    FREE_TRIAL_IMAGES,
    IMAGE_COOLDOWN_SEC,
    IMAGE_GUEST_COOLDOWN_SEC,
    IMAGE_QUOTA_WINDOW_SEC,
)

log = logging.getLogger("beam_telegram_bot")

_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

DB_PATH = (APP_DIR / "access.db").resolve()

# חלון מועדף: 24 שעות מ־first_seen_at (/start ראשון).
FORMULAS_FREE_WINDOW_SEC = 24 * 3600
# המתנה מינימלית בין שימושים בפתרון (חשב) ובתרגול.
FEATURE_COOLDOWN_SEC = float(IMAGE_COOLDOWN_SEC) if IMAGE_COOLDOWN_SEC > 0 else 600.0
# אחרי חלון 24ש': פעם אחת לכל יכולת בחלון זה.
FEATURE_DAILY_LIMIT_SEC = 24 * 3600.0


class UserAccessPhase(Enum):
    """מצב הרשאות כללי של המשתמש."""

    PRIVILEGED = "privileged"  # 24ש' ראשונות
    RESTRICTED = "restricted"  # אחרי 24ש'


class FeatureKind(Enum):
    SOLVE = "solve"  # לחיצה על «חשב» בטיוטה
    PRACTICE = "practice"  # תרגול


class ImageAccessStatus(Enum):
    OK = "ok"
    NO_ENTITLEMENT = "no_entitlement"
    QUOTA_EXCEEDED = "quota_exceeded"
    TRIAL_EXHAUSTED = "trial_exhausted"
    ACCESS_EXPIRED = "access_expired"
    COOLDOWN = "cooldown"
    DAILY_LIMIT = "daily_limit"


class AccessSource(Enum):
    FREE_WINDOW = "free_window"
    RESTRICTED = "restricted"
    TRIAL = "trial"
    GUEST = "guest"


class RedeemStatus(Enum):
    OK = "ok"
    INVALID_CODE = "invalid_code"
    ALREADY_REDEEMED = "already_redeemed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class RedeemResult:
    status: RedeemStatus
    code: str
    period_days: int | None = None
    period_expires_at: float | None = None


@dataclass(frozen=True)
class ImageAccessResult:

    """תוצאת שער ליכולת (solve/practice)."""

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


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_bank_unlock (
            user_id INTEGER PRIMARY KEY,
            unlocked_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_first_seen (
            user_id INTEGER PRIMARY KEY,
            first_seen_at REAL NOT NULL,
            username TEXT
        );
        CREATE TABLE IF NOT EXISTS user_feature_usage (
            user_id INTEGER NOT NULL,
            feature TEXT NOT NULL,
            last_used_at REAL NOT NULL,
            PRIMARY KEY (user_id, feature)
        );
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY,
            daily_quota INTEGER NOT NULL,
            period_days INTEGER NOT NULL,
            created_at REAL NOT NULL,
            redeemed_by INTEGER,
            redeemed_at REAL,
            expires_at REAL
        );
        """
    )
    try:
        conn.execute("ALTER TABLE user_first_seen ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()



def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def init_access_db() -> None:
    _connect()


def close_access_db() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def access_status_summary() -> str:
    conn = _connect()
    with _db_lock:
        active_users = int(
            conn.execute("SELECT COUNT(*) FROM user_first_seen").fetchone()[0]
        )
    return f"pong | db={DB_PATH.name} | users={active_users}"


def ping_reply_hebrew() -> str:
    return "הבוט פעיל."


def user_has_bank_unlock(user_id: int) -> bool:
    conn = _connect()
    with _db_lock:
        row = conn.execute(
            "SELECT 1 FROM user_bank_unlock WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        return row is not None


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


def _ensure_user_first_seen_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float, username: str | None = None
) -> float:
    uid = int(user_id)
    clean_username = username.strip().lstrip("@") if username else None
    row = conn.execute(
        "SELECT first_seen_at, username FROM user_first_seen WHERE user_id = ?",
        (uid,),
    ).fetchone()
    if row is not None:
        if clean_username and row["username"] != clean_username:
            conn.execute(
                "UPDATE user_first_seen SET username = ? WHERE user_id = ?",
                (clean_username, uid),
            )
            conn.commit()
        return float(row["first_seen_at"])
    conn.execute(
        "INSERT INTO user_first_seen (user_id, first_seen_at, username) VALUES (?, ?, ?)",
        (uid, now, clean_username),
    )
    conn.commit()
    return float(now)



def _has_free_window_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> bool:
    first_seen = _ensure_user_first_seen_unlocked(conn, user_id, now)
    return (now - first_seen) < FORMULAS_FREE_WINDOW_SEC


VIP_UNLIMITED_DAILY_QUOTA = 999999


def _has_active_coupon_access_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> tuple[bool, float | None, int | None, bool]:
    row = conn.execute(
        "SELECT expires_at, period_days, daily_quota FROM coupons "
        "WHERE redeemed_by = ? AND expires_at > ? "
        "ORDER BY expires_at DESC LIMIT 1",
        (int(user_id), now),
    ).fetchone()
    if row is None or row["expires_at"] is None:
        return False, None, None, False
    is_vip = int(row["daily_quota"]) >= 999
    return True, float(row["expires_at"]), int(row["period_days"]), is_vip


def _phase_unlocked(
    conn: sqlite3.Connection, user_id: int, now: float
) -> tuple[UserAccessPhase, bool, bool]:
    has_coupon, _, _, is_vip = _has_active_coupon_access_unlocked(conn, int(user_id), now)
    if has_coupon or _has_free_window_unlocked(conn, int(user_id), now):
        return UserAccessPhase.PRIVILEGED, has_coupon, is_vip
    return UserAccessPhase.RESTRICTED, False, False


def get_user_access_phase(user_id: int, *, now: float | None = None) -> UserAccessPhase:
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        phase, _, _ = _phase_unlocked(conn, int(user_id), ts)
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
    feature: str,
    is_vip: bool = False,
) -> ImageAccessResult:
    base = dict(
        tier_limit=0,
        images_used=0,
        images_remaining=0,
        period_expires_sec=None,
        period_days=None,
        access_source=access_source,
        feature=feature,
        phase=phase,
    )
    if is_vip:
        return ImageAccessResult(status=ImageAccessStatus.OK, **base)

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
    key = _feature_key(feature)
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        phase, _, is_vip = _phase_unlocked(conn, int(user_id), ts)
        last_used = _load_feature_last_used_unlocked(conn, int(user_id), key)
        source = AccessSource.FREE_WINDOW if phase == UserAccessPhase.PRIVILEGED else AccessSource.RESTRICTED
        return _evaluate_feature_access(
            phase=phase,
            last_used_at=last_used,
            now=ts,
            access_source=source,
            feature=key,
            is_vip=is_vip,
        )


def consume_feature_slot(
    user_id: int,
    feature: FeatureKind | str,
    *,
    now: float | None = None,
) -> ImageAccessResult:
    key = _feature_key(feature)
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        phase, _, is_vip = _phase_unlocked(conn, int(user_id), ts)
        last_used = _load_feature_last_used_unlocked(conn, int(user_id), key)
        source = AccessSource.FREE_WINDOW if phase == UserAccessPhase.PRIVILEGED else AccessSource.RESTRICTED
        result = _evaluate_feature_access(
            phase=phase,
            last_used_at=last_used,
            now=ts,
            access_source=source,
            feature=key,
            is_vip=is_vip,
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
    return check_feature_access(user_id, FeatureKind.SOLVE)


def check_solve_access(user_id: int) -> ImageAccessResult:
    return check_feature_access(user_id, FeatureKind.SOLVE)


def check_practice_feature_access(user_id: int) -> ImageAccessResult:
    return check_feature_access(user_id, FeatureKind.PRACTICE)


def consume_image_slot(user_id: int) -> ImageAccessResult:
    return consume_feature_slot(user_id, FeatureKind.SOLVE)


def consume_solve_slot(user_id: int) -> ImageAccessResult:
    return consume_feature_slot(user_id, FeatureKind.SOLVE)


def consume_practice_slot(user_id: int) -> ImageAccessResult:
    return consume_feature_slot(user_id, FeatureKind.PRACTICE)


def ensure_user_first_seen(
    user_id: int, username: str | None = None, *, now: float | None = None
) -> float:
    conn = _connect()
    ts = time.time() if now is None else float(now)
    with _db_lock:
        return _ensure_user_first_seen_unlocked(conn, int(user_id), ts, username=username)


def list_users_first_seen() -> list[tuple[int, float, str | None]]:
    conn = _connect()
    with _db_lock:
        rows = conn.execute(
            "SELECT user_id, first_seen_at, username FROM user_first_seen "
            "ORDER BY first_seen_at ASC, user_id ASC"
        ).fetchall()
        return [
            (
                int(r["user_id"]),
                float(r["first_seen_at"]),
                r["username"] if "username" in r.keys() else None,
            )
            for r in rows
        ]


def get_user_info(user_id: int) -> dict | None:
    uid = int(user_id)
    conn = _connect()
    now = time.time()
    with _db_lock:
        row = conn.execute(
            "SELECT user_id, first_seen_at, username FROM user_first_seen WHERE user_id = ?",
            (uid,),
        ).fetchone()
        if row is None:
            return None
        first_seen = float(row["first_seen_at"])
        username = row["username"] if "username" in row.keys() else None

        coupon_row = conn.execute(
            "SELECT code, period_days, expires_at, daily_quota FROM coupons "
            "WHERE redeemed_by = ? AND expires_at > ? "
            "ORDER BY expires_at DESC LIMIT 1",
            (uid, now),
        ).fetchone()
        coupon_info = None
        if coupon_row:
            coupon_info = {
                "code": coupon_row["code"],
                "period_days": int(coupon_row["period_days"]),
                "expires_at": float(coupon_row["expires_at"]),
                "is_vip": int(coupon_row["daily_quota"]) >= 999,
            }
        bank_unlocked = conn.execute(
            "SELECT 1 FROM user_bank_unlock WHERE user_id = ?", (uid,)
        ).fetchone() is not None

        return {
            "user_id": uid,
            "first_seen_at": first_seen,
            "username": username,
            "active_coupon": coupon_info,
            "bank_unlocked": bank_unlocked,
        }



def has_formulas_free_window(user_id: int, *, now: float | None = None) -> bool:
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        return _has_free_window_unlocked(conn, int(user_id), ts)


def has_formulas_access(user_id: int) -> bool:
    return True


def has_practice_access(user_id: int) -> bool:
    return (
        check_feature_access(user_id, FeatureKind.PRACTICE).status
        == ImageAccessStatus.OK
    )


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
        ImageAccessStatus.ACCESS_EXPIRED,
        ImageAccessStatus.TRIAL_EXHAUSTED,
        ImageAccessStatus.NO_ENTITLEMENT,
    ):
        return "הגעת למגבלת השימוש היומית."
    return ""


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
    phase = result.phase or UserAccessPhase.RESTRICTED
    lines: list[str] = []
    if phase == UserAccessPhase.PRIVILEGED:
        lines.append("מצב: 24 השעות הראשונות (גישה חופשית).")
        lines.append("פתרון ותרגול: המתנה קצרה בין שימושים.")
    else:
        lines.append("מצב: גישה בסיסית.")
        lines.append("פתרון ותרגול: פעם אחת ביממה לכל יכולת, עם המתנה בין שימושים.")
    lines.append(_status_line_hebrew("פתרון", result))
    return "\n".join(lines)


def quota_status_for_user(user_id: int) -> str:
    solve = check_feature_access(user_id, FeatureKind.SOLVE)
    practice = check_feature_access(user_id, FeatureKind.PRACTICE)
    base_lines = quota_status_reply_hebrew(solve).split("\n")
    lines = [ln for ln in base_lines if not ln.startswith("פתרון:")]
    lines.append(_status_line_hebrew("פתרון", solve))
    lines.append(_status_line_hebrew("תרגול", practice))
    return "\n".join(lines)


def normalize_coupon_code(code: str) -> str:
    return code.strip().upper().replace(" ", "").replace("-", "")


def looks_like_coupon_code(text: str) -> bool:
    cleaned = normalize_coupon_code(text)
    return bool(cleaned and 6 <= len(cleaned) <= 24 and cleaned.isalnum())


def insert_coupon_codes(
    codes: list[str],
    daily_quota: int = 6,
    period_days: int = 30,
) -> None:
    conn = _connect()
    now = time.time()
    with _db_lock:
        for raw in codes:
            code = normalize_coupon_code(raw)
            if not code:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO coupons (code, daily_quota, period_days, created_at) VALUES (?, ?, ?, ?)",
                (code, int(daily_quota), int(period_days), now),
            )
        conn.commit()


def redeem_coupon(code_text: str, user_id: int, *, now: float | None = None) -> RedeemResult:
    ts = time.time() if now is None else float(now)
    code = normalize_coupon_code(code_text)
    if not code:
        return RedeemResult(status=RedeemStatus.INVALID_CODE, code=code_text)

    conn = _connect()
    with _db_lock:
        row = conn.execute(
            "SELECT code, daily_quota, period_days, redeemed_by, expires_at FROM coupons WHERE code = ?",
            (code,),
        ).fetchone()

        if row is None:
            return RedeemResult(status=RedeemStatus.INVALID_CODE, code=code)

        if row["redeemed_by"] is not None:
            return RedeemResult(status=RedeemStatus.ALREADY_REDEEMED, code=code)

        period_days = int(row["period_days"])
        daily_quota = int(row["daily_quota"])
        expires_at = ts + period_days * 86400.0

        conn.execute(
            "UPDATE coupons SET redeemed_by = ?, redeemed_at = ?, expires_at = ? WHERE code = ?",
            (int(user_id), ts, expires_at, code),
        )
        if daily_quota >= 999:
            conn.execute(
                "INSERT OR IGNORE INTO user_bank_unlock (user_id, unlocked_at) VALUES (?, ?)",
                (int(user_id), ts),
            )
        conn.commit()
        log.info("Coupon redeemed user=%s code=%s days=%s quota=%s", user_id, code, period_days, daily_quota)


        return RedeemResult(
            status=RedeemStatus.OK,
            code=code,
            period_days=period_days,
            period_expires_at=expires_at,
        )


def coupon_prompt_text_hebrew() -> str:
    return "שלח/י את קוד הקופון שקיבלת:"


def redeem_reply_hebrew(result: RedeemResult) -> str:
    if result.status == RedeemStatus.OK:
        days = result.period_days or 30
        if days == 30:
            period_str = "לחודש"
        elif days == 60:
            period_str = "לחודשיים"
        elif days == 90:
            period_str = "ל-3 חודשים"
        elif days == 120:
            period_str = "ל-4 חודשים"
        else:
            period_str = f"ל-{days} ימים"
        return f"קוד הקופון נקלט בהצלחה!\nקיבלת גישה מועדפת {period_str}."

    if result.status == RedeemStatus.ALREADY_REDEEMED:
        return "קוד הקופון הזה כבר נפדה בעבר."

    if result.status == RedeemStatus.EXPIRED:
        return "קוד הקופון פג תוקף."

    return "קוד הקופון לא תקין. ודא/י שהקלדת נכון."


def has_intro_access(user_id: int, *, now: float | None = None) -> bool:
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        has_coupon, _, _, is_vip = _has_active_coupon_access_unlocked(conn, int(user_id), ts)
        if has_coupon or is_vip or _has_free_window_unlocked(conn, int(user_id), ts):
            return True
        return False


def intro_access_blocked_hebrew() -> str:
    return (
        "הגישה לתכני הלימוד זמינה ב-24 השעות הראשונות או עם קוד קופון בתוקף.\n"
        "לרכישת חבילה/קופון לחץ/י על 'רכישת חבילה' בתפריט הראשי."
    )


