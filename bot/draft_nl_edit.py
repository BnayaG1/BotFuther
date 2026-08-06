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
    _sync_inclined_components,
    set_beam_L_user,
    set_distributed_span_user,
    set_load_x_user,
    set_support_x_user,
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

פעולות נתמכות (בחר אחת לפי ההוראה):
1) אורך קורה — שנה L (סמן _user_L).
2) הזזת עומס — ל-x= / לקצה / מטר ימינה-שמאלה (רק אותו עומס).
3) הגדלת/הקטנת מפורס — x1/x2 + _user_span.
4) הזזת סמך נייד/קבוע — supports בלבד, לא loads; סמן _user_x.
5) שינוי כיוון עומס — סימן Fx/Fy / incl_dir / M.
6) שינוי זווית אלכסוני — angle_deg + עדכון Fx/Fy (למשל «שנה זווית ל-45»).
7) המרת סוג עומס — למשל אלכסוני→אנכי, אנכי→מומנט.
8) הוספת/מחיקת עומס לפי הצורך.

מבנה פקודה מהמשתמש (פרש לפי הסדר הזה):
1) פקודה — מה לעשות: תשנה / תעביר / תוסיף / תמחק / תהפוך / תזיז וכו'.
2) יעד — סמך או עומס. אם כתוב «סמך» / «קבוע» / «נייד» / «נעץ» / «גליל» / «קיבוע»
   זה סמך (supports), לא עומס. אל תזיז עומס כשמבקשים סמך.
3) שם עומס (סוג) — מומנט / אלכסוני / משופע / צירי / אופקי / אנכי / נקודתי / מפורס.
4) זיהוי (רק אם צריך להבדיל) — למשל: הימני / השמאלי / בנקודה C /
   ב-x=5 / במשקל 15 טון / העומס השני / כל האלכסוניים.
5) תוצאה — המצב הרצוי אחרי השינוי: לאנכי / ל-8 טון / ל-x=3 / מטר ימינה /
   למעלה / לכיוון ↙ / מחק / זווית 45 וכו'.

