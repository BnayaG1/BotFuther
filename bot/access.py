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

import os

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

_raw_access_db = (
    os.getenv("ACCESS_DB_PATH", "").strip()
    or os.getenv("COUPON_DB_PATH", "").strip()
    or os.getenv("DB_PATH", "").strip()
)
DB_PATH = Path(_raw_access_db).resolve() if _raw_access_db else (APP_DIR / "access.db").resolve()

# חלון 24 השעות הישן — נשאר רק לתצוגת has_formulas_free_window; לא משפיע על הרשאות.
FORMULAS_FREE_WINDOW_SEC = 24 * 3600
# המתנה מינימלית בין שימושים בפתרון ובמדריך לפתרון (לכולם, חוץ מ-VIP).
FEATURE_COOLDOWN_SEC = float(IMAGE_COOLDOWN_SEC) if IMAGE_COOLDOWN_SEC > 0 else 600.0
# מכסה חינמית לכל החיים: הגעה לגבול באחד המונים נועלת גם פתרון וגם מדריך.
FREE_SOLUTIONS_LIMIT = 6


class UserAccessPhase(Enum):
    """מצב הרשאות כללי של המשתמש."""

    PRIVILEGED = "privileged"  # קופון בתוקף
    RESTRICTED = "restricted"  # חינמי (מכסה של FREE_SOLUTIONS_LIMIT)


class FeatureKind(Enum):
    SOLVE = "solve"  # קבלת פתרון מלא
    GUIDE = "guide"  # לחיצה על «מדריך לפתרון»
    PRACTICE = "practice"  # תרגול — חופשי תמיד


