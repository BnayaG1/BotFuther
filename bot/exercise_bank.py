# -*- coding: utf-8 -*-
"""מאגר תרגילים מוכנים (SQLite) — שמירה ואחזור של תרגילים שאושרו לצורך שימוש חוזר."""
from __future__ import annotations

import json
import logging
import random
import shutil
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from telegram.error import BadRequest

from bot.config import (
    EXERCISE_BANK_COOLDOWN_SEC,
    EXERCISE_BANK_DB_PATH,
    EXERCISE_BANK_IMAGES_DIR,
)
from bot.draft_session import set_draft_error_message_id

log = logging.getLogger("beam_telegram_bot")

SendTextFn = Callable[..., Awaitable[object]]
EditDraftFn = Callable[..., Awaitable[None]]

_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracted_json TEXT NOT NULL,
            beam_kind TEXT NOT NULL DEFAULT 'unknown',
            added_by_user_id INTEGER,
            created_at REAL NOT NULL,
            image_path TEXT
        );
        CREATE TABLE IF NOT EXISTS user_exercise_sent (
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            sent_at REAL NOT NULL,
            PRIMARY KEY (user_id, exercise_id)
        );
        """
    )
    _ensure_image_path_column(conn)
    conn.commit()


def _ensure_image_path_column(conn: sqlite3.Connection) -> None:
    """מיגרציה רכה ל-DB קיים שנבנה לפני עמודת image_path."""
    cols = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(exercises)").fetchall()
    }
    if "image_path" not in cols:
        conn.execute("ALTER TABLE exercises ADD COLUMN image_path TEXT")


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = Path(EXERCISE_BANK_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def init_exercise_bank_db() -> None:
    """אתחול DB בהפעלת הבוט — מבטיח שהטבלה קיימת."""
    _connect()
    ensure_exercise_bank_images_dir()


def close_exercise_bank_db() -> None:
    """סגירת חיבור DB — לשימוש בטסטים בלבד."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def ensure_exercise_bank_images_dir() -> Path:
    EXERCISE_BANK_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return EXERCISE_BANK_IMAGES_DIR


_DUP_ROUND_DECIMALS = 2