סמכים (supports):
- «סמך קבוע» / «נעץ» → type=pin. «סמך נייד» / «גליל» → type=roller. «קיבוע» → type=fixed.
- «הזז את הסמך הקבוע מטר ימינה» → שנה רק x של הסמך pin (+1 מטר), סמן _user_x=true.
  אסור לגעת ב-loads.

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
_MOVE_VERB_RE = re.compile(
    r"תעביר|תזיז|העבר|הזיז|הזז|תעבירי|תזיזי",
    re.IGNORECASE,
)
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
    r"תאריך|שי?אריך|להאריך|האר[י]?ך|יאריך|הגדל|תגדיל|להגדיל|תגדילי",
    re.IGNORECASE,
)
_SHORTEN_RE = re.compile(
    r"תקצר|לקצר|תקצרי|הקטן|תקטין|להקטין|תקטיני",
    re.IGNORECASE,
)
_BEAM_L_EQ_RE = re.compile(r"\bL\s*=\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_BEAM_LENGTH_WORD_RE = re.compile(
    r"אורך\s*(?:של\s*)?ה?קורה|האורך|אורך\s*L|\bL\b",
    re.IGNORECASE,
)
_DIR_INTENT_RE = re.compile(
    r"כיוון|הפוך|תהפוך|החליף|↙|↘|←|→|↑|↓|למעלה|למטה",
    re.IGNORECASE,
)
_CHANGE_TYPE_VERB_RE = re.compile(
    r"שנה|תהפוך|הפוך|תעשה|המר|תחליף|להפוך|לשנות",
    re.IGNORECASE,
)
_ANGLE_INTENT_RE = re.compile(r"זווית|מעלות|°|degrees?|\bangle\b", re.IGNORECASE)
_ANGLE_WITH_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:°|מעלות|deg(?:rees)?)",
    re.IGNORECASE,
)
_ANGLE_AFTER_WORD_RE = re.compile(
    r"זווית\s*(?:של\s*)?(?:ה?(?:עומס|אלכסונ\w*|משופע\w*)\s*)?"
    r"(?:ל-?|=|:)?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
# יעד המרה: «לאנכי», «למומנט»…
_TARGET_LOAD_KIND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ל\s*(?:עומס\s*)?מומנט", re.I), "moment"),
    (re.compile(r"ל\s*(?:עומס\s*)?(?:אלכסונ|משופע)", re.I), "inclined"),
    (re.compile(r"ל\s*(?:עומס\s*)?(?:צירי|אופקי)", re.I), "axial"),
    (re.compile(r"ל\s*(?:עומס\s*)?(?:מפורס|מפולג)", re.I), "distributed"),
    (re.compile(r"ל\s*(?:עומס\s*)?(?:אנכי|נקודת)", re.I), "vertical"),
)
_KIND_TO_SETTABLE = {
    "vertical": "point",
    "axial": "axial",
    "moment": "moment",
    "distributed": "distributed",
    "inclined": "inclined",
}
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
_SUPPORT_WORD_RE = re.compile(r"סמך|תמיכ|supports?", re.IGNORECASE)
_DELTA_RIGHT_RE = re.compile(r"ימינה|לימין|לכיוון\s*ימין", re.IGNORECASE)
_DELTA_LEFT_RE = re.compile(r"שמאלה|לשמאל|לכיוון\s*שמאל", re.IGNORECASE)
_METER_AMOUNT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:מטר(?:ים)?|מ['׳]|m\b)",
    re.IGNORECASE,
)
_BARE_METER_RE = re.compile(r"מטר(?:ים)?|מ['׳]|m\b", re.IGNORECASE)
# שברים בעברית / ספרות להזזה מדויקת (חצי מטר, מטר וחצי, 0.5 ימינה…)
_THREE_QUARTERS_M_RE = re.compile(
    r"(?:ב-?\s*)?שלוש(?:ה|ת)?\s*רבע(?:י|ים)?(?:\s*(?:מטר(?:ים)?|מ['׳]|m\b))?",
    re.IGNORECASE,
)
_HALF_M_RE = re.compile(
    r"(?:ב-?\s*)?(?:חצי|½)(?:\s*(?:מטר(?:ים)?|מ['׳]|m\b))?",
    re.IGNORECASE,
)
_QUARTER_M_RE = re.compile(
    r"(?:ב-?\s*)?רבע(?:\s*(?:מטר(?:ים)?|מ['׳]|m\b))?",
    re.IGNORECASE,
)
_METER_AND_HALF_RE = re.compile(
    r"(?:ב-?\s*)?מטר(?:ים)?\s*וחצי",
    re.IGNORECASE,
)
_N_AND_HALF_M_RE = re.compile(
    r"(?:ב-?\s*)?(\d+(?:[.,]\d+)?|אחד|אחת|שניים|שנים|שתיים|שתי|שלושה|שלוש|"
    r"ארבעה|ארבע|חמישה|חמש)\s*(?:מטר(?:ים)?\s*)?וחצי"
    r"(?:\s*(?:מטר(?:ים)?|מ['׳]|m\b))?",
    re.IGNORECASE,
)
_FRAC_SLASH_M_RE = re.compile(
    r"(?:ב-?\s*)?(\d+)\s*/\s*(\d+)(?:\s*(?:מטר(?:ים)?|מ['׳]|m\b))?",
    re.IGNORECASE,
)
_BARE_NUM_BEFORE_DIR_RE = re.compile(
    r"(?:ב-?\s*)?(\d+(?:[.,]\d+)?)\s*(?=ימינה|שמאלה|לימין|לשמאל)",
    re.IGNORECASE,
)
_HEB_INT_WORDS: dict[str, float] = {
    "אחד": 1.0,
    "אחת": 1.0,
    "שניים": 2.0,
    "שנים": 2.0,
    "שתיים": 2.0,
    "שתי": 2.0,
    "שלושה": 3.0,
    "שלוש": 3.0,
    "ארבעה": 4.0,
    "ארבע": 4.0,
    "חמישה": 5.0,
    "חמש": 5.0,
}
# (regex על סוג סמך בעברית, type פנימי) — קיבוע לפני קבוע
_SUPPORT_KIND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"קיבוע|רתום|fixed", re.I), "fixed"),
    (re.compile(r"קבוע|נעץ|pin", re.I), "pin"),
    (re.compile(r"נייד|גליל|roller", re.I), "roller"),
)

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
    """דלתא במטרים: «ב-2 מטר», «בחצי מטר», «ב2 מטרים»."""
    m = _BY_DELTA_RE.search(text)
    if m:
        return _parse_float_token(m.group(1))
    # שברים מילוליים: «בחצי מטר», «ברבע מטר»
    if re.search(r"ב-?\s*(?:חצי|רבע|שלוש|½)", text, re.IGNORECASE):
        return _parse_move_amount_m(text)
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


