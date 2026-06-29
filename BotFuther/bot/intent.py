# -*- coding: utf-8 -*-
"""זיהוי כוונה — מתי לחשב הנדסה ומתי שיחת חולין."""
from __future__ import annotations

import re

from bot.config import (
    EXPLICIT_CALC_HINT,
    IMAGE_REFERENCE_HINT,
    SOLUTION_REQUEST_HINT,
)

SMALL_TALK_HINT = re.compile(
    r"לונה פארק|פארק שעשועים|מתקן|אנקונדה|גובה מינימ|מגבלת גובה|"
    r"לא יכול ללמוד|לא בא לי ללמוד|לא לומד|לא לומדת|לא לומד היום|"
    r"לא מעניין|לא בא לי|תהנה|כיף לך|"
    r"מה נשמע|מה שלומך|איך הולך|בילוי|חופש|טיול|חי את החיים|"
    r"חוות|סוסים|שבדיה|מגרד|כואב|הגב|"
    r"amusement|roller coaster|theme park|height limit|horse farm|sweden",
    re.IGNORECASE,
)

ENGINEERING_OPT_OUT_HINT = re.compile(
    r"לא (?:לומד|לומדת|עוסק|עוסקת|מתעסק|מתעסקת).{0,20}הנדס|"
    r"לא מעניין.{0,15}הנדס|"
    r"בכלל לא.{0,12}הנדס|"
    r"לא (?:סטודנט|סטודנטית)",
    re.IGNORECASE,
)

LIFE_HYPOTHETICAL_HINT = re.compile(
    r"מה (אני|עושים) (עושה )?אם",
    re.IGNORECASE,
)

ENGINEERING_INTENT_HINT = re.compile(
    r"קורה|סמך|ריאקצ|עומס|מומנט|שיזור|זיז|קפל|שקיעה|גרבר|מסבך|"
    r"סטטיקה|תרגיל|כוח גזירה|שקיעת|מפולג|נקודתי|"
    r"beam|cantilever|shear|moment|reaction|diagram|Q\s*/\s*M",
    re.IGNORECASE,
)

NUMERIC_EXERCISE_DATA_HINT = re.compile(
    r"L\s*=\s*\d|x\s*=\s*\d|w\s*=\s*\d|M\s*=\s*\d|"
    r"\d\s*(?:טון|ton|t\s*/\s*m|מ['\"]?\s*/\s*מ|מטר|\bm\b|מומנט)",
    re.IGNORECASE,
)

STUDENT_STUCK_HINT = re.compile(
    r"פתרתי|עשיתי|לא יצא|לא יצאה|נראה לי|ראלי|"
    r"איפה טעית|איפה טעיתי|לא יודע איפה|הפתרון שלי|"
    r"didn't work|where did i go wrong|my answer",
    re.IGNORECASE,
)

META_IMAGE_QUESTION_HINT = re.compile(
    r"^(?:איזה|מה|למה)?\s*.*(?:תמונה|שרטוט)\s*\??$|^תמונה\s*\??$",
    re.IGNORECASE,
)

SHORT_SOLVE_COMMAND_HINT = re.compile(
    r"^(?:ריאקציות?|חשב|פתרון|תוצאות|מה ה(?:ריאקצ|תוצא|תשוב))\.?\s*$",
    re.IGNORECASE,
)


def message_has_numeric_exercise_data(text: str) -> bool:
    """מספרים + יחידות/סימון תרגיל — לא סתם ספרה בשיחה."""
    return bool(NUMERIC_EXERCISE_DATA_HINT.search(text or ""))


def is_engineering_opt_out(text: str) -> bool:
    """המשתמש מבהיר שאין לו קשר ללימודים/הנדסה כרגע."""
    return bool(ENGINEERING_OPT_OUT_HINT.search(text or ""))


