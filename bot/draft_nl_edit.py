# -*- coding: utf-8 -*-
"""תיקון טיוטת תרגיל בשפה חופשית דרך Gemini."""
from __future__ import annotations

import copy
import json
import logging
import re

from google.genai import types

from bot.draft_format import (
    _inclined_mag,
    set_distributed_span_user,
    set_load_x_user,
    sync_beam_distributed_loads,
)
from bot.gemini_chat import (
    friendly_gemini_error,
    gemini_runtime,
    generate_content_with_retries,
)
from bot.vision import finalize_beam_extraction, parse_json_from_llm_text

log = logging.getLogger("beam_telegram_bot")

_NL_EDIT_PROMPT = """\
אתה מעדכן מודל תרגיל קורה (JSON) לפי הוראת משתמש בעברית.
עדכן רק את מה שהמשתמש ביקש; שמור על שאר השדות ללא שינוי מיותר.
החזר JSON מלא בלבד (בלי markdown).

מבנה פקודה מהמשתמש (פרש לפי הסדר הזה):
1) פקודה — מה לעשות: תשנה / תעביר / תוסיף / תמחק / תהפוך / תזיז וכו'.
2) שם עומס (סוג) — מומנט / אלכסוני / משופע / צירי / אופקי / אנכי / נקודתי / מפורס.
3) זיהוי עומס (רק אם צריך להבדיל) — למשל: הימני / השמאלי / בנקודה C /
   ב-x=5 / במשקל 15 טון / העומס השני / כל האלכסוניים.
4) תוצאה — המצב הרצוי אחרי השינוי: לאנכי / ל-8 טון / ל-x=3 / למעלה /
   לכיוון ↙ / מחק / זווית 45 וכו'.

זיהוי ימני/שמאלי — חובה לפי מיקום x על הקורה (לא לפי סדר במערך loads):
- «ימני» / «הימני» = העומס מהסוג המבוקש עם x הגדול ביותר.
- «שמאלי» / «השמאלי» = העומס מהסוג המבוקש עם x הקטן ביותר.
כשמעבירים עומס אחד — שנה רק את ה-x של אותו עומס. אסור להחליף מקומות בין שני עומסים
ואסור להזיז עומס אחר. «קצה ימני של הקורה» = x=L. «קצה שמאלי» = x=0.
כשמעבירים ידנית: מחק label_at מהעומס שהוזז (כדי שלא יימשך חזרה לתווית ישנה).

דוגמאות פרשנות:
- «שנה את האלכסוניים לאנכיים» → פקודה=שנה, סוג=אלכסוני, זיהוי=הכל, תוצאה=אנכי
- «תעביר את המומנט הימני לקצה הימני של הקורה» → בחר moment עם max(x), שים x=L; שאר העומסים ללא שינוי
- «תעביר את המומנט הימני ל-x=6» → פקודה=תעביר, סוג=מומנט, זיהוי=ימני, תוצאה=x=6
- «תמחק את העומס האנכי במשקל 15 טון» → פקודה=מחק, סוג=אנכי, זיהוי=15טון, תוצאה=מחיקה
- «תוסיף עומס צירי» → הוסף point עם Fy=0 ו-Fx≠0 (ברירת מחדל Fx=5 במרכז הקורה)
- «תוסיף עומס צירי 4 טון ב-x=2» → פקודה=הוסף, סוג=צירי, תוצאה=Fx=4 ב-x=2
- «שנה אורך של עומס מפורס ל-3 מטר» → אצל distributed: עדכן x1/x2; סמן _user_span
- «תאריך את המפורס הימני» → בחר distributed עם max(x2), הארך את הקצה הימני שלו
- «תאריך את הקצה השמאלי של המפורס הימני ב-2 מטר» → בחר max(x2), הזז x1 שמאלה ב-2 (x2 ללא שינוי)
- «שנה את המפורס מ-x=0 עד x=4» → distributed: x1=0, x2=4
זיהוי מפורס ימני/שמאלי: ימני = הטווח עם x2 הגדול ביותר; שמאלי = הטווח עם x1 הקטן ביותר.
«קצה שמאלי/ימני» של המפורס = איזה קצה של הטווח להזיז; «ב-2 מטר» = דלתא להארכה, לא אורך סופי.
עומס צירי חייב type=point עם Fx ו-Fy=0 — לא type נפרד "axial".
אורך מפורס = x2-x1 (מטרים על הקורה), לא w (טון/מטר).
אם חסר זיהוי ויש רק עומס אחד מהסוג — בחר אותו. אם יש כמה ולא ברור — עדכן רק
את מה שאפשר לזהות בוודאות; אל תנחש בין שני עומסים דומים.

מיפוי שם עומס ל-type:
- אנכי / נקודתי → point עם Fy (Fx=0)
- צירי / אופקי → point עם Fx (Fy=0)
- אלכסוני / משופע → inclined
- מומנט → moment
- מפורס → distributed

סכמת עומסים (loads) — חובה להשתמש בה נכון:
- נקודתי אנכי: {{"type":"point","x":<m>,"Fy":<ton>,"Fx":0}}
  Fy חיובי = מטה. אסור להשאיר Fx משמעותי בעומס אנכי.
- צירי/אופקי: {{"type":"point","x":<m>,"Fy":0,"Fx":<ton>}}
- אלכסוני/משופע: {{"type":"inclined","x":<m>,"magnitude_ton":<ton>,"angle_deg":<deg>,"incl_dir":"dr"|"dl"}}
  incl_dir: dr=↘ , dl=↙. אל תשאיר type=inclined אם המשתמש ביקש אנכי.
- מומנט: {{"type":"moment","x":<m>,"M":<ton·m>}}
- מפורס: {{"type":"distributed","x1":<m>,"x2":<m>,"w":<ton/m>,"shape":"rectangular"}}

המרות חשובות:
- אלכסוני → אנכי/נקודתי: type="point", Fy = magnitude_ton הקיים (אותו משקל), Fx=0.
  מחק magnitude_ton, angle_deg, incl_dir. אל תשנה ל-angle_deg=90 ותשאיר inclined.
- אנכי → אלכסוני: type="inclined" עם magnitude_ton מה-|Fy|, angle_deg (ברירת מחדל 30), incl_dir.
- אל תשנה גודל/משקל אלא אם המשתמש ביקש במפורש מספר חדש בתוצאה.

סכמת מעטפת:
{{
  "exercise_type": "beam",
  "beam": {{
    "L": <number>,
    "supports": [...],
    "loads": [...]
  }}
}}

מודל נוכחי:
{current_json}

הוראת המשתמש:
{user_instruction}
"""