def _pick_load_index(
    loads: list,
    text: str,
    kind: str | None,
    *,
    allow_distributed: bool = False,
) -> int | None:
    """בחירת עומס לפי סוג + ימני/שמאלי / יחיד."""
    candidates: list[tuple[int, dict]] = []
    for i, ld in enumerate(loads):
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower().strip()
        if not allow_distributed and t == "distributed":
            continue
        if kind is not None:
            if not _load_matches_kind(ld, kind):
                continue
        candidates.append((i, ld))
    if not candidates:
        return None
    text_for_side = _END_RIGHT_RE.sub(" ", text)
    text_for_side = _END_LEFT_RE.sub(" ", text_for_side)
    text_for_side = _DELTA_RIGHT_RE.sub(" ", text_for_side)
    text_for_side = _DELTA_LEFT_RE.sub(" ", text_for_side)
    side = _parse_side_token(text_for_side)
    if side is None:
        if len(candidates) != 1:
            return None
        return candidates[0][0]
    if side == "right":
        return max(candidates, key=lambda it: _load_anchor_x(it[1]))[0]
    return min(candidates, key=lambda it: _load_anchor_x(it[1]))[0]


def try_set_beam_length(extracted: dict, user_instruction: str) -> dict | None:
    """שינוי אורך הקורה L — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text:
        return None
    # לא לגנוב «שנה אורך של עומס מפורס»
    if _DIST_WORD_RE.search(text) and not re.search(r"קורה", text, re.IGNORECASE):
        return None

    new_L: float | None = None
    m_eq = _BEAM_L_EQ_RE.search(text)
    if m_eq:
        new_L = _parse_float_token(m_eq.group(1))
    elif _BEAM_LENGTH_WORD_RE.search(text):
        lm = _LENGTH_TO_RE.search(text)
        if lm:
            new_L = _parse_float_token(lm.group(1))
        else:
            meter_m = _METER_AMOUNT_RE.search(text)
            if meter_m:
                new_L = _parse_float_token(meter_m.group(1))
            else:
                nums = list(_NUM_RE.finditer(text))
                if len(nums) == 1:
                    new_L = _parse_float_token(nums[0].group(1))
    if new_L is None or new_L <= 0:
        return None

    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    try:
        old_L = float(beam.get("L", 0.0) or 0.0)
    except (TypeError, ValueError):
        old_L = 0.0
    if abs(old_L - float(new_L)) < 1e-9:
        return None
    beam = dict(beam)
    set_beam_L_user(beam, float(new_L))
    data["beam"] = beam
    return data


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


def _parse_support_kind(text: str) -> str | None:
    for pat, kind in _SUPPORT_KIND_PATTERNS:
        if pat.search(text):
            return kind
    return None


def _heb_int_token(raw: str) -> float | None:
    s = str(raw or "").strip().lower()
    if s in _HEB_INT_WORDS:
        return _HEB_INT_WORDS[s]
    return _parse_float_token(s)


def _parse_move_amount_m(text: str) -> float | None:
    """כמה מטרים להזיז — תומך בחצי/רבע/מטר וחצי/0.5/1/2 וגם מספר ליד ימינה/שמאלה."""
    if not text:
        return None
    if _THREE_QUARTERS_M_RE.search(text):
        return 0.75
    m_nh = _N_AND_HALF_M_RE.search(text)
    if m_nh:
        base = _heb_int_token(m_nh.group(1) or "1")
        if base is not None and base >= 0:
            return float(base) + 0.5
    if _METER_AND_HALF_RE.search(text):
        return 1.5
    if _HALF_M_RE.search(text):
        return 0.5
    if _QUARTER_M_RE.search(text):
        return 0.25
    m_frac = _FRAC_SLASH_M_RE.search(text)
    if m_frac:
        num = _parse_float_token(m_frac.group(1))
        den = _parse_float_token(m_frac.group(2))
        if num is not None and den is not None and den > 0:
            val = float(num) / float(den)
            if val > 0:
                return val
    m = _METER_AMOUNT_RE.search(text)
    if m:
        mag = _parse_float_token(m.group(1))
        if mag is not None and mag > 0:
            return mag
    m_bare_num = _BARE_NUM_BEFORE_DIR_RE.search(text)
    if m_bare_num:
        mag = _parse_float_token(m_bare_num.group(1))
        if mag is not None and mag > 0:
            return mag
    # «מטר ימינה» בלי מספר = 1 — רק אם אין שבר מילולי שכבר טופל
    if _BARE_METER_RE.search(text):
        return 1.0
    return None


def _parse_relative_move_delta_m(text: str) -> float | None:
    """דלתא במטרים: ימינה=+ , שמאלה=- . «מטר ימינה» בלי מספר = 1."""
    if _DELTA_RIGHT_RE.search(text):
        sign = 1.0
    elif _DELTA_LEFT_RE.search(text):
        sign = -1.0
    else:
        return None
    mag = _parse_move_amount_m(text)
    if mag is None or mag <= 0:
        return None
    return sign * mag


def _support_x(sup: dict) -> float:
    try:
        return float(sup.get("x", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def try_move_support(extracted: dict, user_instruction: str) -> dict | None:
    """הזזת סמך יחסית (מטר ימינה/שמאלה) או ל-x= — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text or not _MOVE_VERB_RE.search(text):
        return None
    kind = _parse_support_kind(text)
    has_support_word = bool(_SUPPORT_WORD_RE.search(text))
    if not has_support_word and kind is None:
        return None
    # אם זה בבירור פקודת עומס בלי מילת סמך — לא תופסים
    if _parse_load_kind(text) is not None and not has_support_word:
        return None

    delta = _parse_relative_move_delta_m(text)
    x_abs = _parse_explicit_x(text)
    if delta is None and x_abs is None:
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
    supports = beam.get("supports")
    if not isinstance(supports, list) or not supports:
        return None

    candidates: list[tuple[int, dict]] = []
    for i, sup in enumerate(supports):
        if not isinstance(sup, dict):
            continue
        st = str(sup.get("type", "")).lower().strip()
        if kind is not None and st != kind:
            continue
        candidates.append((i, sup))
    if not candidates:
        return None

    # «ימינה/שמאלה» = כיוון הזזה, לא בחירת סמך ימני/שמאלי
    text_for_side = _DELTA_RIGHT_RE.sub(" ", text)
    text_for_side = _DELTA_LEFT_RE.sub(" ", text_for_side)
    side = _parse_side_token(text_for_side)
    if len(candidates) == 1:
        idx = candidates[0][0]
    elif side == "right":
        idx = max(candidates, key=lambda it: _support_x(it[1]))[0]
    elif side == "left":
        idx = min(candidates, key=lambda it: _support_x(it[1]))[0]
    elif kind is not None:
        # סוג יחיד תואם כבר סונן; אם נשארו כמה מאותו סוג בלי צד — לא לנחש
        if len(candidates) != 1:
            return None
        idx = candidates[0][0]
    else:
        return None

    chosen = supports[idx]
    if not isinstance(chosen, dict):
        return None
    cur_x = _support_x(chosen)
    if x_abs is not None:
        new_x = x_abs
    else:
        new_x = cur_x + float(delta)
    new_x = max(0.0, min(L, new_x))

    beam = dict(beam)
    beam["supports"] = [dict(s) if isinstance(s, dict) else s for s in supports]
    # בלי label — כדי לא לדרוס labeled_points ולהפעיל re-zero שמוחק את ההזזה
    set_support_x_user(beam, new_x, index=idx)
    # עוגן קצה שמאל ב-0 כדי ש-finalize לא יזיז את מערכת הצירים אחרי overhang
    kp_raw = beam.get("key_points_m")
    kp: list[float] = []
    if isinstance(kp_raw, list):
        for p in kp_raw:
            try:
                kp.append(float(p))
            except (TypeError, ValueError):
                continue
    if not any(abs(p) < 1e-9 for p in kp):
        kp.append(0.0)
    if not any(abs(p - L) < 1e-9 for p in kp):
        kp.append(L)
    beam["key_points_m"] = kp
    data["beam"] = beam
    return data