def _dup_round(value: object) -> float:
    try:
        return round(float(value or 0.0), _DUP_ROUND_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _canonical_load_signature(load: dict) -> tuple:
    """מייצג עומס בודד להשוואת כפילויות — מתעלם ממפתחות עריכה פנימיים (_draft_new וכו')."""
    t = str(load.get("type", "point")).lower().strip()
    if t == "moment":
        return ("moment", _dup_round(load.get("x")), _dup_round(load.get("M", load.get("m"))))
    if t == "distributed":
        x1 = _dup_round(load.get("x1", load.get("start_x")))
        x2 = _dup_round(load.get("x2", load.get("end_x")))
        lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
        w = _dup_round(load.get("w", load.get("q", load.get("magnitude"))))
        shape = str(load.get("shape", "rectangular")).lower().strip()
        return ("distributed", lo, hi, w, shape)
    # point (כולל עומס צירי — Fx בלבד) ו-inclined — הכיוון וההיטלים כבר בתוך Fx/Fy.
    return (
        "point",
        _dup_round(load.get("x")),
        _dup_round(load.get("Fx", load.get("fx"))),
        _dup_round(load.get("Fy", load.get("fy"))),
    )


def _canonical_support_signature(support: dict) -> tuple:
    return (
        str(support.get("type", "")).lower().strip(),
        _dup_round(support.get("x")),
    )


def canonicalize_exercise_signature(extracted: dict) -> tuple:
    """מייצג תרגיל (גיאומטריה + עומסים) כמבנה השוואתי, בלי תלות בסדר החילוץ
    או במטא-דאטה (notes/confidence/uncertainties וכו') — לזיהוי כפילויות במאגר.
    """
    beam = extracted.get("beam") if isinstance(extracted, dict) else {}
    if not isinstance(beam, dict):
        beam = {}
    support_mode = str(beam.get("support_mode", "simply_supported")).lower().strip()
    length = _dup_round(beam.get("L"))
    supports = tuple(
        sorted(
            _canonical_support_signature(s)
            for s in (beam.get("supports") or [])
            if isinstance(s, dict)
        )
    )
    loads = tuple(
        sorted(
            _canonical_load_signature(ld)
            for ld in (beam.get("loads") or [])
            if isinstance(ld, dict)
        )
    )
    hinges = tuple(
        sorted(
            _dup_round(h.get("x"))
            for h in (beam.get("internal_hinges") or [])
            if isinstance(h, dict)
        )
    )
    return (support_mode, length, supports, loads, hinges)


def find_duplicate_exercise(extracted: dict) -> int | None:
    """מחזיר מזהה תרגיל קיים במאגר עם נתונים זהים (גיאומטריה+עומסים), אם יש כזה."""
    target = canonicalize_exercise_signature(extracted)
    with _db_lock:
        conn = _connect()
        rows = conn.execute("SELECT id, extracted_json FROM exercises").fetchall()
    for row in rows:
        try:
            existing = json.loads(row["extracted_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if canonicalize_exercise_signature(existing) == target:
            return int(row["id"])
    return None


def _store_exercise_image(exercise_id: int, image_source: Path) -> str | None:
    """מעתיק תמונת מקור לתיקיית המאגר. מחזיר שם קובץ יחסי, או None בכישלון."""
    source = Path(image_source)
    if not source.is_file():
        log.warning(
            "Exercise bank image missing for id=%s path=%s",
            exercise_id,
            source,
        )
        return None
    ensure_exercise_bank_images_dir()
    suffix = source.suffix.lower() if source.suffix else ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    filename = f"{int(exercise_id)}{suffix}"
    dest = EXERCISE_BANK_IMAGES_DIR / filename
    try:
        shutil.copy2(source, dest)
    except OSError as exc:
        log.warning(
            "Failed to copy exercise bank image id=%s from %s: %s",
            exercise_id,
            source,
            exc,
        )
        return None
    return filename


def add_exercise(
    extracted: dict,
    *,
    added_by_user_id: int | None = None,
    image_source: Path | None = None,
) -> int:
    """שומר תרגיל (extracted מנורמל) במאגר, ומחזיר את מזהה הרשומה.

    אם ``image_source`` קיים — מעתיק את התמונה לתיקיית המאגר ומקשר אותה לרשומה.
    """
    # ייבוא מקומי — נמנע מלולאת ייבוא מעגלית (personal_assistant טוען את runtime
    # שמייבא בעצמו את exercise_bank).
    from personal_assistant.reactions import detect_reaction_beam_kind

    beam_kind = detect_reaction_beam_kind(extracted).value
    with _db_lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO exercises "
            "(extracted_json, beam_kind, added_by_user_id, created_at, image_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (json.dumps(extracted), beam_kind, added_by_user_id, time.time(), None),
        )
        exercise_id = int(cur.lastrowid)
        image_name: str | None = None
        if image_source is not None:
            image_name = _store_exercise_image(exercise_id, Path(image_source))
            if image_name is not None:
                conn.execute(
                    "UPDATE exercises SET image_path = ? WHERE id = ?",
                    (image_name, exercise_id),
                )
        conn.commit()
        return exercise_id


def count_exercises() -> int:
    with _db_lock:
        conn = _connect()
        row = conn.execute("SELECT COUNT(*) AS n FROM exercises").fetchone()
        return int(row["n"]) if row else 0


def get_exercise_by_id(exercise_id: int) -> dict | None:
    with _db_lock:
        conn = _connect()
        row = conn.execute(
            "SELECT extracted_json FROM exercises WHERE id = ?", (int(exercise_id),)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["extracted_json"])


def get_exercise_image_path(exercise_id: int) -> Path | None:
    """נתיב לקובץ התמונה השמורה של תרגיל, אם קיים על הדיסק."""
    with _db_lock:
        conn = _connect()
        row = conn.execute(
            "SELECT image_path FROM exercises WHERE id = ?", (int(exercise_id),)
        ).fetchone()
    if row is None:
        return None
    rel = row["image_path"]
    if not rel:
        return None
    path = EXERCISE_BANK_IMAGES_DIR / str(rel)
    return path if path.is_file() else None


def get_random_exercise() -> tuple[int, dict] | None:
    """תרגיל אקראי מכל המאגר, ללא זכירת מי קיבל מה — לשימושים כלליים."""
    with _db_lock:
        conn = _connect()
        row = conn.execute(
            "SELECT id, extracted_json FROM exercises ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return int(row["id"]), json.loads(row["extracted_json"])


def _all_exercise_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT id FROM exercises").fetchall()
    return [int(row["id"]) for row in rows]


def _sent_exercise_ids(conn: sqlite3.Connection, user_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT exercise_id FROM user_exercise_sent WHERE user_id = ?", (int(user_id),)
    ).fetchall()
    return {int(row["exercise_id"]) for row in rows}


def reset_sent_exercises_for_user(user_id: int) -> None:
    """מוחק את היסטוריית התרגילים שנשלחו למשתמש — מאפשר סבב חדש."""
    with _db_lock:
        conn = _connect()
        conn.execute(
            "DELETE FROM user_exercise_sent WHERE user_id = ?", (int(user_id),)
        )
        conn.commit()


def exercise_bank_cooldown_remaining_sec(user_id: int, *, now: float | None = None) -> float | None:
    """כמה שניות נשארו עד שאפשר לקבל תרגיל נוסף מהמאגר; None אם מותר עכשיו."""
    from bot.access import user_has_bank_unlock

    if user_has_bank_unlock(user_id):
        return None
    if EXERCISE_BANK_COOLDOWN_SEC <= 0:
        return None
    ts = time.time() if now is None else float(now)
    with _db_lock:
        conn = _connect()
        row = conn.execute(
            "SELECT MAX(sent_at) AS last_sent FROM user_exercise_sent WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
    if row is None or row["last_sent"] is None:
        return None
    remaining = EXERCISE_BANK_COOLDOWN_SEC - (ts - float(row["last_sent"]))
    return remaining if remaining > 0 else None


def pick_next_exercise_for_user(user_id: int) -> tuple[int, dict] | None:
    """תרגיל אקראי שלא נשלח עדיין למשתמש הזה; אם כל התרגילים נשלחו — ממחזר את כולם ומתחיל סבב חדש.

    מסמן את התרגיל שנבחר כ«נשלח» באותה פעולה — קריאה חוזרת תמיד תבחר תרגיל אחר,
    עד שהמאגר ייגמר וייעל מיחזור.
    """
    with _db_lock:
        conn = _connect()
        all_ids = _all_exercise_ids(conn)
        if not all_ids:
            return None
        sent_ids = _sent_exercise_ids(conn, user_id)
        unsent = [eid for eid in all_ids if eid not in sent_ids]
        if not unsent:
            conn.execute(
                "DELETE FROM user_exercise_sent WHERE user_id = ?", (int(user_id),)
            )
            unsent = all_ids
        chosen_id = random.choice(unsent)
        row = conn.execute(
            "SELECT extracted_json FROM exercises WHERE id = ?", (chosen_id,)
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "INSERT OR REPLACE INTO user_exercise_sent (user_id, exercise_id, sent_at) "
            "VALUES (?, ?, ?)",
            (int(user_id), int(chosen_id), time.time()),
        )
        conn.commit()
        return chosen_id, json.loads(row["extracted_json"])


async def deliver_exercise_bank_after_approve(
    context,
    chat_id: int,
    *,
    extracted: dict,
    reply: str,
    solved: dict,
    draft_msg_id: int | None,
    send_text: SendTextFn,
    edit_draft_message: EditDraftFn,
) -> None:
    """אחרי אישור טיוטה במצב «הוספה למאגר»: שומר במאגר במקום לפתור/למסור."""
    from bot.solution_session import (
        clear_pending_bank_submission_image,
        consume_pending_bank_submission_image,
    )

    has_result = bool((solved or {}).get("result"))
    if not has_result:
        if reply:
            sent = await send_text(context, chat_id, reply)
            try:
                set_draft_error_message_id(chat_id, int(getattr(sent, "message_id", 0)))
            except Exception:
                pass
        if draft_msg_id is not None:
            await edit_draft_message(
                context,
                chat_id,
                draft_msg_id,
                extracted,
            )
        return

    duplicate_id = find_duplicate_exercise(extracted)
    if duplicate_id is not None:
        # כפילות — לא שומרים תמונה נוספת; מנקים עותק זמני.
        clear_pending_bank_submission_image(chat_id)
        if draft_msg_id is not None:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=draft_msg_id)
            except BadRequest:
                pass
        await send_text(
            context,
            chat_id,
            f"תרגיל עם הנתונים האלה כבר קיים במאגר (מספר #{duplicate_id}) — לא נוסף בשנית.",
        )
        return

    pending_image = consume_pending_bank_submission_image(chat_id)
    try:
        exercise_id = add_exercise(
            extracted,
            added_by_user_id=chat_id,
            image_source=pending_image,
        )
    finally:
        if pending_image is not None:
            try:
                Path(pending_image).unlink(missing_ok=True)
            except OSError as exc:
                log.warning(
                    "Failed to delete pending bank image after save %s: %s",
                    pending_image,
                    exc,
                )

    if draft_msg_id is not None:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=draft_msg_id)
        except BadRequest:
            pass

    await send_text(
        context,
        chat_id,
        f"התרגיל נוסף למאגר התרגילים (מספר #{exercise_id}).",
    )