class ImageAccessStatus(Enum):
    OK = "ok"
    NO_ENTITLEMENT = "no_entitlement"
    QUOTA_EXCEEDED = "quota_exceeded"
    TRIAL_EXHAUSTED = "trial_exhausted"
    ACCESS_EXPIRED = "access_expired"
    COOLDOWN = "cooldown"
    DAILY_LIMIT = "daily_limit"
    FREE_LIMIT_REACHED = "free_limit_reached"


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
    free_solves_used: int = 0
    free_guides_used: int = 0


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
        CREATE TABLE IF NOT EXISTS user_free_usage (
            user_id INTEGER PRIMARY KEY,
            solves_used INTEGER NOT NULL DEFAULT 0,
            guides_used INTEGER NOT NULL DEFAULT 0
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
        CREATE TABLE IF NOT EXISTS admin_usage_event (
            user_id INTEGER NOT NULL,
            ts REAL NOT NULL,
            action TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_usage_event_ts
            ON admin_usage_event (ts);
        CREATE INDEX IF NOT EXISTS idx_admin_usage_event_user_ts
            ON admin_usage_event (user_id, ts);
        CREATE INDEX IF NOT EXISTS idx_admin_usage_event_action_ts
            ON admin_usage_event (action, ts);
        CREATE TABLE IF NOT EXISTS admin_user_session (
            user_id INTEGER PRIMARY KEY,
            session_started_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            total_session_sec REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS admin_closed_session (
            user_id INTEGER NOT NULL,
            started_at REAL NOT NULL,
            ended_at REAL NOT NULL,
            duration_sec REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_closed_session_ended
            ON admin_closed_session (ended_at);
        CREATE INDEX IF NOT EXISTS idx_admin_closed_session_started
            ON admin_closed_session (started_at);
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
    clean_username = username.strip().lstrip("@") if isinstance(username, str) and username.strip() else None
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
    if has_coupon:
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
    if key in {kind.value for kind in FeatureKind}:
        return key
    raise ValueError(f"unknown feature: {feature!r}")


_FREE_USAGE_COLUMN = {
    FeatureKind.SOLVE.value: "solves_used",
    FeatureKind.GUIDE.value: "guides_used",
}


def _load_free_usage_unlocked(conn: sqlite3.Connection, user_id: int) -> tuple[int, int]:
    row = conn.execute(
        "SELECT solves_used, guides_used FROM user_free_usage WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return 0, 0
    return int(row["solves_used"]), int(row["guides_used"])


def _increment_free_usage_unlocked(conn: sqlite3.Connection, user_id: int, feature: str) -> None:
    column = _FREE_USAGE_COLUMN[feature]
    conn.execute(
        "INSERT INTO user_free_usage (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
        (int(user_id),),
    )
    conn.execute(
        f"UPDATE user_free_usage SET {column} = {column} + 1 WHERE user_id = ?",
        (int(user_id),),
    )


def free_limit_reached(solves_used: int, guides_used: int) -> bool:
    return max(int(solves_used), int(guides_used)) >= FREE_SOLUTIONS_LIMIT


def get_free_usage(user_id: int) -> tuple[int, int]:
    """(פתרונות, מדריכים) שנוצלו במכסה החינמית."""
    conn = _connect()
    with _db_lock:
        return _load_free_usage_unlocked(conn, int(user_id))


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
    solves_used: int = 0,
    guides_used: int = 0,
) -> ImageAccessResult:
    base = dict(
        tier_limit=FREE_SOLUTIONS_LIMIT,
        images_used=0,
        images_remaining=0,
        period_expires_sec=None,
        period_days=None,
        access_source=access_source,
        feature=feature,
        phase=phase,
        free_solves_used=int(solves_used),
        free_guides_used=int(guides_used),
    )
    if feature == FeatureKind.PRACTICE.value or is_vip:
        return ImageAccessResult(status=ImageAccessStatus.OK, **base)

    if phase == UserAccessPhase.RESTRICTED and free_limit_reached(solves_used, guides_used):
        return ImageAccessResult(status=ImageAccessStatus.FREE_LIMIT_REACHED, **base)

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
        return _evaluate_feature_access_unlocked(conn, int(user_id), key, ts)


def _evaluate_feature_access_unlocked(
    conn: sqlite3.Connection, user_id: int, key: str, now: float
) -> ImageAccessResult:
    phase, _, is_vip = _phase_unlocked(conn, int(user_id), now)
    last_used = _load_feature_last_used_unlocked(conn, int(user_id), key)
    solves_used, guides_used = _load_free_usage_unlocked(conn, int(user_id))
    source = AccessSource.FREE_WINDOW if phase == UserAccessPhase.PRIVILEGED else AccessSource.RESTRICTED
    return _evaluate_feature_access(
        phase=phase,
        last_used_at=last_used,
        now=now,
        access_source=source,
        feature=key,
        is_vip=is_vip,
        solves_used=solves_used,
        guides_used=guides_used,
    )


def consume_feature_slot(
    user_id: int,
    feature: FeatureKind | str,
    *,
    now: float | None = None,
) -> ImageAccessResult:
    """בודק ורושם שימוש בפעולה אטומית אחת — מונע ספירה כפולה בלחיצות מקבילות."""
    key = _feature_key(feature)
    ts = time.time() if now is None else float(now)
    conn = _connect()
    with _db_lock:
        result = _evaluate_feature_access_unlocked(conn, int(user_id), key, ts)
        if result.status != ImageAccessStatus.OK or key == FeatureKind.PRACTICE.value:
            return result
        conn.execute(
            "INSERT INTO user_feature_usage (user_id, feature, last_used_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, feature) DO UPDATE SET last_used_at = excluded.last_used_at",
            (int(user_id), key, ts),
        )
        if result.phase == UserAccessPhase.RESTRICTED:
            _increment_free_usage_unlocked(conn, int(user_id), key)
        conn.commit()
        log.info(
            "Feature slot user=%s feature=%s phase=%s",
            user_id,
            key,
            result.phase.value if result.phase else None,
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


def check_guide_access(user_id: int) -> ImageAccessResult:
    return check_feature_access(user_id, FeatureKind.GUIDE)


def check_solution_entry_access(user_id: int) -> ImageAccessResult:
    """שער לפני חילוץ/חישוב תרגיל: מותר אם פתרון או מדריך זמינים (הספירה נעשית במסירה)."""
    solve = check_feature_access(user_id, FeatureKind.SOLVE)
    if solve.status == ImageAccessStatus.OK:
        return solve
    guide = check_feature_access(user_id, FeatureKind.GUIDE)
    if guide.status == ImageAccessStatus.OK:
        return guide
    if solve.status == guide.status == ImageAccessStatus.COOLDOWN:
        return min(solve, guide, key=lambda res: res.cooldown_remaining_sec or 0.0)
    return solve if solve.status != ImageAccessStatus.COOLDOWN else guide


def consume_guide_slot(user_id: int) -> ImageAccessResult:
    return consume_feature_slot(user_id, FeatureKind.GUIDE)


def is_user_first_seen(user_id: int) -> bool:
    """מחזיר True אם המשתמש כבר נרשם בעבר ב-user_first_seen."""
    conn = _connect()
    with _db_lock:
        row = conn.execute(
            "SELECT 1 FROM user_first_seen WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        return row is not None


def ensure_user_first_seen(
    user_id: int, username: str | None = None, *, now: float | None = None
) -> float:
    conn = _connect()
    ts = time.time() if now is None else float(now)
    with _db_lock:
        return _ensure_user_first_seen_unlocked(conn, int(user_id), ts, username=username)


def list_users_first_seen(*, exclude_admin_ids: set[int] | frozenset[int] | None = None) -> list[tuple[int, float, str | None]]:
    conn = _connect()
    with _db_lock:
        rows = conn.execute(
            "SELECT user_id, first_seen_at, username FROM user_first_seen "
            "WHERE user_id > 0 "
            "ORDER BY first_seen_at ASC, user_id ASC"
        ).fetchall()
        admins = set(exclude_admin_ids) if exclude_admin_ids else set()
        return [
            (
                int(r["user_id"]),
                float(r["first_seen_at"]),
                r["username"] if "username" in r.keys() else None,
            )
            for r in rows
            if int(r["user_id"]) not in admins
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
        solves_used, guides_used = _load_free_usage_unlocked(conn, uid)

        return {
            "user_id": uid,
            "first_seen_at": first_seen,
            "username": username,
            "active_coupon": coupon_info,
            "bank_unlocked": bank_unlocked,
            "free_solves_used": solves_used,
            "free_guides_used": guides_used,
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
    if feature == FeatureKind.GUIDE.value:
        return "מדריך לפתרון"
    return "פתרון"


def _cooldown_wait_label_hebrew() -> str:
    wait_mins = max(1, int(FEATURE_COOLDOWN_SEC // 60)) if FEATURE_COOLDOWN_SEC > 0 else 0
    return f"{wait_mins} דקות" if wait_mins > 0 else "כמה רגעים"


def free_limit_reached_reply_hebrew() -> str:
    return (
        f"ניצלת את המכסה החינמית: {FREE_SOLUTIONS_LIMIT} פתרונות "
        f"או {FREE_SOLUTIONS_LIMIT} מדריכים לפתרון.\n"
        "כדי לקבל גישה חופשית לפתרונות ולמדריך לפתרון, יש לרכוש אחת משתי החבילות.\n"
        "תרגילים ולימוד בסיס נשארים פתוחים בחינם."
    )


def image_access_reply_hebrew(result: ImageAccessResult) -> str:
    if result.status == ImageAccessStatus.OK:
        return ""
    if result.status == ImageAccessStatus.COOLDOWN:
        label = _feature_label_hebrew(result.feature)
        secs = result.cooldown_remaining_sec or 0.0
        mins = max(1, int((secs + 59) // 60))
        return (
            f"אפשר להשתמש ב«{label}» שוב בעוד כ-{mins} דקות "
            f"(המתנה של {_cooldown_wait_label_hebrew()} בין שימושים)."
        )
    return free_limit_reached_reply_hebrew()


def _status_line_hebrew(label: str, res: ImageAccessResult) -> str:
    if res.status == ImageAccessStatus.COOLDOWN:
        secs = res.cooldown_remaining_sec or 0.0
        mins = max(1, int((secs + 59) // 60))
        return f"{label}: זמין שוב בעוד כ-{mins} דקות."
    if res.status == ImageAccessStatus.OK:
        return f"{label}: זמין עכשיו."
    return f"{label}: נעול — נדרשת חבילה."


def _days_left_hebrew(expires_at: float, now: float) -> str:
    days = max(1, int((float(expires_at) - now + 86399) // 86400))
    return "יום אחד" if days == 1 else f"{days} ימים"


def quota_status_for_user(user_id: int) -> str:
    uid = int(user_id)
    ts = time.time()
    conn = _connect()
    with _db_lock:
        has_coupon, expires_at, _, is_vip = _has_active_coupon_access_unlocked(conn, uid, ts)
    solve = check_feature_access(uid, FeatureKind.SOLVE, now=ts)
    guide = check_feature_access(uid, FeatureKind.GUIDE, now=ts)

    lines: list[str] = []
    if is_vip and expires_at is not None:
        lines.append(f"מצב: VIP — ללא הגבלה (נותרו {_days_left_hebrew(expires_at, ts)}).")
    elif has_coupon and expires_at is not None:
        lines.append(f"מצב: חבילה בתוקף (נותרו {_days_left_hebrew(expires_at, ts)}).")
        lines.append(
            f"פתרון ומדריך לפתרון: ללא הגבלת כמות, "
            f"המתנה של {_cooldown_wait_label_hebrew()} בין שימושים."
        )
    else:
        lines.append("מצב: גישה חינמית.")
        lines.append(
            f"פתרונות שקיבלת: {min(solve.free_solves_used, FREE_SOLUTIONS_LIMIT)} "
            f"מתוך {FREE_SOLUTIONS_LIMIT}."
        )
        lines.append(
            f"מדריכים לפתרון: {min(solve.free_guides_used, FREE_SOLUTIONS_LIMIT)} "
            f"מתוך {FREE_SOLUTIONS_LIMIT}."
        )
        lines.append(
            f"כשאחד מהם מגיע ל-{FREE_SOLUTIONS_LIMIT}, הפתרון והמדריך ננעלים עד רכישת חבילה."
        )
    lines.append(_status_line_hebrew("פתרון", solve))
    lines.append(_status_line_hebrew("מדריך לפתרון", guide))
    lines.append("תרגול ולימוד בסיס: פתוחים תמיד.")
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
        elif days == 105:
            period_str = "ל-3.5 חודשים"
        elif days == 120:
            period_str = "ל-4 חודשים"
        else:
            period_str = f"ל-{days} ימים"
        return (
            "קוד הקופון נקלט בהצלחה!\n"
            f"קיבלת גישה חופשית לפתרונות ולמדריך לפתרון {period_str}."
        )

    if result.status == RedeemStatus.ALREADY_REDEEMED:
        return "קוד הקופון הזה כבר נפדה בעבר."

    if result.status == RedeemStatus.EXPIRED:
        return "קוד הקופון פג תוקף."

    return "קוד הקופון לא תקין. ודא/י שהקלדת נכון."


def has_intro_access(user_id: int, *, now: float | None = None) -> bool:
    """לימוד בסיס פתוח לכולם תמיד."""
    return True


def intro_access_blocked_hebrew() -> str:
    return free_limit_reached_reply_hebrew()