_INCLINED_WORD_RE = re.compile(r"אלכסונ|משופע|אלכסון|inclined", re.IGNORECASE)
_VERTICAL_WORD_RE = re.compile(r"אנכי|נקודת|ישר(?!ה)|vertical|לאנכי", re.IGNORECASE)
_MOVE_VERB_RE = re.compile(r"תעביר|תזיז|העבר|הזז|תעבירי|תזיזי", re.IGNORECASE)
_ADD_VERB_RE = re.compile(r"תוסיף|הוסף|תוסיפי|להוסיף", re.IGNORECASE)
_SIDE_RIGHT_RE = re.compile(r"ימני|ימין", re.IGNORECASE)
_SIDE_LEFT_RE = re.compile(r"שמאל", re.IGNORECASE)
_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_X_EQUALS_RE = re.compile(r"(?:ב\s*)?x\s*=\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_MAG_TON_RE = re.compile(
    r"(?:במשקל|גודל|כוח)?\s*(\d+(?:[.,]\d+)?)\s*(?:טון|ton|t\b)",
    re.IGNORECASE,
)
_END_RIGHT_RE = re.compile(
    r"קצה\s*ה?ימנ|קצה\s*ימין|סוף\s*ה?קורה|לקצה\s*ה?ימנ",
    re.IGNORECASE,
)
_END_LEFT_RE = re.compile(
    r"קצה\s*ה?שמאל|תחילת\s*ה?קורה|התחלת\s*ה?קורה|לקצה\s*ה?שמאל",
    re.IGNORECASE,
)
_DIST_WORD_RE = re.compile(r"מפורס|מפולג|distributed|udl", re.IGNORECASE)
_SPAN_INTENT_RE = re.compile(r"אורך|טווח|תקצר|תאריך|קצר|ארך", re.IGNORECASE)
_EXTEND_RE = re.compile(
    r"תאריך|שי?אריך|להאריך|האר[י]?ך|יאריך",
    re.IGNORECASE,
)
_SHORTEN_RE = re.compile(r"תקצר|לקצר|תקצרי", re.IGNORECASE)
_LENGTH_TO_RE = re.compile(
    r"(?:ל-?|לאורך\s*(?:של)?|באורך(?:\s*של)?)\s*"
    r"(\d+(?:[.,]\d+)?)\s*(?:מ(?:['׳]?|טר(?:ים)?)?|m\b)?",
    re.IGNORECASE,
)
_BY_DELTA_RE = re.compile(
    r"ב-?\s*(\d+(?:[.,]\d+)?)\s*(?:מ(?:['׳]?|טר(?:ים)?)?|m\b)?",
    re.IGNORECASE,
)
_SPAN_EDGE_LEFT_RE = re.compile(r"קצה\s*ה?שמאל", re.IGNORECASE)
_SPAN_EDGE_RIGHT_RE = re.compile(
    r"קצה\s*ה?ימנ|קצה\s*ימין",
    re.IGNORECASE,
)
_FROM_TO_X_RE = re.compile(
    r"מ-?\s*(?:x\s*=\s*)?(\d+(?:[.,]\d+)?)\s*"
    r"עד\s*-?\s*(?:x\s*=\s*)?(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_DEFAULT_SPAN_DELTA_M = 1.0

# (regex על סוג בעברית, kind פנימי)
_LOAD_KIND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"מומנט", re.I), "moment"),
    (re.compile(r"אלכסונ|משופע", re.I), "inclined"),
    (re.compile(r"צירי|אופקי", re.I), "axial"),
    (re.compile(r"מפורס", re.I), "distributed"),
    (re.compile(r"אנכי|נקודת", re.I), "vertical"),
)


