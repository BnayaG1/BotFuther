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
USERS_PAGE_SIZE = 6

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


def _fmt_ago(ts: float | None, now: float) -> str:
    if ts is None:
        return "אין פעילות"
    delta = max(0.0, now - float(ts))
    if delta < 60:
        return "עכשיו"
    if delta < 3600:
        return f"לפני {max(1, int(delta // 60))} דק׳"
    if delta < 86400:
        return f"לפני {max(1, int(delta // 3600))} שע׳"
    days = int(delta // 86400)
    if days == 1:
        return "אתמול"
    if days < 7:
        return f"לפני {days} ימים"
    return _fmt_when(ts, now)


def _fmt_left(sec: float) -> str:
    left = max(0.0, float(sec))
    if left <= 0:
        return "פג"
    if left < 3600:
        return f"עוד {max(1, int((left + 59) // 60))} דק׳"
    if left < 86400:
        return f"עוד {max(1, int((left + 3599) // 3600))} שע׳"
    days = int((left + 86399) // 86400)
    if days == 1:
        return "עוד יום"
    return f"עוד {days} ימים"


def _period_short(days: int) -> str:
    return {
        30: "חודש",
        60: "חודשיים",
        90: "3 חודשים",
        120: "4 חודשים",
    }.get(int(days), f"{int(days)} ימים")


def _active_coupon_join() -> str:
    return (
        "LEFT JOIN coupons c ON c.rowid = ("
        "SELECT c2.rowid FROM coupons c2 "
        "WHERE c2.redeemed_by = f.user_id AND c2.expires_at > ? "
        "ORDER BY c2.expires_at DESC LIMIT 1)"
    )


def _access_fields(first_seen: float, quota, expires_at, period_days, now: float) -> dict:
    if quota is not None and expires_at is not None:
        left = float(expires_at) - now
        is_vip = int(quota) >= 999
        if is_vip:
            return {
                "access_kind": "vip",
                "access_short": "VIP",
                "access_line": f"VIP · {_fmt_left(left)}",
            }
        period = _period_short(int(period_days or 0))
        return {
            "access_kind": "coupon",
            "access_short": period,
            "access_line": f"{period} · {_fmt_left(left)}",
        }
    window_left = FORMULAS_FREE_WINDOW_SEC - (now - first_seen)
    if window_left > 0:
        return {
            "access_kind": "window",
            "access_short": "חלון",
            "access_line": f"חלון חינם · {_fmt_left(window_left)}",
        }
    return {
        "access_kind": "none",
        "access_short": "בלי",
        "access_line": "בלי גישה",
    }


def _counts_for_users(conn, user_ids: list[int]) -> dict[int, dict[str, int]]:
    grouped: dict[int, dict[str, int]] = {uid: {} for uid in user_ids}
    if not user_ids:
        return grouped
    marks = ",".join("?" for _ in user_ids)
    rows = conn.execute(
        f"SELECT user_id, action, COUNT(*) AS n FROM admin_usage_event "
        f"WHERE user_id IN ({marks}) GROUP BY user_id, action",
        tuple(user_ids),
    ).fetchall()
    for row in rows:
        uid = int(row["user_id"])
        action = str(row["action"])
        if uid in grouped and action in USAGE_ACTION_SET and action != "main":
            grouped[uid][action] = int(row["n"])
    return grouped


def _top_usage(counts: dict[str, int], limit: int = 3) -> list[tuple[str, int]]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [(action, n) for action, n in ranked if n > 0][:limit]


def _users_summary_unlocked(conn, now: float) -> dict[str, int]:
    rows = conn.execute(
        "SELECT f.first_seen_at, c.daily_quota AS quota, c.expires_at, c.period_days "
        "FROM user_first_seen f "
        f"{_active_coupon_join()} "
        "WHERE f.user_id > 0",
        (now,),
    ).fetchall()
    summary = {"total": 0, "vip": 0, "coupon": 0, "window": 0, "none": 0}
    for row in rows:
        summary["total"] += 1
        kind = _access_fields(
            float(row["first_seen_at"]),
            row["quota"],
            row["expires_at"],
            row["period_days"],
            now,
        )["access_kind"]
        summary[kind] += 1
    return summary


def _row_dwell(row) -> float:
    if row["last_seen_at"] is None or row["session_started_at"] is None:
        return 0.0
    total = float(row["total_session_sec"] or 0.0)
    return total + max(0.0, float(row["last_seen_at"]) - float(row["session_started_at"]))


def list_users_page(
    *,
    offset: int = 0,
    limit: int = USERS_PAGE_SIZE,
    now: float | None = None,
) -> tuple[list[dict], int, dict[str, int]]:
    ts = _ts(now)
    off = max(0, int(offset))
    lim = max(1, int(limit))
    conn = _connect()
    with _db_lock:
        summary = _users_summary_unlocked(conn, ts)
        rows = conn.execute(
            "SELECT f.user_id, f.first_seen_at, f.username, "
            "s.last_seen_at, s.session_started_at, s.total_session_sec, "
            "c.daily_quota AS quota, c.expires_at, c.period_days "
            "FROM user_first_seen f "
            "LEFT JOIN admin_user_session s ON s.user_id = f.user_id "
            f"{_active_coupon_join()} "
            "WHERE f.user_id > 0 "
            "ORDER BY COALESCE(s.last_seen_at, 0) DESC, f.first_seen_at DESC, f.user_id DESC "
            "LIMIT ? OFFSET ?",
            (ts, lim, off),
        ).fetchall()
        ids = [int(row["user_id"]) for row in rows]
        counts = _counts_for_users(conn, ids)
        items = []
        for row in rows:
            uid = int(row["user_id"])
            first_seen = float(row["first_seen_at"])
            last_seen = float(row["last_seen_at"]) if row["last_seen_at"] is not None else None
            access = _access_fields(
                first_seen,
                row["quota"],
                row["expires_at"],
                row["period_days"],
                ts,
            )
            top = _top_usage(counts.get(uid, {}))
            items.append(
                {
                    "user_id": uid,
                    "username": row["username"],
                    "first_seen_at": first_seen,
                    "last_seen_at": last_seen,
                    "dwell_sec": _row_dwell(row),
                    "usage_line": " · ".join(
                        f"{ACTION_LABEL_HEBREW[action]} {n}" for action, n in top
                    ),
                    **access,
                }
            )
        return items, summary["total"], summary


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


def _session_count(user_id: int) -> int:
    conn = _connect()
    with _db_lock:
        closed = int(
            conn.execute(
                "SELECT COUNT(*) FROM admin_closed_session WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()[0]
        )
        open_row = conn.execute(
            "SELECT 1 FROM admin_user_session WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
    return closed + (1 if open_row is not None else 0)


def format_users_page_text(
    items: list[dict],
    total: int,
    offset: int,
    summary: dict | None = None,
    *,
    now: float | None = None,
) -> str:
    ts = _ts(now)
    counts = summary or {}
    lines = [
        "<b>משתמשים</b>",
        (
            f"{total} רשומים · "
            f"VIP {counts.get('vip', 0)} · "
            f"קופון {counts.get('coupon', 0)} · "
            f"חלון {counts.get('window', 0)} · "
            f"בלי {counts.get('none', 0)}"
        ),
    ]
    if items:
        lines.append(f"{offset + 1}–{offset + len(items)} מתוך {total}")
    if not items:
        lines.append("")
        lines.append("אין משתמשים במערכת.")
        return "\n".join(lines)
    lines.append("")
    for idx, item in enumerate(items, start=offset + 1):
        uname = item.get("username")
        name = f"@{uname}" if uname else str(item["user_id"])
        lines.append(f"<b>{idx}. {name}</b>")
        lines.append(item.get("access_line") or "בלי גישה")
        activity = _fmt_ago(item.get("last_seen_at"), ts) if item.get("last_seen_at") else "אין פעילות"
        detail = [activity]
        usage = (item.get("usage_line") or "").strip()
        if usage:
            detail.append(usage)
        dwell = float(item.get("dwell_sec") or 0)
        if dwell >= 60:
            detail.append(f"שהייה {_fmt_duration(dwell)}")
        lines.append(" · ".join(detail))
        lines.append("")
    return "\n".join(lines).strip()


def format_user_card_text(user_id: int, *, now: float | None = None) -> str | None:
    ts = _ts(now)
    info = get_user_info(int(user_id))
    if not info:
        return None
    uid = int(info["user_id"])
    uname = info.get("username")
    if uname:
        title = f"@{uname}"
        chat_link = f'<a href="https://t.me/{uname}">פתיחת שיחה</a>'
    else:
        title = str(uid)
        chat_link = f'<a href="tg://user?id={uid}">פתיחת שיחה</a>'

    coupon = info.get("active_coupon")
    access = _access_fields(
        float(info["first_seen_at"]),
        999999 if coupon and coupon.get("is_vip") else (1 if coupon else None),
        coupon["expires_at"] if coupon else None,
        coupon["period_days"] if coupon else None,
        ts,
    )
    if coupon:
        exp_dt = datetime.fromtimestamp(coupon["expires_at"], tz=_IL_TZ).strftime("%d/%m/%Y %H:%M")
        access_body = (
            f"{access['access_line']}\n"
            f"עד {exp_dt}\n"
            f"קוד <code>{coupon['code']}</code>"
        )
    else:
        access_body = access["access_line"]

    last_seen = user_last_seen(uid)
    if last_seen is None:
        seen_line = "אין פעילות"
    else:
        seen_line = f"{_fmt_ago(last_seen, ts)} · {_fmt_when(last_seen, ts)}"

    counts = user_action_counts(uid)
    ranked = sorted(
        ((action, n) for action, n in counts.items() if n > 0 and action != "main"),
        key=lambda item: (-item[1], item[0]),
    )
    if ranked:
        usage_block = "\n".join(
            f"{ACTION_LABEL_HEBREW[action]}  {n}" for action, n in ranked
        )
    else:
        usage_block = "עדיין לא נרשם שימוש"

    sessions = _session_count(uid)
    dwell = _fmt_duration(user_dwell_sec(uid, now=ts))
    bank = "פתוח" if info.get("bank_unlocked") else "סגור"

    return (
        f"<b>{title}</b>\n"
        f"{chat_link} · <code>{uid}</code>\n\n"
        f"<b>גישה</b>\n"
        f"{access_body}\n"
        f"מאגר תרגילים {bank}\n\n"
        f"<b>פעילות</b>\n"
        f"הצטרפות {_fmt_when(info['first_seen_at'], ts)}\n"
        f"נראה {seen_line}\n"
        f"שהייה {dwell} · {sessions} סשנים\n\n"
        f"<b>שימוש</b>\n"
        f"{usage_block}"
    )