def is_small_talk(text: str) -> bool:
    """שיחת חולין, בדיחה, או שאלה אישית/חיים — לא תרגיל סטטיקה."""
    t = (text or "").strip()
    if not t:
        return False
    if is_engineering_opt_out(t):
        return True
    if SMALL_TALK_HINT.search(t):
        return True
    if LIFE_HYPOTHETICAL_HINT.search(t) and not has_engineering_intent(t):
        return not message_has_numeric_exercise_data(t)
    if not has_engineering_intent(t) and not message_has_numeric_exercise_data(t):
        if re.search(
            r"חוות|סוס|שבד|נורווג|חי את|מטייל|בחופש|בטיול|בעבודה|במילואים",
            t,
            re.I,
        ):
            return True
    return False


def has_engineering_intent(text: str) -> bool:
    """המשתמש מדבר על סטטיקה/קורות — לא רק מילה שנקלטה בטעות."""
    return bool(ENGINEERING_INTENT_HINT.search(text or ""))


def is_describing_own_solution_problem(text: str) -> bool:
    """סטודנט מתאר שפתר בעצמו ומשהו לא יצא — לא בקשת חישוב מהבוט."""
    return bool(STUDENT_STUCK_HINT.search(text or ""))


def is_meta_question_about_image(text: str) -> bool:
    """שאלת הבהרה על «תמונה» — לא בקשת חישוב."""
    t = (text or "").strip()
    if len(t) > 48:
        return False
    if EXPLICIT_CALC_HINT.search(t) or SHORT_SOLVE_COMMAND_HINT.match(t):
        return False
    return bool(META_IMAGE_QUESTION_HINT.search(t))


def wants_stored_vision_solve(text: str) -> bool:
    """בקשה מפורשת לחשב/לפתור מהתמונה השמורה — לא דיון כללי על ריאקציות."""
    t = (text or "").strip()
    if not t or is_describing_own_solution_problem(t) or is_meta_question_about_image(t):
        return False
    if SHORT_SOLVE_COMMAND_HINT.match(t):
        return True
    if IMAGE_REFERENCE_HINT.search(t) and (
        EXPLICIT_CALC_HINT.search(t) or SOLUTION_REQUEST_HINT.search(t)
    ):
        return True
    if EXPLICIT_CALC_HINT.search(t) and SOLUTION_REQUEST_HINT.search(t):
        return True
    return False


def prompt_has_exercise_data(
    prompt: str,
    *,
    image: tuple[bytes, str] | None = None,
    chat_id: int | None = None,
) -> bool:
    """יש מספיק נתונים לחישוב — מההודעה הנוכחית או מתמונה שחולצה + בקשת פתרון."""
    if image is not None:
        return True
    text = (prompt or "").strip()
    if not text:
        return False
    if message_has_numeric_exercise_data(text):
        return True
    if chat_id is not None and wants_stored_vision_solve(text):
        from bot.vision import get_stored_vision_extracted

        if get_stored_vision_extracted(chat_id):
            return True
    return False


def should_enable_solver_tools(
    prompt: str,
    *,
    image: tuple[bytes, str] | None = None,
    chat_id: int | None = None,
) -> bool:
    """כלים הנדסיים — רק כשיש כוונה הנדסית ברורה ונתונים אמיתיים."""
    text = (prompt or "").strip()
    if not text and image is None:
        return False
    if is_small_talk(text):
        return False
    if image is not None:
        return has_engineering_intent(text) or message_has_numeric_exercise_data(text)
    if not has_engineering_intent(text):
        if chat_id is not None and wants_stored_vision_solve(text):
            from bot.vision import get_stored_vision_extracted

            return get_stored_vision_extracted(chat_id) is not None
        return False
    if message_has_numeric_exercise_data(text):
        return True
    if chat_id is not None and wants_stored_vision_solve(text):
        from bot.vision import get_stored_vision_extracted

        return get_stored_vision_extracted(chat_id) is not None
    return False