def wants_inclined_to_vertical(user_instruction: str) -> bool:
    """האם ההוראה מבקשת להפוך עומס(ים) אלכסוניים לאנכיים."""
    text = (user_instruction or "").strip()
    if not text:
        return False
    if _INCLINED_WORD_RE.search(text) and _VERTICAL_WORD_RE.search(text):
        return True
    # ניסוחים קצרים: «תעשה לאנכיים», «שנה לאנכי»
    if re.search(r"ל\s*אנכי", text) and (
        _INCLINED_WORD_RE.search(text) or "עומס" in text or "כוח" in text
    ):
        return True
    return False


def convert_inclined_loads_to_vertical(extracted: dict) -> dict:
    """כל עומס inclined → point אנכי עם אותו משקל (magnitude) כ-Fy."""
    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return data
    loads = beam.get("loads")
    if not isinstance(loads, list):
        return data
    out_loads: list = []
    for raw in loads:
        if not isinstance(raw, dict):
            out_loads.append(raw)
            continue
        if str(raw.get("type", "")).lower().strip() != "inclined":
            out_loads.append(dict(raw))
            continue
        mag = _inclined_mag(raw)
        x = float(raw.get("x", 0.0) or 0.0)
        # כיוון מטה נשמר כ-Fy חיובי (מוסכמת השרטוט)
        new_ld: dict = {
            "type": "point",
            "x": x,
            "Fy": abs(mag),
            "Fx": 0.0,
        }
        for key in ("label_at", "from_label", "to_label"):
            if raw.get(key):
                new_ld[key] = raw[key]
        out_loads.append(new_ld)
    beam = dict(beam)
    beam["loads"] = out_loads
    data["beam"] = beam
    return data


def _load_anchor_x(ld: dict) -> float:
    t = str(ld.get("type", "")).lower().strip()
    if t == "distributed":
        try:
            x1 = float(ld.get("x1", ld.get("start_x", 0.0)) or 0.0)
            x2 = float(ld.get("x2", ld.get("end_x", x1)) or x1)
            return 0.5 * (x1 + x2)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(ld.get("x", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_axial_point(ld: dict) -> bool:
    if str(ld.get("type", "")).lower().strip() != "point":
        return False
    if ld.get("_draft_axial"):
        return True
    try:
        fy = abs(float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0))
        fx = abs(float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0))
    except (TypeError, ValueError):
        return False
    return fx >= 1e-9 and fy < 1e-9


