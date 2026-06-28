# -*- coding: utf-8 -*-
"""קבועים, prompts וסכמות — ללא לוגיקה."""
from __future__ import annotations

import os
import re
from pathlib import Path

# שורש החבילה (BotFuther/), לא תיקיית bot/
APP_DIR = Path(__file__).resolve().parent.parent

BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "Beam Solver").strip() or "Beam Solver"

TELEGRAM_KEY_NAMES = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_TOKEN",
    "BOT_TOKEN",
    "TG_BOT_TOKEN",
)
GEMINI_KEY_NAMES = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GEMINI_API_KEY",
)

# Paid Tier — lite ראשי (פחות 503); flash כגיבוי איכות
DEFAULT_MODEL = "gemini-2.5-flash-lite"
FALLBACK_MODELS: tuple[str, ...] = ("gemini-2.5-flash",)
DEPRECATED_MODEL_PREFIXES = ("gemini-1.5-", "gemini-1.0-")

# רזולוציה גבוהה — כתב יד ושרטוטים הנדסיים
IMAGE_MAX_PX = 2048
IMAGE_MIN_VISION_PX = 1400
IMAGE_JPEG_QUALITY = 94
VISION_MAX_OUTPUT_TOKENS = 4096
# הסברים בעברית נקטעים עם 500 — מינימום ~2000 לשאלות "למה/איך/תסביר"
CHAT_MAX_OUTPUT_TOKENS = 2048
TOOL_MAX_OUTPUT_TOKENS = 1024
RETRYABLE_API_CODES = frozenset({429, 500, 502, 503, 504})
MAX_TOOL_ROUNDS = 5
GEMINI_HTTP_TIMEOUT_MS = 25_000


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


MAX_RETRIES_PER_MODEL = _env_int("GEMINI_MAX_RETRIES_PER_MODEL", 3)
RETRY_BASE_DELAY_SEC = _env_float("GEMINI_RETRY_BASE_DELAY_SEC", 1.5)
CHAT_HTTP_TIMEOUT_MS = _env_int("CHAT_HTTP_TIMEOUT_MS", 10_000)
CHAT_LOCAL_REPLIES = _env_bool("CHAT_LOCAL_REPLIES", True)

# מצב הבוט: False = חילוץ + חישוב ריאקציות; True = חילוץ בלבד (רגרסיה)
VISION_EXTRACT_ONLY_MODE = _env_bool("VISION_EXTRACT_ONLY_MODE", False)

# human-in-the-loop: טיוטה לעריכה לפני חישוב (ברירת מחדל: פעיל)
DRAFT_APPROVAL_MODE = _env_bool("DRAFT_APPROVAL_MODE", True)

# מצב מהיר (ברירת מחדל): קריאת Gemini אחת + נורמליזציה — ~10–18 שניות.
# VISION_FAST_MODE=0 + VISION_TOTAL_BUDGET_SEC=50 → staged (5 קריאות) לדיוק מקסימלי.
VISION_PREFER_FAST = _env_bool("VISION_PREFER_FAST", True)
VISION_FAST_MODE = _env_bool("VISION_FAST_MODE", VISION_PREFER_FAST)

VISION_FAST_FALLBACK_STAGED = _env_bool("VISION_FAST_FALLBACK_STAGED", True)