def try_move_load(extracted: dict, user_instruction: str) -> dict | None:
    """העברת עומס ל-x= / לקצה קורה / בדלתא ימינה-שמאלה — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text or not _MOVE_VERB_RE.search(text):
        return None
    if _SUPPORT_WORD_RE.search(text):
        return None
    # «הזז קבוע…» בלי מילת עומס — לא כאן (סמך)
    if _parse_support_kind(text) is not None and _parse_load_kind(text) is None:
        return None

    dest = _parse_dest_end(text)
    x_abs = _parse_explicit_x(text)
    delta = _parse_relative_move_delta_m(text)
    if dest is None and x_abs is None and delta is None:
        return None

    kind = _parse_load_kind(text)
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

    idx = _pick_load_index(loads, text, kind, allow_distributed=False)
    if idx is None:
        return None

    chosen = dict(loads[idx])
    if str(chosen.get("type", "")).lower().strip() == "distributed":
        return None

    cur_x = _load_anchor_x(chosen)
    if x_abs is not None:
        target_x = x_abs
    elif dest is not None:
        target_x = L if dest == "right" else 0.0
    else:
        target_x = cur_x + float(delta)
    target_x = max(0.0, min(L, float(target_x)))
    if abs(target_x - cur_x) < 1e-9:
        return None

    set_load_x_user(chosen, target_x)
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def try_move_load_to_beam_end(extracted: dict, user_instruction: str) -> dict | None:
    """תאימות לאחור — העברה לקצה הקורה דרך try_move_load."""
    text = (user_instruction or "").strip()
    if not text or _parse_dest_end(text) is None:
        return None
    return try_move_load(extracted, user_instruction)


def _parse_target_load_kind(text: str) -> str | None:
    for pat, kind in _TARGET_LOAD_KIND_PATTERNS:
        if pat.search(text):
            return kind
    return None


def _parse_source_load_kind(text: str, target_kind: str | None) -> str | None:
    """סוג מקור — מתעלם ממילות היעד («לאנכי»)."""
    cleaned = text
    for pat, _kind in _TARGET_LOAD_KIND_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    kind = _parse_load_kind(cleaned)
    if kind is not None:
        return kind
    if target_kind is not None and wants_inclined_to_vertical(text):
        return "inclined"
    return None


def _parse_inclined_angle_deg(text: str) -> float | None:
    """מחלץ זווית במעלות מפקודה כמו «שנה זווית ל-45» / «זווית 30 מעלות»."""
    if not text or not _ANGLE_INTENT_RE.search(text):
        return None
    m = _ANGLE_WITH_UNIT_RE.search(text)
    if m:
        angle = _parse_float_token(m.group(1))
    else:
        m = _ANGLE_AFTER_WORD_RE.search(text)
        if m:
            angle = _parse_float_token(m.group(1))
        else:
            m = re.search(r"(?:ל-?|=|:)\s*(\d+(?:[.,]\d+)?)", text)
            if m:
                angle = _parse_float_token(m.group(1))
            else:
                nums = list(_NUM_RE.finditer(text))
                if len(nums) != 1:
                    return None
                angle = _parse_float_token(nums[0].group(1))
    if angle is None or angle <= 0 or angle >= 90:
        return None
    return float(angle)


def try_set_inclined_angle(extracted: dict, user_instruction: str) -> dict | None:
    """שינוי זווית לעומס אלכסוני — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text:
        return None
    angle = _parse_inclined_angle_deg(text)
    if angle is None:
        return None
    # לא לבלבל עם המרת סוג («שנה לאנכי»)
    if _parse_target_load_kind(text) is not None:
        return None

    kind = _parse_load_kind(text)
    if kind is not None and kind != "inclined":
        return None

    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    loads = beam.get("loads")
    if not isinstance(loads, list) or not loads:
        return None

    idx = _pick_load_index(loads, text, "inclined", allow_distributed=False)
    if idx is None:
        return None

    chosen = dict(loads[idx])
    if str(chosen.get("type", "")).lower().strip() != "inclined":
        return None
    try:
        cur_angle = float(chosen.get("angle_deg", 30.0) or 30.0)
    except (TypeError, ValueError):
        cur_angle = 30.0
    if abs(cur_angle - angle) < 1e-9:
        return None

    chosen["angle_deg"] = angle
    chosen = _sync_inclined_components(chosen)
    chosen["_user_mag"] = True
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def try_flip_load_direction(extracted: dict, user_instruction: str) -> dict | None:
    """שינוי/היפוך כיוון עומס — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text or not _DIR_INTENT_RE.search(text):
        return None
    # המרת סוג («שנה לאנכי») — לא היפוך כיוון
    if _parse_target_load_kind(text) is not None:
        return None
    if _SUPPORT_WORD_RE.search(text):
        return None

    kind = _parse_load_kind(text)
    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    loads = beam.get("loads")
    if not isinstance(loads, list) or not loads:
        return None

    idx = _pick_load_index(loads, text, kind, allow_distributed=True)
    if idx is None:
        return None

    from bot.draft_editor import toggle_any_load_direction

    want_dl = bool(re.search(r"↙|dl\b|לכיוון\s*שמאל|שמאלה", text, re.I))
    want_dr = bool(re.search(r"↘|dr\b|לכיוון\s*ימין|ימינה", text, re.I))
    want_up = bool(re.search(r"למעלה|↑", text, re.I))
    want_down = bool(re.search(r"למטה|↓", text, re.I))
    want_left = bool(re.search(r"←|שמאלה|לשמאל", text, re.I)) and not want_dl
    want_right = bool(re.search(r"→|ימינה|לימין", text, re.I)) and not want_dr

    chosen = dict(loads[idx])
    t = str(chosen.get("type", "")).lower().strip()

    # כיוון מפורש לאלכסוני
    if t == "inclined" and (want_dl or want_dr):
        import math

        target_dir = "dl" if want_dl else "dr"
        cur = str(chosen.get("incl_dir", "") or "").lower()
        if cur == target_dir:
            return None
        mag = float(chosen.get("magnitude_ton") or 0.0)
        if mag < 1e-6:
            mag = math.hypot(
                float(chosen.get("Fx", 0) or 0),
                float(chosen.get("Fy", 0) or 0),
            )
        angle = float(chosen.get("angle_deg", 30) or 30)
        rad = math.radians(angle)
        fx_mag = mag * math.cos(rad)
        fy_mag = mag * math.sin(rad)
        if target_dir == "dl":
            chosen["Fx"], chosen["Fy"] = -abs(fx_mag), abs(fy_mag)
        else:
            chosen["Fx"], chosen["Fy"] = abs(fx_mag), abs(fy_mag)
        chosen["incl_dir"] = target_dir
        chosen["magnitude_ton"] = mag
        new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
        new_loads[idx] = chosen
        beam = dict(beam)
        beam["loads"] = new_loads
        data["beam"] = beam
        return data

    # כיוון מפורש לצירי
    if _is_axial_point(chosen) and (want_left or want_right):
        try:
            fx = float(chosen.get("Fx", chosen.get("fx", 0.0)) or 0.0)
        except (TypeError, ValueError):
            fx = 0.0
        mag = abs(fx) if abs(fx) >= 1e-9 else 5.0
        new_fx = -mag if want_left else mag
        if abs(new_fx - fx) < 1e-9:
            return None
        chosen["Fx"] = new_fx
        chosen["Fy"] = 0.0
        new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
        new_loads[idx] = chosen
        beam = dict(beam)
        beam["loads"] = new_loads
        data["beam"] = beam
        return data

    # אנכי למעלה/למטה
    if _is_vertical_point(chosen) and (want_up or want_down):
        try:
            fy = float(chosen.get("Fy", chosen.get("fy", 0.0)) or 0.0)
        except (TypeError, ValueError):
            fy = 0.0
        mag = abs(fy) if abs(fy) >= 1e-9 else 5.0
        # Fy חיובי = מטה
        new_fy = -mag if want_up else mag
        if abs(new_fy - fy) < 1e-9:
            return None
        chosen["Fy"] = new_fy
        chosen["Fx"] = 0.0
        new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
        new_loads[idx] = chosen
        beam = dict(beam)
        beam["loads"] = new_loads
        data["beam"] = beam
        return data

    # ברירת מחדל — היפוך
    if not re.search(r"הפוך|תהפוך|החליף|שנה\s+כיוון|כיוון", text, re.I):
        return None
    out = toggle_any_load_direction(data, idx + 1)
    if out is data:
        return None
    return out


def try_change_load_type(extracted: dict, user_instruction: str) -> dict | None:
    """המרת סוג עומס (למשל אלכסוני→אנכי) — דטרמיניסטי."""
    text = (user_instruction or "").strip()
    if not text:
        return None
    target_kind = _parse_target_load_kind(text)
    if target_kind is None and wants_inclined_to_vertical(text):
        target_kind = "vertical"
    if target_kind is None:
        return None
    if not _CHANGE_TYPE_VERB_RE.search(text) and not wants_inclined_to_vertical(text):
        return None

    source_kind = _parse_source_load_kind(text, target_kind)
    settable = _KIND_TO_SETTABLE.get(target_kind)
    if settable is None:
        return None

    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None
    loads = beam.get("loads")
    if not isinstance(loads, list) or not loads:
        return None

    # «האלכסוניים» / «כל האלכסוניים» לאנכי — כל האלכסוניים
    if source_kind == "inclined" and target_kind == "vertical" and re.search(
        r"אלכסוניים|משופעים|כל\s+ה(?:עומסים\s+)?ה?(?:אלכסונ|משופע)",
        text,
        re.I,
    ):
        return convert_inclined_loads_to_vertical(data)

    idx = _pick_load_index(
        loads,
        text,
        source_kind,
        allow_distributed=True,
    )
    if idx is None and source_kind is None:
        # יעד בלבד + עומס יחיד
        idx = _pick_load_index(loads, text, None, allow_distributed=True)
    if idx is None and source_kind == "inclined" and target_kind == "vertical":
        # כל האלכסוניים אם אין בחירה בודדת ברורה
        inclined_idxs = [
            i
            for i, ld in enumerate(loads)
            if isinstance(ld, dict) and _load_matches_kind(ld, "inclined")
        ]
        if not inclined_idxs:
            return None
        if len(inclined_idxs) == 1:
            idx = inclined_idxs[0]
        else:
            return convert_inclined_loads_to_vertical(data)
    if idx is None:
        return None

    from bot.draft_editor import load_picker_kind, set_load_type

    cur = loads[idx]
    if not isinstance(cur, dict):
        return None
    if load_picker_kind(cur) == settable:
        return None
    return set_load_type(data, idx + 1, settable)


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

    lengthened = try_set_beam_length(current, instruction)
    if lengthened is not None:
        return _finalize_or_raw(lengthened), []

    moved_support = try_move_support(current, instruction)
    if moved_support is not None:
        return _finalize_or_raw(moved_support), []

    moved = try_move_load(current, instruction)
    if moved is not None:
        return _finalize_or_raw(moved), []

    angled = try_set_inclined_angle(current, instruction)
    if angled is not None:
        return _finalize_or_raw(angled), []

    flipped = try_flip_load_direction(current, instruction)
    if flipped is not None:
        return _finalize_or_raw(flipped), []

    typed = try_change_load_type(current, instruction)
    if typed is not None:
        return _finalize_or_raw(typed), []

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
