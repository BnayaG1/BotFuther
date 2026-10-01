# -*- coding: utf-8 -*-
"""רישום שימוש סגור ומדדי שהייה לפי סשן — למסך מנהל."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from bot.access import (
    FORMULAS_FREE_WINDOW_SEC,
    _connect,
    _db_lock,
    get_user_info,
)

log = logging.getLogger("beam_admin")

SESSION_GAP_SEC = 30 * 60
USERS_PAGE_SIZE = 8

USAGE_ACTIONS: tuple[str, ...] = (
    "main",
    "intro",
    "solve",
    "practice",
    "formulas",
    "cog",
    "buy",
    "bug",
    "coupon",
)
USAGE_ACTION_SET = frozenset(USAGE_ACTIONS)

ACTION_LABEL_HEBREW: dict[str, str] = {
    "main": "ראשי",
    "intro": "לימוד בסיס",
    "solve": "פתרון",
    "practice": "תרגול",
    "formulas": "נוסחאות",
    "cog": "מרכז כובד",
    "buy": "רכישה",
    "bug": "דיווח",
    "coupon": "מימוש קופון",
}

_IL_TZ = timezone(timedelta(hours=3))


def _ts(now: float | None) -> float:
    return time.time() if now is None else float(now)


def _touch_unlocked(conn, user_id: int, ts: float) -> None:
    uid = int(user_id)
    row = conn.execute(
        "SELECT session_started_at, last_seen_at, total_session_sec "
        "FROM admin_user_session WHERE user_id = ?",
        (uid,),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO admin_user_session "
            "(user_id, session_started_at, last_seen_at, total_session_sec) "
            "VALUES (?, ?, ?, 0)",
            (uid, ts, ts),
        )
        return
    started = float(row["session_started_at"])
    last_seen = float(row["last_seen_at"])
    total = float(row["total_session_sec"] or 0.0)
    if ts - last_seen > SESSION_GAP_SEC:
        duration = max(0.0, last_seen - started)
        conn.execute(
            "INSERT INTO admin_closed_session "
            "(user_id, started_at, ended_at, duration_sec) VALUES (?, ?, ?, ?)",
            (uid, started, last_seen, duration),
        )
        total += duration
        started = ts
    conn.execute(
        "UPDATE admin_user_session SET last_seen_at = ?, session_started_at = ?, "
        "total_session_sec = ? WHERE user_id = ?",
        (ts, started, total, uid),
    )


def touch_usage(user_id: int, *, now: float | None = None) -> None:
    """Heartbeat לסשן — בלי לספור לחיצה."""
    try:
        ts = _ts(now)
        conn = _connect()
        with _db_lock:
            _touch_unlocked(conn, int(user_id), ts)
            conn.commit()
    except Exception:
        log.debug("usage touch failed user=%s", user_id, exc_info=True)


def record_usage(user_id: int, action: str, *, now: float | None = None) -> None:
    """Heartbeat + אירוע פעולה אם היא ברשימה הסגורה."""
    try:
        key = str(action).strip().lower()
        ts = _ts(now)
        conn = _connect()
        with _db_lock:
            _touch_unlocked(conn, int(user_id), ts)
            if key in USAGE_ACTION_SET:
                conn.execute(
                    "INSERT INTO admin_usage_event (user_id, ts, action) VALUES (?, ?, ?)",
                    (int(user_id), ts, key),
                )
            conn.commit()
    except Exception:
        log.debug("usage record failed user=%s action=%s", user_id, action, exc_info=True)


def _window_starts(now: float) -> tuple[float, float]:
    local = datetime.fromtimestamp(now, tz=_IL_TZ)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    week_start = day_start - 6 * 86400.0
    return day_start, week_start


def _count_new_users(conn, start: float, end: float) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM user_first_seen WHERE user_id > 0 AND first_seen_at >= ? AND first_seen_at < ?",
        (start, end),
    ).fetchone()
    return int(row[0] if row else 0)


def _count_active_users(conn, start: float, end: float) -> int:
    row = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM admin_usage_event WHERE ts >= ? AND ts < ?",
        (start, end),
    ).fetchone()
    return int(row[0] if row else 0)


def _action_counts(conn, start: float, end: float) -> dict[str, int]:
    counts = {key: 0 for key in USAGE_ACTIONS}
    rows = conn.execute(
        "SELECT action, COUNT(*) AS n FROM admin_usage_event "
        "WHERE ts >= ? AND ts < ? GROUP BY action",
        (start, end),
    ).fetchall()
    for row in rows:
        action = str(row["action"])
        if action in counts:
            counts[action] = int(row["n"])
    return counts


def _session_stats(conn, start: float, end: float) -> tuple[int, float]:
    closed = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(duration_sec), 0) AS dur "
        "FROM admin_closed_session "
        "WHERE ended_at >= ? AND started_at < ?",
        (start, end),
    ).fetchone()
    n = int(closed["n"] if closed else 0)
    dur = float(closed["dur"] if closed else 0.0)
    open_rows = conn.execute(
        "SELECT session_started_at, last_seen_at FROM admin_user_session "
        "WHERE last_seen_at >= ? AND session_started_at < ?",
        (start, end),
    ).fetchall()
    for row in open_rows:
        started = float(row["session_started_at"])
        last_seen = float(row["last_seen_at"])
        n += 1
        dur += max(0.0, last_seen - started)
    return n, dur


def overview_stats(*, now: float | None = None) -> dict:
    ts = _ts(now)
    day_start, week_start = _window_starts(ts)
    conn = _connect()
    with _db_lock:
        return {
            "now": ts,
            "day": _window_bundle(conn, day_start, ts),
            "week": _window_bundle(conn, week_start, ts),
        }


def _window_bundle(conn, start: float, end: float) -> dict:
    sessions, dwell = _session_stats(conn, start, end)
    avg = (dwell / sessions) if sessions else 0.0
    return {
        "start": start,
        "end": end,
        "active_users": _count_active_users(conn, start, end),
        "new_users": _count_new_users(conn, start, end),
        "sessions": sessions,
        "avg_dwell_sec": avg,
        "actions": _action_counts(conn, start, end),
    }


def _fmt_duration(sec: float) -> str:
    total = max(0, int(round(float(sec))))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours} ש׳ {minutes} דק׳"
    if minutes:
        return f"{minutes} דק׳"
    return f"{seconds} שנ׳"


def _fmt_when(ts: float | None, now: float) -> str:
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(float(ts), tz=_IL_TZ)
    return dt.strftime("%d/%m/%Y %H:%M")


def format_overview_text(stats: dict | None = None, *, now: float | None = None) -> str:
    data = stats if stats is not None else overview_stats(now=now)

    def block(title: str, bundle: dict) -> str:
        ranked = sorted(
            bundle["actions"].items(),
            key=lambda item: (-item[1], USAGE_ACTIONS.index(item[0]) if item[0] in USAGE_ACTION_SET else 99),
        )
        lines = [f"<b>{title}</b>"]
        lines.append(f"• פעילים: <b>{bundle['active_users']}</b>")
        lines.append(f"• חדשים: <b>{bundle['new_users']}</b>")
        lines.append(
            f"• סשנים: <b>{bundle['sessions']}</b> · ממוצע שהייה: <b>{_fmt_duration(bundle['avg_dwell_sec'])}</b>"
        )
        lines.append("• שימוש:")
        for action, count in ranked:
            if count <= 0:
                continue
            lines.append(f"   {ACTION_LABEL_HEBREW.get(action, action)} — {count}")
        if not any(count > 0 for count in bundle["actions"].values()):
            lines.append("   אין עדיין")
        return "\n".join(lines)

    return (
        "<b>סקירה</b>\n\n"
        f"{block('היום', data['day'])}\n\n"
        f"{block('7 ימים', data['week'])}"
    )


def _coupon_user_ids_unlocked(conn, now: float) -> set[int]:
    rows = conn.execute(
        "SELECT DISTINCT redeemed_by FROM coupons "
        "WHERE redeemed_by IS NOT NULL AND expires_at > ?",
        (now,),
    ).fetchall()
    return {int(r["redeemed_by"]) for r in rows if r["redeemed_by"] is not None}


def _status_label(uid: int, first_seen: float, coupon_ids: set[int], now: float) -> str:
    if uid in coupon_ids:
        return "קופון"
    if (now - first_seen) < FORMULAS_FREE_WINDOW_SEC:
        return "חלון חינם"
    return "בלי"


def list_users_page(
    *,
    offset: int = 0,
    limit: int = USERS_PAGE_SIZE,
    now: float | None = None,
) -> tuple[list[dict], int]:
    ts = _ts(now)
    off = max(0, int(offset))
    lim = max(1, int(limit))
    conn = _connect()
    with _db_lock:
        total = int(
            conn.execute(
                "SELECT COUNT(*) FROM user_first_seen WHERE user_id > 0"
            ).fetchone()[0]
        )
        coupon_ids = _coupon_user_ids_unlocked(conn, ts)
        rows = conn.execute(
            "SELECT f.user_id, f.first_seen_at, f.username, s.last_seen_at "
            "FROM user_first_seen f "
            "LEFT JOIN admin_user_session s ON s.user_id = f.user_id "
            "WHERE f.user_id > 0 "
            "ORDER BY COALESCE(s.last_seen_at, f.first_seen_at) DESC, f.user_id DESC "
            "LIMIT ? OFFSET ?",
            (lim, off),
        ).fetchall()
        items = []
        for row in rows:
            uid = int(row["user_id"])
            first_seen = float(row["first_seen_at"])
            last_seen = float(row["last_seen_at"]) if row["last_seen_at"] is not None else None
            items.append(
                {
                    "user_id": uid,
                    "username": row["username"],
                    "first_seen_at": first_seen,
                    "last_seen_at": last_seen,
                    "status": _status_label(uid, first_seen, coupon_ids, ts),
                }
            )
        return items, total


def user_dwell_sec(user_id: int, *, now: float | None = None) -> float:
    conn = _connect()
    with _db_lock:
        row = conn.execute(
            "SELECT session_started_at, last_seen_at, total_session_sec "
            "FROM admin_user_session WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        if row is None:
            return 0.0
        started = float(row["session_started_at"])
        last_seen = float(row["last_seen_at"])
        total = float(row["total_session_sec"] or 0.0)
        return total + max(0.0, last_seen - started)


def user_action_counts(user_id: int) -> dict[str, int]:
    counts = {key: 0 for key in USAGE_ACTIONS}
    conn = _connect()
    with _db_lock:
        rows = conn.execute(
            "SELECT action, COUNT(*) AS n FROM admin_usage_event "
            "WHERE user_id = ? GROUP BY action",
            (int(user_id),),
        ).fetchall()
    for row in rows:
        action = str(row["action"])
        if action in counts:
            counts[action] = int(row["n"])
    return counts


def user_last_seen(user_id: int) -> float | None:
    conn = _connect()
    with _db_lock:
        row = conn.execute(
            "SELECT last_seen_at FROM admin_user_session WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        if row is None or row["last_seen_at"] is None:
            return None
        return float(row["last_seen_at"])


def format_users_page_text(items: list[dict], total: int, offset: int, *, now: float | None = None) -> str:
    ts = _ts(now)
    lines = [f"<b>משתמשים</b> (סה״כ: {total})"]
    if not items:
        lines.append("אין משתמשים במערכת.")
        return "\n".join(lines)
    for idx, item in enumerate(items, start=offset + 1):
        uname = item.get("username")
        name = f"@{uname}" if uname else str(item["user_id"])
        seen = item.get("last_seen_at") or item.get("first_seen_at")
        lines.append(
            f"{idx}. {name} · {_fmt_when(seen, ts)} · {item.get('status') or 'בלי'}"
        )
    return "\n".join(lines)


def format_user_card_text(user_id: int, *, now: float | None = None) -> str | None:
    ts = _ts(now)
    info = get_user_info(int(user_id))
    if not info:
        return None
    uid = int(info["user_id"])
    uname = info.get("username")
    if uname:
        chat_link = f'<a href="https://t.me/{uname}">@{uname}</a>'
    else:
        chat_link = f'<a href="tg://user?id={uid}">פרופיל ({uid})</a>'

    coupon_str = "אין קופון פעיל"
    if info.get("active_coupon"):
        cp = info["active_coupon"]
        exp_dt = datetime.fromtimestamp(cp["expires_at"], tz=_IL_TZ).strftime("%d/%m/%Y %H:%M")
        vip_tag = " [VIP]" if cp.get("is_vip") else ""
        coupon_str = (
            f"<code>{cp['code']}</code> ({cp['period_days']} ימים){vip_tag} — עד {exp_dt}"
        )

    last_seen = user_last_seen(uid)
    counts = user_action_counts(uid)
    usage_lines = []
    for action in USAGE_ACTIONS:
        n = counts.get(action, 0)
        if n:
            usage_lines.append(f"   {ACTION_LABEL_HEBREW[action]} — {n}")
    usage_block = "\n".join(usage_lines) if usage_lines else "   אין עדיין"

    return (
        f"<b>משתמש {uid}</b>\n\n"
        f"• שיחה: {chat_link}\n"
        f"• הצטרפות: {_fmt_when(info['first_seen_at'], ts)}\n"
        f"• נראה לאחרונה: {_fmt_when(last_seen or info['first_seen_at'], ts)}\n"
        f"• שהייה: {_fmt_duration(user_dwell_sec(uid, now=ts))}\n"
        f"• קופון: {coupon_str}\n"
        f"• מאגר תרגילים: {'פתוח' if info.get('bank_unlocked') else 'סגור'}\n"
        f"• שימוש:\n{usage_block}"
    )