# אחרי כישלון ולידציה במצב מהיר: ניסיון נוסף עם מודל איכות (flash).
VISION_QUALITY_RETRY = _env_bool("VISION_QUALITY_RETRY", True)
VISION_QUALITY_MODEL = os.getenv("VISION_QUALITY_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

# חילוץ עומסים ממוקד (שלבים 3–4) כשהגיאומטריה כבר טובה — 2 קריאות במקום 5.
VISION_LOADS_REFINE = _env_bool("VISION_LOADS_REFINE", True)

# החזרת טיוטה חלקית גרועה במצב מהיר (רק אם כל ה-fallbacks נכשלו).
VISION_ALLOW_PARTIAL_FAST = _env_bool("VISION_ALLOW_PARTIAL_FAST", False)

# 429/503: ניסיון אוטומטי עם gemini-2.5-flash לפני כישלון (כשהראשי הוא lite).
VISION_OVERLOAD_FALLBACK = _env_bool("VISION_OVERLOAD_FALLBACK", True)
VISION_OVERLOAD_BACKOFF_SEC = _env_float("VISION_OVERLOAD_BACKOFF_SEC", 3.0)

# תקציב זמן כולל לכל חילוץ תמונה (שניות).
VISION_TOTAL_BUDGET_SEC = _env_float("VISION_TOTAL_BUDGET_SEC", 120.0)

# עיבוד תמונה ברקע — תשובה מיידית "מעבד..." ואז שליחת תוצאה.
VISION_ASYNC_ENABLED = _env_bool("VISION_ASYNC_ENABLED", True)
VISION_ASYNC_ACK_TEXT = "⏳"

# מגבלות כדי לשמור על התקציב.
VISION_MAX_MODELS_PER_IMAGE = _env_int("VISION_MAX_MODELS_PER_IMAGE", 1)
VISION_MAX_STAGED_RETRIES = _env_int("VISION_MAX_STAGED_RETRIES", 2)
# כמה חילוצי תמונה במקביל (גלובלי) — מונע הצפה של Gemini.
VISION_GLOBAL_CONCURRENCY = _env_int("VISION_GLOBAL_CONCURRENCY", 2)
# ניסיונות חוזרים לכל תמונה כש-Gemini מחזיר 429/503.
VISION_JOB_RETRY_ATTEMPTS = _env_int("VISION_JOB_RETRY_ATTEMPTS", 3)
VISION_JOB_RETRY_BASE_SEC = _env_float("VISION_JOB_RETRY_BASE_SEC", 5.0)
VISION_FAST_MAX_OUTPUT_TOKENS = _env_int("VISION_FAST_MAX_OUTPUT_TOKENS", 4096)
VISION_FAST_IMAGE_MIN_PX = _env_int("VISION_FAST_IMAGE_MIN_PX", 1400)

# חיתוך אוטומטי של שרטוט הקורה (Gemini bbox + Pillow) — כבוי כברירת מחדל (חוסך קריאת API).
VISION_BEAM_CROP = _env_bool("VISION_BEAM_CROP", False)

# מקובל בהנדסה אזרחית בישראל: 1 טון = 10 kN
KN_PER_TON = 10.0
CM_PER_M = 100.0
CM2_PER_M2 = 10_000.0

BEAM_TOOL_HINT = re.compile(
    r"קורה|ריאקצ|עומס|סמך|זיז|מומנט|שיזור|קפיצ|מפולג|נקודתי|טון|"
    r"beam|reaction|shear|moment|cantilever|ton",
    re.IGNORECASE,
)
COG_TOOL_HINT = re.compile(
    r"מרכז.?כובד|כובד|xc|yc|IPE|IPN|IPB|UPB|LPN|RHS|צינור|פרופיל|"
    r"חתך\s|שטח|מ[״\"']?ר|m²|m2|"
    r"centroid|cog|center of gravity",
    re.IGNORECASE,
)
EXPLICIT_CALC_HINT = re.compile(
    r"חשב|תחשב|חשבו|בדוק|תבדוק|מה ה|מהו|מה הן|מה הם|תן את|"
    r"compute|calculate",
    re.IGNORECASE,
)
EXERCISE_DATA_HINT = re.compile(
    r"\d|L\s*=|x\s*=\s*\d|w\s*=|M\s*=|"
    r"טון|ton|t\s*/\s*m|מ['\"]?\s*/\s*מ|מטר|\bm\b|מומנט",
    re.IGNORECASE,
)
SOLUTION_REQUEST_HINT = re.compile(
    r"פתרון|ריאקצ|תשוב|תוצא|חשב|תחשב|מה ה|כמה|ערכ|תן|"
    r"xc|yc|מרכז.?כובד",
    re.IGNORECASE,
)
USER_CORRECTION_HINT = re.compile(
    r"לא נכון|לא נכונה|שגוי|שגויה|טעות|טועה|תתקן|תקן|תיקון|"
    r"זה לא|אתה טועה|הבנת לא|קראת לא|לא מה ש|בעצם|למעשה|"
    r"התכוונתי|הנתון (ה)?נכון|הערך (ה)?נכון|תחשב שוב|תנסה שוב|"
    r"עדכון|מעדכן|תעדכן|שיניתי|התיקון|"
    r"wrong|incorrect|not right|fix|actually|i meant|recalculate",
    re.IGNORECASE,
)
CONVERSATIONAL_FOLLOWUP_HINT = re.compile(
    r"למה|איך|תסביר|הסבר|המשך|תמשיך|"
    r"מה (זה|הפירוש|הקשר|קורה)|האם|אם |לא הבנתי|"
    r"תוכל|בבקשה|עזור לי|תעזור|הבנה|לדוגמה|דוגמה|שאלה|"
    r"why|how|explain|continue|what if|can you|help me|understand",
    re.IGNORECASE,
)
IMAGE_REFERENCE_HINT = re.compile(
    r"תמונה|בתרגיל|מה שחילצת|לפי (ה)?(תמונה|שרטוט|תרגיל|תרגילים)|בשרטוט",
    re.IGNORECASE,
)
DATA_CORRECTION_HINT = re.compile(
    r"אורך|עומס|מטר|טון|במקום|צריך להיות|הנתון|הערך|מיקום|"
    r"מ['\"]מה|L\s*=|x\s*=|ריאקצ",
    re.IGNORECASE,
)

EMPTY_GEMINI_REPLY = "לא התקבלה תשובה מ-Gemini."

FULL_EXPLANATION_HINT = re.compile(
    r"הסבר|תסביר|שלב.?אחר.?שלב|פתרון מלא|תפרק|לעומק|בפירוט|מפורט|"
    r"explain|step.?by.?step|in detail|walk me through",
    re.IGNORECASE,
)

BEAM_LOAD_ITEM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["point", "distributed", "moment", "inclined"],
            "description": "סוג העומס",
        },
        "x": {"type": "number", "description": "מיקום x [m] לעומס נקודתי/מומנט/אלכסוני"},
        "x1": {"type": "number", "description": "התחלת עומס מפולג [m]"},
        "x2": {"type": "number", "description": "סוף עומס מפולג [m]"},
        "magnitude_ton": {
            "type": "number",
            "description": "גודל כוח [טון] לעומס נקודתי/אלכסוני (חיובי)",
        },
        "intensity_ton_per_m": {
            "type": "number",
            "description": "עומס מפולג [טון/מ'] (חיובי = כלפי מטה)",
        },
        "M_ton_m": {"type": "number", "description": "מומנט טהור [טון·מ]"},
        "angle_deg": {"type": "number", "description": "זווית עומס אלכסוני מ-+x [מעלות]"},
        "incl_dir": {
            "type": "string",
            "enum": ["dl", "dr"],
            "description": "כיוון אלכסון: dr=מטה-ימין, dl=מטה-שמאל",
        },
        "direction": {
            "type": "string",
            "enum": ["up", "down"],
            "description": "כיוון עומס נקודתי אנכי (ברירת מחדל: down)",
        },
        "Fx_ton": {"type": "number", "description": "רכיב אופקי נוסף לעומס נקודתי [טון]"},
    },
    "required": ["kind"],
}