def _parse_float_token(raw: str) -> float | None:
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _parse_magnitude_ton(text: str) -> float | None:
    m = _MAG_TON_RE.search(text)
    if m:
        return _parse_float_token(m.group(1))
    return None


def _parse_explicit_x(text: str) -> float | None:
    m = _X_EQUALS_RE.search(text)
    if m:
        return _parse_float_token(m.group(1))
    return None


def try_add_load(extracted: dict, user_instruction: str) -> dict | None:
    """הוספת עומס לפי סוג (+ גודל/מיקום אופציונליים) — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text or not _ADD_VERB_RE.search(text):
        return None
    # לא לבלבל עם «תוסיף … לאנכי» כהמרה — אם יש המרת סוג בלי הוספה מפורשת של חדש
    kind = _parse_load_kind(text)
    if kind is None:
        return None

    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    try:
        L = float(beam.get("L", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if L <= 0:
        return None

    mag = _parse_magnitude_ton(text)
    # מספר בודד בלי «טון» — רק אם אין x= מפורש שתופס אותו
    if mag is None:
        x_m = _X_EQUALS_RE.search(text)
        nums = list(_NUM_RE.finditer(text))
        if len(nums) == 1 and (x_m is None or nums[0].start() != x_m.start()):
            # אם יש x= — המספר שם הוא מיקום, לא גודל
            if x_m is None:
                mag = _parse_float_token(nums[0].group(1))

    x_explicit = _parse_explicit_x(text)
    if x_explicit is not None:
        x = max(0.0, min(L, x_explicit))
    elif _END_RIGHT_RE.search(text):
        x = L
    elif _END_LEFT_RE.search(text):
        x = 0.0
    else:
        x = round(L * 0.5, 3)

    # כיוון: ברירת מחדל ימינה (Fx>0) / מטה (Fy>0 במוסכמת vision)
    to_left = bool(re.search(r"שמאלה|לכיוון\s*שמאל|←", text))
    to_up = bool(re.search(r"למעלה|כלפי\s*מעלה|↑", text))

    if kind == "axial":
        fx_mag = abs(mag) if mag is not None and mag > 0 else 5.0
        fx = -fx_mag if to_left else fx_mag
        new_ld = {
            "type": "point",
            "x": x,
            "Fy": 0.0,
            "Fx": fx,
            "_user_x": True,
            "_user_mag": True,
        }
    elif kind == "vertical":
        fy_mag = abs(mag) if mag is not None and mag > 0 else 5.0
        fy = -fy_mag if to_up else fy_mag
        new_ld = {
            "type": "point",
            "x": x,
            "Fy": fy,
            "Fx": 0.0,
            "_user_x": True,
            "_user_mag": True,
        }
    elif kind == "moment":
        m_mag = abs(mag) if mag is not None and mag > 0 else 10.0
        new_ld = {
            "type": "moment",
            "x": x,
            "M": m_mag,
            "_user_x": True,
            "_user_mag": True,
        }
    elif kind == "inclined":
        m_mag = abs(mag) if mag is not None and mag > 0 else 5.0
        incl_dir = "dl" if to_left else "dr"
        new_ld = {
            "type": "inclined",
            "x": x,
            "magnitude_ton": m_mag,
            "angle_deg": 30.0,
            "incl_dir": incl_dir,
            "_user_x": True,
            "_user_mag": True,
        }
    elif kind == "distributed":
        w_mag = abs(mag) if mag is not None and mag > 0 else 2.0
        half = min(L * 0.2, 2.0)
        x1 = max(0.0, x - half)
        x2 = min(L, x + half)
        if x2 - x1 < 0.1:
            x1, x2 = 0.0, min(L, max(0.1, L * 0.3))
        new_ld = {
            "type": "distributed",
            "x1": x1,
            "x2": x2,
            "w": w_mag,
            "shape": "rectangular",
            "_user_span": True,
            "_user_mag": True,
        }
    else:
        return None

    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    loads.append(new_ld)
    beam = dict(beam)
    beam["loads"] = loads
    data["beam"] = beam
    return data


def _is_vertical_point(ld: dict) -> bool:
    if str(ld.get("type", "")).lower().strip() != "point":
        return False
    if _is_axial_point(ld):
        return False
    return True


def _load_matches_kind(ld: dict, kind: str) -> bool:
    t = str(ld.get("type", "")).lower().strip()
    if kind == "moment":
        return t == "moment"
    if kind == "inclined":
        return t == "inclined"
    if kind == "distributed":
        return t == "distributed"
    if kind == "axial":
        return _is_axial_point(ld)
    if kind == "vertical":
        return _is_vertical_point(ld)
    return False


def _parse_side_token(text: str) -> str | None:
    """מחזיר 'right' / 'left' לפי האזכור הראשון של צד בעומס (לא ביעד)."""
    # מעדיפים אזכור ליד סוג העומס: «מומנט ימני» לפני «קצה ימני»
    m_right = _SIDE_RIGHT_RE.search(text)
    m_left = _SIDE_LEFT_RE.search(text)
    if m_right and m_left:
        return "right" if m_right.start() < m_left.start() else "left"
    if m_right:
        return "right"
    if m_left:
        return "left"
    return None


def _parse_dest_end(text: str) -> str | None:
    """יעד בקצה הקורה: 'right' / 'left'."""
    if _END_RIGHT_RE.search(text):
        return "right"
    if _END_LEFT_RE.search(text):
        return "left"
    return None


def _parse_load_kind(text: str) -> str | None:
    for pat, kind in _LOAD_KIND_PATTERNS:
        if pat.search(text):
            return kind
    return None


def _distributed_x1_x2(ld: dict) -> tuple[float, float]:
    try:
        x1 = float(ld.get("x1", ld.get("start_x", 0.0)) or 0.0)
        x2 = float(ld.get("x2", ld.get("end_x", x1)) or x1)
    except (TypeError, ValueError):
        return 0.0, 0.0
    if x2 < x1:
        x1, x2 = x2, x1
    return x1, x2


def _parse_span_edge(text: str) -> str | None:
    """קצה של טווח המפורס להזזה: 'left' / 'right'."""
    m_left = _SPAN_EDGE_LEFT_RE.search(text)
    m_right = _SPAN_EDGE_RIGHT_RE.search(text)
    if m_left and m_right:
        return "left" if m_left.start() < m_right.start() else "right"
    if m_left:
        return "left"
    if m_right:
        return "right"
    return None


def _parse_distributed_side(text: str) -> str | None:
    """ימני/שמאלי של איזה מפורס — מתעלם מקצה הטווח ומקצה הקורה."""
    text_for_side = _SPAN_EDGE_LEFT_RE.sub(" ", text)
    text_for_side = _SPAN_EDGE_RIGHT_RE.sub(" ", text_for_side)
    text_for_side = _END_RIGHT_RE.sub(" ", text_for_side)
    text_for_side = _END_LEFT_RE.sub(" ", text_for_side)
    return _parse_side_token(text_for_side)


def _parse_span_delta_m(text: str) -> float | None:
    """דלתא במטרים: «ב-2 מטר», «ב2 מטרים»."""
    m = _BY_DELTA_RE.search(text)
    if m:
        return _parse_float_token(m.group(1))
    return None


def _pick_distributed_index(
    loads: list,
    text: str,
) -> int | None:
    """ימני = max(x2), שמאלי = min(x1) — לא לפי אמצע הטווח."""
    candidates: list[tuple[int, dict]] = []
    for i, ld in enumerate(loads):
        if isinstance(ld, dict) and _load_matches_kind(ld, "distributed"):
            candidates.append((i, ld))
    if not candidates:
        return None
    side = _parse_distributed_side(text)
    if side is None:
        if len(candidates) != 1:
            return None
        return candidates[0][0]
    if side == "right":
        return max(candidates, key=lambda it: _distributed_x1_x2(it[1])[1])[0]
    return min(candidates, key=lambda it: _distributed_x1_x2(it[1])[0])[0]


def try_resize_distributed_load(extracted: dict, user_instruction: str) -> dict | None:
    """שינוי אורך/טווח עומס מפורס — דטרמיניסטי.

    דוגמאות: «שנה אורך של עומס מפורס ל-3 מטר», «תאריך את המפורס הימני»,
    «שנה מפורס מ-x=0 עד x=4».
    """
    text = (user_instruction or "").strip()
    if not text or not _DIST_WORD_RE.search(text):
        return None

    from_to = _FROM_TO_X_RE.search(text)
    extend_mode = bool(_EXTEND_RE.search(text))
    shorten_mode = bool(_SHORTEN_RE.search(text))
    span_edge = _parse_span_edge(text)
    # דלתא («ב-2 מטר») לעומת אורך סופי («ל-2 מטר» / «באורך 2»)
    delta_m = _parse_span_delta_m(text)
    length_m: float | None = None
    if from_to is None and not extend_mode and not shorten_mode:
        if not _SPAN_INTENT_RE.search(text):
            return None
        lm = _LENGTH_TO_RE.search(text)
        if lm is None:
            nums = list(_NUM_RE.finditer(text))
            meter_m = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(?:מ(?:['׳]?|טר(?:ים)?)?|m\b)",
                text,
                re.IGNORECASE,
            )
            if meter_m:
                length_m = _parse_float_token(meter_m.group(1))
            elif len(nums) == 1:
                length_m = _parse_float_token(nums[0].group(1))
            else:
                return None
        else:
            length_m = _parse_float_token(lm.group(1))
        if length_m is None or length_m <= 0:
            return None
    elif from_to is None and (extend_mode or shorten_mode):
        # בהארכה/קיצור המספר הוא דלתא — לא אורך סופי
        if delta_m is None:
            lm = _LENGTH_TO_RE.search(text)
            if lm is not None:
                delta_m = _parse_float_token(lm.group(1))
        if delta_m is None:
            meter_m = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(?:מ(?:['׳]?|טר(?:ים)?)?|m\b)",
                text,
                re.IGNORECASE,
            )
            if meter_m:
                delta_m = _parse_float_token(meter_m.group(1))

    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    try:
        L = float(beam.get("L", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if L <= 0:
        return None
    loads = beam.get("loads")
    if not isinstance(loads, list) or not loads:
        return None

    idx = _pick_distributed_index(loads, text)
    if idx is None:
        return None

    side = _parse_distributed_side(text)
    chosen = dict(loads[idx])
    cur_x1, cur_x2 = _distributed_x1_x2(chosen)
    if cur_x2 - cur_x1 < 0.05:
        cur_x1, cur_x2 = 0.0, min(L, 2.0)

    if from_to is not None:
        x1 = _parse_float_token(from_to.group(1))
        x2 = _parse_float_token(from_to.group(2))
        if x1 is None or x2 is None:
            return None
    elif extend_mode:
        # «תאריך את הקצה השמאלי … ב-2 מטר» — מזיזים קצה בדלתא, לא כופים אורך סופי
        delta = float(delta_m) if delta_m is not None and delta_m > 0 else _DEFAULT_SPAN_DELTA_M
        edge = span_edge
        if edge is None:
            # בלי קצה מפורש — הקצה החיצוני של העומס שנבחר
            edge = "left" if side == "left" else "right"
        if edge == "left":
            x1 = max(0.0, cur_x1 - delta)
            x2 = cur_x2
        else:
            x1 = cur_x1
            x2 = min(L, cur_x2 + delta)
    elif shorten_mode:
        delta = float(delta_m) if delta_m is not None and delta_m > 0 else _DEFAULT_SPAN_DELTA_M
        edge = span_edge
        if edge is None:
            edge = "left" if side == "left" else "right"
        if edge == "left":
            x1 = min(cur_x2 - 0.1, cur_x1 + delta)
            x2 = cur_x2
        else:
            x1 = cur_x1
            x2 = max(cur_x1 + 0.1, cur_x2 - delta)
    else:
        assert length_m is not None and length_m > 0
        # מפורס ימני: שומרים את הקצה הימני (x2); שמאלי: את הקצה השמאלי (x1)
        if side == "right":
            x2 = cur_x2
            x1 = max(0.0, x2 - float(length_m))
            if x2 - x1 + 1e-9 < float(length_m):
                x1 = 0.0
                x2 = min(L, float(length_m))
        else:
            x1 = cur_x1
            x2 = min(L, x1 + float(length_m))
            if x2 - x1 + 1e-9 < float(length_m):
                x2 = L
                x1 = max(0.0, x2 - float(length_m))

    x1 = max(0.0, min(L, float(x1)))
    x2 = max(0.0, min(L, float(x2)))
    if x2 < x1:
        x1, x2 = x2, x1
    if x2 - x1 < 0.05:
        return None
    if abs(x1 - cur_x1) < 1e-9 and abs(x2 - cur_x2) < 1e-9:
        return None

    set_distributed_span_user(chosen, x1, x2)
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    sync_beam_distributed_loads(beam)
    data["beam"] = beam
    return data


def _lock_changed_distributed_spans(original: dict, updated: dict) -> dict:
    """אם Gemini שינה x1/x2 של מפורס — סמן _user_span כדי ש-finalize לא ידרוס."""
    orig_beam = original.get("beam") if isinstance(original, dict) else None
    upd_beam = updated.get("beam") if isinstance(updated, dict) else None
    if not isinstance(orig_beam, dict) or not isinstance(upd_beam, dict):
        return updated
    orig_loads = [
        ld
        for ld in (orig_beam.get("loads") or [])
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() == "distributed"
    ]
    upd_loads = upd_beam.get("loads")
    if not isinstance(upd_loads, list):
        return updated
    changed = False
    for i, ld in enumerate(upd_loads):
        if not isinstance(ld, dict) or str(ld.get("type", "")).lower() != "distributed":
            continue
        if ld.get("_user_span"):
            continue
        try:
            x1 = float(ld.get("x1", ld.get("start_x", 0.0)) or 0.0)
            x2 = float(ld.get("x2", ld.get("end_x", x1)) or x1)
        except (TypeError, ValueError):
            continue
        matched_orig = None
        if i < len(orig_loads):
            matched_orig = orig_loads[i]
        if matched_orig is not None:
            try:
                ox1 = float(matched_orig.get("x1", matched_orig.get("start_x", 0.0)) or 0.0)
                ox2 = float(matched_orig.get("x2", matched_orig.get("end_x", ox1)) or ox1)
            except (TypeError, ValueError):
                ox1 = ox2 = None
            if ox1 is not None and abs(x1 - ox1) < 0.05 and abs(x2 - ox2) < 0.05:
                continue
        set_distributed_span_user(ld, x1, x2)
        changed = True
    if changed:
        beam = dict(upd_beam)
        beam["loads"] = [dict(x) if isinstance(x, dict) else x for x in upd_loads]
        sync_beam_distributed_loads(beam)
        out = dict(updated)
        out["beam"] = beam
        return out
    return updated


def try_move_load_to_beam_end(extracted: dict, user_instruction: str) -> dict | None:
    """העברת עומס מזוהה (ימני/שמאלי לפי x) לקצה הקורה — דטרמיניסטי.

    מחזיר extracted מעודכן, או None אם הפקודה לא מתאימה.
    """
    text = (user_instruction or "").strip()
    if not text or not _MOVE_VERB_RE.search(text):
        return None
    dest = _parse_dest_end(text)
    if dest is None:
        return None
    kind = _parse_load_kind(text)
    if kind is None:
        return None
    # צד לזיהוי העומס: האזכור שאינו חלק מיעד «קצה …»
    # מסירים את חלק היעד ואז מחפשים ימני/שמאלי
    text_for_side = _END_RIGHT_RE.sub(" ", text)
    text_for_side = _END_LEFT_RE.sub(" ", text_for_side)
    side = _parse_side_token(text_for_side)
    if side is None:
        # אם אין ימני/שמאלי אבל יש רק עומס אחד מהסוג — נבחר אותו
        side = "only"

    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    try:
        L = float(beam.get("L", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if L <= 0:
        return None
    loads = beam.get("loads")
    if not isinstance(loads, list) or not loads:
        return None

    candidates: list[tuple[int, dict]] = []
    for i, ld in enumerate(loads):
        if isinstance(ld, dict) and _load_matches_kind(ld, kind):
            candidates.append((i, ld))
    if not candidates:
        return None

    if side == "only":
        if len(candidates) != 1:
            return None
        idx = candidates[0][0]
    elif side == "right":
        idx = max(candidates, key=lambda it: _load_anchor_x(it[1]))[0]
    else:
        idx = min(candidates, key=lambda it: _load_anchor_x(it[1]))[0]

    target_x = L if dest == "right" else 0.0
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    chosen = dict(new_loads[idx])
    if str(chosen.get("type", "")).lower().strip() == "distributed":
        # לא מעבירים מפורס לקצה בפקודה הזו
        return None
    set_load_x_user(chosen, target_x)
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def apply_nl_draft_edit(extracted: dict, user_instruction: str) -> tuple[dict | None, list[str]]:
    """מעדכן extracted לפי טקסט חופשי. מחזיר (updated, errors)."""
    instruction = (user_instruction or "").strip()
    if not instruction:
        return None, ["כתוב מה לתקן בטיוטה."]

    current = extracted if isinstance(extracted, dict) else {}

    # פקודות ברורות — בלי Gemini (אמין יותר מפרשנות חופשית)
    resized = try_resize_distributed_load(current, instruction)
    if resized is not None:
        return _finalize_or_raw(resized), []

    moved = try_move_load_to_beam_end(current, instruction)
    if moved is not None:
        return _finalize_or_raw(moved), []

    added = try_add_load(current, instruction)
    if added is not None:
        return _finalize_or_raw(added), []

    verticalize = wants_inclined_to_vertical(instruction)

    try:
        current_json = json.dumps(current, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        current_json = "{}"

    prompt = _NL_EDIT_PROMPT.format(
        current_json=current_json,
        user_instruction=instruction,
    )

    parsed: dict | None = None
    gemini_error: str | None = None
    try:
        client, model = gemini_runtime()
        response = generate_content_with_retries(
            client,
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", None) or ""
        parsed = parse_json_from_llm_text(str(text))
    except Exception as exc:
        log.warning("Draft NL edit failed: %s", exc)
        gemini_error = friendly_gemini_error(exc)
        parsed = None

    if parsed is None:
        # בקשת המרה ברורה לאנכי — גם בלי Gemini מצליחים דטרמיניסטית
        if verticalize:
            updated = convert_inclined_loads_to_vertical(current)
            return _finalize_or_raw(updated), []
        return None, [gemini_error or "לא הצלחתי להבין את התיקון — נסה לנסח שוב."]

    if not isinstance(parsed, dict):
        if verticalize:
            updated = convert_inclined_loads_to_vertical(current)
            return _finalize_or_raw(updated), []
        return None, ["לא הצלחתי להבין את התיקון — נסה לנסח שוב."]

    beam = parsed.get("beam")
    if not isinstance(beam, dict):
        if "L" in parsed or "loads" in parsed or "supports" in parsed:
            parsed = {"exercise_type": "beam", "beam": parsed}
            beam = parsed["beam"]
        else:
            if verticalize:
                updated = convert_inclined_loads_to_vertical(current)
                return _finalize_or_raw(updated), []
            return None, ["התשובה מהמודל לא כוללת מודל קורה תקין."]

    if "exercise_type" not in parsed:
        parsed["exercise_type"] = current.get("exercise_type") or "beam"

    if isinstance(current.get("meta"), dict) and "meta" not in parsed:
        parsed["meta"] = dict(current["meta"])

    # אם ביקשו אנכי — כפה המרה גם אם Gemini השאיר inclined / Fx+Fy
    if verticalize:
        parsed = convert_inclined_loads_to_vertical(parsed)

    parsed = _lock_changed_distributed_spans(current, parsed)
    updated = _finalize_or_raw(parsed)
    if not isinstance(updated.get("beam"), dict):
        return None, ["לא הצלחתי לעדכן את הטיוטה — נסה שוב."]

    # אחרי finalize עלול _promote_diagonal_point_loads להחזיר inclined — כפה שוב
    if verticalize:
        updated = convert_inclined_loads_to_vertical(updated)
        updated = _finalize_or_raw(updated)
        # אם finalize שוב קידם ל-inclined, השאר את הגרסה האנכית בלי לקדם
        still = any(
            isinstance(ld, dict) and str(ld.get("type", "")).lower() == "inclined"
            for ld in (updated.get("beam") or {}).get("loads") or []
        )
        if still:
            updated = convert_inclined_loads_to_vertical(updated)

    return updated, []


def _finalize_or_raw(parsed: dict) -> dict:
    try:
        return finalize_beam_extraction(parsed, merge_nearby_point_loads=False)
    except Exception as exc:
        log.warning("Draft NL finalize failed: %s", exc)
        return parsed