COG_SHAPE_ITEM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "catalog",
                "i_section",
                "c_section",
                "l_section",
                "rhs",
                "tube",
            ],
            "description": "סוג חתך; catalog=פרופיל מוכן (IPE, IPN...)",
        },
        "catalog_key": {
            "type": "string",
            "description": "שם פרופיל מהקטלוג: IPE, IPN, IPB, UPB, LPN שווה, LPN שונה, צינור עגול, RHS מלבני",
        },
        "label": {"type": "string", "description": "תווית לטבלה (אופציונלי)"},
        "x_m": {"type": "number", "description": "מיקום פינה שמאלית-תחתונה x [m]"},
        "y_m": {"type": "number", "description": "מיקום פינה שמאלית-תחתונה y [m]"},
        "b": {"type": "number", "description": "רוחב [m]"},
        "h": {"type": "number", "description": "גובה [m]"},
        "tf": {"type": "number", "description": "עובי שוליים [m] — חתכי I/U"},
        "tw": {"type": "number", "description": "עובי דופן [m] — חתכי I/U"},
        "t": {"type": "number", "description": "עובי [m] — L / RHS / צינור"},
        "b1": {"type": "number", "description": "רוחב שוק 1 [m] — זווית L"},
        "b2": {"type": "number", "description": "רוחב שוק 2 [m] — זווית L"},
        "D": {"type": "number", "description": "קוטר חיצוני [m] — צינור עגול"},
    },
    "required": ["kind"],
}

COG_CATALOG_ALIASES: dict[str, str] = {
    "ipe": "IPE",
    "ipn": "IPN",
    "ipb": "IPB",
    "upb": "UPB",
    "lpn": "LPN שווה",
    "lpn שווה": "LPN שווה",
    "lpn שונה": "LPN שונה",
    "rhs": "RHS מלבני",
    "rhs מלבני": "RHS מלבני",
    "tube": "צינור עגול",
    "צינור": "צינור עגול",
    "צינור עגול": "צינור עגול",
}

TEMP_IMAGE_DIR = APP_DIR / "_bot_temp_images"
