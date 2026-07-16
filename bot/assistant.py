# -*- coding: utf-8 -*-
"""עוזר אישי — בחירת מצב פתרון והדרכה שלב-אחר-שלב (בלי מחברת מלאה מיד)."""
from __future__ import annotations

import logging
import math
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.draft_format import (
    _fmt_num,
    _inclined_dir,
    _inclined_mag,
    distributed_span_from_left,
)
from bot.solution_session import (
    AssistantProgress,
    SolveMode,
    append_assistant_message_id,
    get_assistant_last_screen,
    get_assistant_progress,
    get_solve_mode,
    has_active_assistant_progress,
    has_assistant_prev_state,
    pop_assistant_message_ids,
    pop_assistant_prev_state,
    push_assistant_prev_state,
    clear_assistant_prev_stack,
    set_assistant_beam_kind,
    set_assistant_progress,
    set_assistant_last_screen,
    set_pending_solve_mode,
)
from bot.vision import set_draft_error_message_id
from bot.vision import (
    infer_vision_exercise_type,
    resolve_beam_support_geometry,
)

log = logging.getLogger("beam_telegram_bot")

SendTextFn = Callable[..., Awaitable[object]]
EditDraftFn = Callable[..., Awaitable[None]]
DeliverNotebookFn = Callable[..., Awaitable[None]]

_ASSISTANT_EXPLAIN = "explain"
_ASSISTANT_NEXT = "next"
_ASSISTANT_CHOOSE = "choose"
_ASSISTANT_BACK = "back"
_ASSISTANT_SHOW = "show"
_ASSISTANT_YES = "yes"
_ASSISTANT_PREV = "prev"
_DECOMPOSE_TYPES = frozenset({"distributed", "inclined"})
_FRIENDLY_PREFIXES = ("מעולה, ", "מעולה — ")
_ENCOURAGEMENT_WORDS: tuple[str, ...] = (
    "מעולה",
    "יופי",
    "איזה יופי",
    "מצוין",
    "יפה מאד",
    "קטלני",
    "טיל",
    "מטורף אתה",
    "מקסים",
    "מהמם",
    "כל הכבוד",
    "אין עליך",
    "יאללה בוא נמשיך",
    "קדימה בוא נמשיך",
)
_STEP_ORDINALS: dict[int, str] = {
    1: "הראשון",
    2: "השני",
    3: "השלישי",
    4: "הרביעי",
    5: "החמישי",
    6: "השישי",
    7: "השביעי",
    8: "השמיני",
    9: "התשיעי",
    10: "העשירי",
}
_LOAD_ORDINALS: dict[int, str] = {
    1: "הראשון",
    2: "השני",
    3: "השלישי",
    4: "הרביעי",
    5: "החמישי",
    6: "השישי",
    7: "השביעי",
}


def step_ordinal_hebrew(step_no: int) -> str:
    """מחזיר 'הראשון', 'השני' וכו' לפי מספר שלב (1-based)."""
    return _STEP_ORDINALS.get(step_no, f"ה-{step_no}")


def step_phrase_hebrew(step_no: int, *, total: int | None = None) -> str:
    """למשל 'השלב הראשון' או 'השלב השני מתוך 7'."""
    phrase = f"השלב {step_ordinal_hebrew(step_no)}"
    if total is not None and total > 1:
        return f"{phrase} מתוך {total}"
    return phrase


def load_ordinal_hebrew(part: int) -> str:
    return _LOAD_ORDINALS.get(part, f"ה-{part}")


def collaborative_continue_prompt() -> str:
    return "רוצה הסבר, או שנמשיך?"


def distributed_decomposition_context_hebrew() -> str:
    return (
        "בשביל לפתור את המשך התרגיל, אנחנו נצטרך למצוא את מה שנקרא העומס השקול של העומס "
        "ואיתו נעבוד כשנרצה למצוא את הריאקציות בהמשך."
    )


def inclined_decomposition_context_hebrew() -> str:
    return (
        "בשביל לפתור את המשך התרגיל, אנחנו נצטרך לפרק את העומס האלכסוני לרכיבים אופקיים ואנכיים, "
        "ואיתם נעבוד כשנרצה למצוא את הריאקציות בהמשך."
    )


def decomposition_continue_prompt() -> str:
    return "רוצה הסבר איך לפרוק אותו, או שנמשיך?"


def decomposition_context_hebrew(ld: dict) -> str:
    load_type = str(ld.get("type", "")).lower()
    if load_type == "distributed":
        return distributed_decomposition_context_hebrew()
    if load_type == "inclined":
        return inclined_decomposition_context_hebrew()
    return (
        "בשביל לפתור את המשך התרגיל, נצטרך לפרק את העומס "
        "לפני שממשיכים לחישוב הריאקציות."
    )


def strip_friendly_opener(text: str) -> str:
    """מסיר פתיח 'מעולה' מתחילת טקסט."""
    for prefix in _FRIENDLY_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    if text.startswith("מעולה,"):
        return text[6:].lstrip()
    return text


def apply_friendly_opener(text: str, *, friendly: bool) -> str:
    """מוסיף או מסיר פתיח 'מעולה' לפי הצורך."""
    body = strip_friendly_opener(text)
    if not friendly:
        return body
    if not body:
        return "מעולה"
    return f"מעולה, {body}"


def encouragement_prefix_hebrew() -> str:
    """מחזיר פתיח רנדומלי כמו 'יופי,' כדי להתחיל הודעת המשך."""
    return f"{random.choice(_ENCOURAGEMENT_WORDS)},"


class AssistantBeamKind(str, Enum):
    """סוג תרגיל קורה לעוזר אישי."""

    SIMPLY_SUPPORTED = "simply_supported"
    CANTILEVER = "cantilever"
    UNKNOWN = "unknown"


# תרגיל הדגמה לכפתור מאסטר — סמך קבוע (נעץ) ב-x=2, סמך נייד (גליל) ב-x=9.
MASTER_DEMO_EXTRACTED: dict = {
    "exercise_type": "beam",
    "beam": {
        "L": 9.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 2.0},
            {"label": "B", "type": "roller", "x": 9.0},
        ],
        "loads": [
            {"type": "distributed", "x1": 0.0, "x2": 5.0, "w": 3.0},
            {"type": "distributed", "x1": 5.0, "x2": 9.0, "w": 1.0},
            {"type": "moment", "x": 5.0, "M": 4.0},
            {"type": "point", "x": 6.0, "Fy": 2.0},
        ],
    },
}


@dataclass(frozen=True)
class AssistantStep:
    number: int
    title: str


_ASSISTANT_STEPS: dict[AssistantBeamKind, tuple[AssistantStep, ...]] = {
    AssistantBeamKind.SIMPLY_SUPPORTED: (
        AssistantStep(1, "פרוק עומסים (מפורסים ואלכסוניים)"),
        AssistantStep(2, "מציאת ריאקציות"),
        AssistantStep(3, "שרטוט דיאגרמת גוף חופשי (D.F.D)"),
        AssistantStep(4, "משוואות שיווי משקל — ΣFx=0 ו-ΣFy=0"),
        AssistantStep(5, "בניית דיאגרמת גזירה Q(x)"),
        AssistantStep(6, "בניית דיאגרמת מומנט M(x)"),
        AssistantStep(7, "חישובי נקודות וערכי קיצון"),
    ),
    AssistantBeamKind.CANTILEVER: (
        AssistantStep(1, "פרוק עומסים (מפורסים ואלכסוניים)"),
        AssistantStep(2, "מציאת ריאקציות"),
        AssistantStep(3, "שרטוט דיאגרמת גוף חופשי (D.F.D)"),
        AssistantStep(4, "משוואות שיווי משקל בריתום — Rx, Ry, M"),
        AssistantStep(5, "בניית דיאגרמת גזירה Q(x)"),
        AssistantStep(6, "בניית דיאגרמת מומנט M(x)"),
        AssistantStep(7, "חישובי נקודות לאורך הקורה"),
    ),
    AssistantBeamKind.UNKNOWN: (
        AssistantStep(1, "פרוק עומסים (מפורסים ואלכסוניים)"),
        AssistantStep(2, "מציאת ריאקציות"),
        AssistantStep(3, "בניית דיאגרמת גוף חופשי"),
        AssistantStep(4, "בניית דיאגרמות Q(x) ו-M(x)"),
    ),
}


_STEP_PROCEDURE_EXPLAIN: dict[str, str] = {
    "מציאת ריאקציות": (
        "בשלב הזה נמצא את הריאקציות בסמכים/בריתום בעזרת שיווי משקל.\n"
        "נפתור אותן בתתי-שלבים, כל פעם ריאקציה אחת."
    ),
    "זיהוי הריתום והגפה החופשית": (
        "קודם נזהה איפה הריתום ואיפה הגפה החופשית.\n"
        "בריתום יש בדרך כלל שלוש ריאקציות (אופקית, אנכית ומומנט), "
        "ובגפה החופשית אין סמך."
    ),
    "שרטוט דיאגרמת גוף חופשי (D.F.D)": (
        "נשרטט את הקורה ונראה עליה את כל העומסים אחרי הפרוק,\n"
        "וגם את הריאקציות בסמכים — לרוב מסמנים אותן ככוחות לא ידועים."
    ),
    "בניית דיאגרמת גוף חופשי": (
        "נשרטט את הקורה ונראה עליה את כל העומסים והריאקציות,\n"
        "בלי לחשב עדיין את הערכים המספריים."
    ),
    "משוואות שיווי משקל — ΣFx=0 ו-ΣFy=0": (
        "נכתוב שיווי משקל לגוף החופשי:\n"
        "סכום הכוחות האופקיים שווה אפס, וסכום הכוחות האנכיים שווה אפס."
    ),
    "משוואות שיווי משקל בריתום — Rx, Ry, M": (
        "נכתוב שיווי משקל בנקודת הריתום:\n"
        "סכום כוחות אופקיים, סכום כוחות אנכיים, וסכום מומנטים שווה אפס."
    ),
    "חישוב ריאקציות בסמך A ובסמך B": (
        "נשתמש במשוואות שיווי המשקל כדי למצוא את הריאקציות בשני הסמכים.\n"
        "לפעמים נוח להתחיל מסכום מומנטים סביב אחד הסמכים."
    ),
    "חישוב ריאקציות": (
        "נשתמש במשוואות שיווי המשקל כדי למצוא את הריאקציות.\n"
        "נבחר נקודת מומנטים שנוחה לחישוב."
    ),
    "בניית דיאגרמת גזירה Q(x)": (
        "נבנה את דיאגרמת הגזירה לאורך הקורה:\n"
        "עוברים מקטע-מקטע, מתחשבים בעומסים ובשינויי כוח, "
        "ומסמנים את ערכי הגזירה בכל אזור."
    ),
    "בניית דיאגרמת מומנט M(x)": (
        "נבנה את דיאגרמת המומנט לאורך הקורה:\n"
        "מתחילים ממומנט ידוע (לרוב באחד הסמכים) ומצטברים מומנטים מקטע אחר מקטע."
    ),
    "בניית דיאגרמות Q(x) ו-M(x)": (
        "קודם נבנה את דיאגרמת הגזירה Q(x), ואחר כך את דיאגרמת המומנט M(x) "
        "לאורך הקורה."
    ),
    "חישובי נקודות וערכי קיצון": (
        "נאתר נקודות חשובות לאורך הקורה — סמכים, עומסים, ונקודות שבהן הגזירה מתאפסת.\n"
        "בנקודות האלה נחשב ערכי מומנט ונזהה ערכי קיצון."
    ),
    "חישובי נקודות לאורך הקורה": (
        "נאתר נקודות חשובות לאורך הקורה — ריתום, עומסים, ונקודות שבהן הגזירה מתאפסת.\n"
        "בנקודות האלה נחשב ערכי מומנט ונבדוק ערכים מיוחדים."
    ),
}


def solve_mode_picker_intro_hebrew() -> str:
    return "מעולה, בוא/י נבחר איך לפתור את התרגיל."


def build_solve_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📓 פתרון מחברת", callback_data="menu:mode:notebook")],
            [InlineKeyboardButton("🧑‍🏫 עוזר אישי", callback_data="menu:mode:assistant")],
            [InlineKeyboardButton("◀️ חזרה", callback_data="formula:back")],
        ]
    )


def build_bank_solve_mode_keyboard() -> InlineKeyboardMarkup:
    """בחירת מצב פתרון לתרגיל שנשלף מהמאגר (בלי כפתור חזרה — אין טיוטה קודמת)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📓 פתרון מחברת", callback_data="menu:bank:notebook")],
            [InlineKeyboardButton("🧑‍🏫 עוזר אישי", callback_data="menu:bank:assistant")],
        ]
    )


def build_assistant_step_keyboard(
    *,
    include_explain: bool = True,
    include_show_solution: bool = False,
    include_prev: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if include_prev:
        rows.append([InlineKeyboardButton("↩️", callback_data="assist:prev")])
    if include_explain:
        rows.append([InlineKeyboardButton("הסבר לי", callback_data="assist:explain")])
    if include_show_solution:
        rows.append([InlineKeyboardButton("הצג פתרון", callback_data="assist:show")])
    rows.append([InlineKeyboardButton("המשך", callback_data="assist:next")])
    rows.append([InlineKeyboardButton("בחר שלב", callback_data="assist:choose")])
    return InlineKeyboardMarkup(rows)


def _reaction_substeps_for_kind(kind: AssistantBeamKind) -> tuple[str, str, str]:
    if kind == AssistantBeamKind.SIMPLY_SUPPORTED:
        return ("Ax", "Ay", "By")
    return ("Ax", "Ma", "Ay")


def build_reactions_step_keyboard(
    progress: AssistantProgress,
    *,
    include_explain: bool = True,
    include_prev: bool = False,
    include_show_solution: bool = False,
    include_yes: bool = False,
) -> InlineKeyboardMarkup:
    """שלב 2: עמודה שמאלית תתי-שלבים + עמודה ימנית פעולות."""
    kind = AssistantBeamKind(progress.beam_kind)
    subs = _reaction_substeps_for_kind(kind)
    left = [
        InlineKeyboardButton(subs[0], callback_data="assist:sub:0"),
        InlineKeyboardButton(subs[1], callback_data="assist:sub:1"),
        InlineKeyboardButton(subs[2], callback_data="assist:sub:2"),
    ]

    # עמודה ימנית: גם מלמעלה למטה
    right: list[InlineKeyboardButton] = []
    show_on_bottom = False
    if include_explain:
        right = [
            InlineKeyboardButton("הסבר לי", callback_data="assist:explain"),
            InlineKeyboardButton("המשך", callback_data="assist:next"),
            InlineKeyboardButton("בחר שלב", callback_data="assist:choose"),
        ]
    elif include_show_solution and not include_yes:
        # מול Ax/Ay/By: הצג פתרון, המשך, בחר שלב
        right = [
            InlineKeyboardButton("הצג פתרון", callback_data="assist:show"),
            InlineKeyboardButton("המשך", callback_data="assist:next"),
            InlineKeyboardButton("בחר שלב", callback_data="assist:choose"),
        ]
    else:
        if include_yes:
            right.append(InlineKeyboardButton("כן", callback_data="assist:yes"))
        right.extend(
            [
                InlineKeyboardButton("המשך", callback_data="assist:next"),
                InlineKeyboardButton("בחר שלב", callback_data="assist:choose"),
            ]
        )
        # כשיש גם «כן» וגם «הצג פתרון» — הצג נשאר בשורה נפרדת למטה
        show_on_bottom = include_show_solution

    rows: list[list[InlineKeyboardButton]] = []
    if include_prev:
        rows.append([InlineKeyboardButton("↩️", callback_data="assist:prev")])
    for i in range(3):
        row = [left[i]]
        if i < len(right):
            row.append(right[i])
        rows.append(row)
    if show_on_bottom:
        rows.append([InlineKeyboardButton("הצג פתרון", callback_data="assist:show")])
    return InlineKeyboardMarkup(rows)


def build_assistant_step_picker_keyboard(progress: AssistantProgress) -> InlineKeyboardMarkup:
    kind = AssistantBeamKind(progress.beam_kind)
    steps = assistant_steps_for_kind(kind)
    rows: list[list[InlineKeyboardButton]] = []
    for step in steps:
        label = f"{step.number}. {step.title}"
        if len(label) > 64:
            label = label[:61] + "..."
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"assist:goto:{step.number}")]
        )
    rows.append([InlineKeyboardButton("חזרה לשלב הנוכחי", callback_data="assist:back")])
    return InlineKeyboardMarkup(rows)


def parse_assistant_callback(data: str) -> str | None:
    if not data.startswith("assist:"):
        return None
    action = data.split(":", 1)[-1]
    if action in (
        _ASSISTANT_EXPLAIN,
        _ASSISTANT_NEXT,
        _ASSISTANT_CHOOSE,
        _ASSISTANT_BACK,
        _ASSISTANT_SHOW,
        _ASSISTANT_YES,
        _ASSISTANT_PREV,
    ):
        return action
    if action.startswith("goto:"):
        step_part = action.split(":", 1)[-1]
        if step_part.isdigit() and int(step_part) >= 1:
            return action
    if action.startswith("sub:"):
        part = action.split(":", 1)[-1]
        if part.isdigit() and int(part) in (0, 1, 2):
            return action
    return None


def solve_mode_prompt_hebrew(mode: SolveMode) -> str:
    if mode == SolveMode.ASSISTANT:
        return (
            "מעולה, שלח/י תמונה של התרגיל.\n"
            "נעבור עליו יחד שלב-אחר-שלב."
        )
    if mode == SolveMode.ADD_TO_BANK:
        return (
            "שלח/י תמונה של התרגיל שתרצה להוסיף למאגר.\n"
            "אזהה את הנתונים ותוכל/י לתקן אותם לפני השמירה."
        )
    return (
        "מעולה — שלח/י עכשיו תמונה 📸 של התרגיל.\n"
        "אחזיר פתרון מחברת מלא."
    )


def parse_menu_mode_action(action: str) -> SolveMode | None:
    if not action.startswith("mode:"):
        return None
    mode_key = action.split(":", 1)[-1]
    mapping = {
        "notebook": SolveMode.NOTEBOOK,
        "assistant": SolveMode.ASSISTANT,
    }
    return mapping.get(mode_key)


def parse_bank_mode_action(action: str) -> SolveMode | None:
    """מזהה בחירת מצב פתרון לתרגיל מהמאגר (menu:bank:notebook / menu:bank:assistant)."""
    if not action.startswith("bank:"):
        return None
    mode_key = action.split(":", 1)[-1]
    mapping = {
        "notebook": SolveMode.NOTEBOOK,
        "assistant": SolveMode.ASSISTANT,
    }
    return mapping.get(mode_key)


def select_solve_mode(chat_id: int, mode: SolveMode) -> str:
    set_pending_solve_mode(chat_id, mode)
    return solve_mode_prompt_hebrew(mode)


def detect_assistant_beam_kind(extracted: dict) -> AssistantBeamKind:
    if infer_vision_exercise_type(extracted) != "beam":
        return AssistantBeamKind.UNKNOWN

    beam = extracted.get("beam")
    if not isinstance(beam, dict):
        return AssistantBeamKind.UNKNOWN

    support_mode, _, _ = resolve_beam_support_geometry(beam)
    if support_mode == "cantilever":
        return AssistantBeamKind.CANTILEVER

    supports = beam.get("supports") or []
    if isinstance(supports, list) and len(supports) >= 2:
        return AssistantBeamKind.SIMPLY_SUPPORTED

    if str(beam.get("support_mode", "")).lower() == "simply_supported":
        return AssistantBeamKind.SIMPLY_SUPPORTED

    return AssistantBeamKind.UNKNOWN


def assistant_beam_kind_label_hebrew(kind: AssistantBeamKind) -> str:
    if kind == AssistantBeamKind.CANTILEVER:
        return "תרגיל ריתום"
    if kind == AssistantBeamKind.SIMPLY_SUPPORTED:
        return "תרגיל עם שני סמכים"
    return "תרגיל קורה"


def assistant_beam_kind_short_label_hebrew(kind: AssistantBeamKind) -> str:
    if kind == AssistantBeamKind.CANTILEVER:
        return "ריתום"
    if kind == AssistantBeamKind.SIMPLY_SUPPORTED:
        return "2 סמכים"
    return "קורה"


def assistant_steps_for_kind(kind: AssistantBeamKind) -> tuple[AssistantStep, ...]:
    return _ASSISTANT_STEPS.get(kind, _ASSISTANT_STEPS[AssistantBeamKind.UNKNOWN])


def _beam_from_extracted(extracted: dict) -> dict:
    beam = extracted.get("beam")
    return beam if isinstance(beam, dict) else {}


def _load_left_x(ld: dict, beam: dict) -> float:
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        x1, x2 = distributed_span_from_left(ld, beam)
        return min(float(x1), float(x2))
    try:
        return float(ld.get("x", ld.get("x1", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def decomposition_load_entries(extracted: dict) -> list[tuple[int, dict]]:
    """עומסים לפרוק — ממוינים משמאל לימין על הקורה."""
    beam = _beam_from_extracted(extracted)
    loads = beam.get("loads") or []
    entries: list[tuple[int, dict]] = []
    if not isinstance(loads, list):
        return entries
    for idx, ld in enumerate(loads):
        if not isinstance(ld, dict):
            continue
        if str(ld.get("type", "")).lower() not in _DECOMPOSE_TYPES:
            continue
        entries.append((idx, ld))
    entries.sort(key=lambda item: _load_left_x(item[1], beam))
    return entries


def _load_summary_hebrew(ld: dict, beam: dict) -> str:
    t = str(ld.get("type", "")).lower()
    if t == "inclined":
        x = _fmt_num(float(ld.get("x", 0.0)))
        mag = _fmt_num(_inclined_mag(ld))
        angle = _fmt_num(float(ld.get("angle_deg", 30.0) or 30.0))
        dir_he = "שמאלה-מטה" if _inclined_dir(ld) == "dl" else "ימינה-מטה"
        return f"עומס אלכסוני {mag} טון, {angle} מעלות, {dir_he}, ב-x={x} מ'"
    if t == "distributed":
        x1, x2 = distributed_span_from_left(ld, beam)
        w = float(ld.get("w", ld.get("q", ld.get("magnitude", 0.0))) or 0.0)
        return (
            f"עומס מפורס, {_fmt_num(abs(w))} טון/מ', "
            f"מ-x={_fmt_num(x1)} עד x={_fmt_num(x2)} מ'"
        )
    return "עומס"


def explain_inclined_load_hebrew(ld: dict) -> str:
    return (
        "נפרק את העומס האלכסוני לרכיב אופקי Fx ולרכיב אנכי Fy, "
        "לפי זווית העומס ביחס לאופקי.\n"
        "אחרי החישוב, נחליף בדיאגרמה את העומס האלכסוני בשני חיצים נפרדים — "
        "אחד אופקי ואחד אנכי."
    )


def _distributed_equivalent_force_ton(ld: dict, beam: dict) -> tuple[float, float]:
    """מחזיר (w_abs_ton_per_m, length_m)."""
    x1, x2 = distributed_span_from_left(ld, beam)
    w = float(ld.get("w", ld.get("q", ld.get("magnitude", 0.0))) or 0.0)
    length = abs(float(x2) - float(x1))
    return abs(float(w)), length


def _inclined_fx_ton(ld: dict) -> float:
    mag = float(_inclined_mag(ld))
    angle = float(ld.get("angle_deg", 30.0) or 30.0)
    try:
        import math

        fx = mag * math.cos(math.radians(angle))
    except Exception:
        fx = 0.0
    return float(fx)


def compute_Ax_from_extracted(extracted: dict) -> float:
    """מחזיר Ax [t] כך ש-ΣFx=0 (ימינה חיובי)."""
    beam = _beam_from_extracted(extracted)
    loads = beam.get("loads") or []
    if not isinstance(loads, list):
        return 0.0
    sum_fx = 0.0
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower()
        if t == "inclined":
            fx = _inclined_fx_ton(ld)
            dir_key = _inclined_dir(ld)
            # dr = ימינה, dl = שמאלה
            sum_fx += fx if dir_key == "dr" else -fx
            continue
        # נקודתי יכול להגיע עם Fx
        fx_raw = ld.get("Fx", ld.get("fx"))
        if fx_raw is not None:
            try:
                sum_fx += float(fx_raw)
            except (TypeError, ValueError):
                pass
    return -sum_fx


def compute_Ay_from_extracted(extracted: dict) -> float:
    """מחזיר Ay [t] מפתרון הקורה (ריאקציה אנכית בסמך A)."""
    import copy

    from bot.solution_check import solve_extracted_beam

    try:
        solved = solve_extracted_beam(copy.deepcopy(extracted))
    except Exception:
        return 0.0
    result = solved.get("result") if isinstance(solved.get("result"), dict) else {}
    raw = result.get("reactions_ton") or result.get("reactions_kN") or {}
    try:
        ay = float(raw.get("R_Ay", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    if "reactions_kN" in result and "reactions_ton" not in result:
        from bot.config import KN_PER_TON

        return ay / float(KN_PER_TON)
    return ay


def _horizontal_load_terms_for_ax_equation(extracted: dict) -> list[tuple[float, str, str, str]]:
    """עומסים אופקיים במשוואת Ax — ממוינים משמאל לימין.

    Returns:
        list of (x, signed_term, direction_he, sign_word_he)
        - signed_term: "3" or "-3" (magnitude in tons)
        - direction_he: "ימין" / "שמאל"
        - sign_word_he: "פלוס" / "מינוס"
    """
    beam = _beam_from_extracted(extracted)
    loads = beam.get("loads") or []
    entries: list[tuple[float, str, str, str]] = []
    if not isinstance(loads, list):
        return entries
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower()
        if t == "inclined":
            fx = abs(_inclined_fx_ton(ld))
            if fx < 1e-12:
                continue
            fx_txt = _fmt_num(fx)
            is_right = _inclined_dir(ld) == "dr"
            signed = fx_txt if is_right else f"-{fx_txt}"
            entries.append(
                (
                    float(ld.get("x", 0.0)),
                    signed,
                    ("ימין" if is_right else "שמאל"),
                    ("פלוס" if is_right else "מינוס"),
                )
            )
            continue
        fx_raw = ld.get("Fx", ld.get("fx"))
        if fx_raw is None:
            continue
        try:
            fx = float(fx_raw)
        except (TypeError, ValueError):
            continue
        if abs(fx) < 1e-12:
            continue
        fx_txt = _fmt_num(abs(fx))
        is_right = fx >= 0
        signed = fx_txt if is_right else f"-{fx_txt}"
        entries.append(
            (
                float(ld.get("x", 0.0)),
                signed,
                ("ימין" if is_right else "שמאל"),
                ("פלוס" if is_right else "מינוס"),
            )
        )
    entries.sort(key=lambda item: item[0])
    return entries


def build_ax_equation_message_hebrew(extracted: dict) -> str:
    load_terms = _horizontal_load_terms_for_ax_equation(extracted)
    if not load_terms:
        return (
            "בתרגיל שלנו אין כוחות על ציר הx שהולכים ימינה או שמאלה, ולכן המשוואה תיהיה:\n"
            "Ax = 0\n"
            "ומכיוון שלא היו עומסים זאת תיהיה גם בתוצאה:\n"
            "⬆️ Ax = 0"
        )
    # build final equation (no ΣFx)
    pieces = ["Ax"]
    for _, term, _dir, _sign_word in load_terms:
        if term.startswith("-"):
            pieces.append(term)
        else:
            pieces.append(f"+ {term}")
    expr = " ".join(pieces) + " = 0"

    if len(load_terms) == 1:
        _x, term, direction_he, sign_word_he = load_terms[0]
        return (
            "דבר ראשון נציב את הAx בצד שמאל של המשוואה.\n"
            f"בתרגיל שלנו יש רק עומס צירי אחד שפונה לכיוון {direction_he}, ולכן נציב אותו אחרי הAx כ{sign_word_he}.\n"
            "זה יראה ככה:\n"
            f"{expr}"
        )

    lines: list[str] = []
    lines.append(f"בתרגיל שלנו יש {len(load_terms)} עומסים ציריים.")
    lines.append("נתחיל בלהציב את Ax בצד שמאל של המשוואה.")
    for i, (_x, term, direction_he, sign_word_he) in enumerate(load_terms, start=1):
        mag = term[1:] if term.startswith("-") else term
        if i == 1:
            lines.append(
                f"לאחר מכן ניקח את העומס הצירי הראשון משמאל שהוא {mag}, ונציב אותו כ{sign_word_he} בגלל שהוא פונה לכיוון {direction_he}."
            )
        else:
            ord_he = "השני" if i == 2 else "השלישי" if i == 3 else f"ה-{i}"
            lines.append(
                f"העומס {ord_he} הוא {mag}, ופונה לכיוון {direction_he}, ולכן נציב אותו במשוואה כ{sign_word_he}."
            )
    lines.append("בסופו של דבר המשוואה תיראה ככה:")
    lines.append(expr)
    return "\n".join(lines)


def _inclined_fy_ton(ld: dict) -> float:
    mag = float(_inclined_mag(ld))
    angle = float(ld.get("angle_deg", 30.0) or 30.0)
    return abs(mag * math.sin(math.radians(angle)))


# קונבנציית סימן במשוואת ΣMB לתלמיד: עם כיוון השעון = חיובי.
_MB_CLOCKWISE_POSITIVE = True


def _vertical_force_rotates_clockwise_about(
    pivot_x: float,
    force_x: float,
    *,
    vertical_down: bool,
) -> bool:
    """האם כוח אנכי ב-force_x מסובב עם כיוון השעון סביב pivot_x.

    מודל גיאומטרי לשרטוט קורה סטנדרטי (שמאל→ימין, מבט על הדף):
    - כוח למטה משמאל לנקודה → נגד כיוון השעון
    - כוח למטה מימין לנקודה → עם כיוון השעון
    - כוח למעלה משמאל לנקודה → עם כיוון השעון
    - כוח למעלה מימין לנקודה → נגד כיוון השעון

    מחושב מ-lever arm יחסי לנקודת הסיבוב (לא מהיפוך שרירותי של תווית).
    """
    # חיובי = הכוח מימין לנקודת הסיבוב
    lever = float(force_x) - float(pivot_x)
    if abs(lever) < 1e-12:
        return False
    if vertical_down:
        return lever > 0
    return lever < 0


def _moment_rotation_about_b_hebrew(
    rb_pos: float, x: float, *, vertical_down: bool
) -> tuple[str, str]:
    """מחזיר (מילת כיוון בעברית, סימן במשוואה) לפי גיאומטריה + קונבנציית סימן."""
    clockwise = _vertical_force_rotates_clockwise_about(
        rb_pos, x, vertical_down=vertical_down
    )
    rot_he = "עם" if clockwise else "נגד"
    if _MB_CLOCKWISE_POSITIVE:
        sign = "+" if clockwise else "-"
    else:
        sign = "-" if clockwise else "+"
    return rot_he, sign


def _mb_product_expr(sign: str, dist_txt: str, force_txt: str) -> str:
    """סימן ואז מכפלה בסוגריים: -(6.5·15)"""
    return f"{sign}({dist_txt}·{force_txt})"


def _mb_product_expr_opened(sign: str, dist: float, force: float) -> str:
    """סימן ואז תוצאת ההכפלה אחרי פתיחת סוגריים: -97.5"""
    return f"{sign}{_fmt_num(float(dist) * float(force))}"


def _mb_ay_product_expr(sign: str, dist_txt: str) -> str:
    """סימן ואז ריאקציה: +7Ay"""
    return f"{sign}{dist_txt}Ay"


@dataclass(frozen=True)
class _MbVerticalTerm:
    kind: str  # distributed | inclined | point | ay
    x: float
    dist: float
    force_txt: str
    vertical_down: bool
    ld: dict | None = None


def _collect_mb_vertical_terms(extracted: dict) -> tuple[list[_MbVerticalTerm], float, float]:
    beam = _beam_from_extracted(extracted)
    _, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    loads = beam.get("loads") or []
    terms: list[_MbVerticalTerm] = []

    ay_dist = abs(rb_pos - ra_pos)
    terms.append(
        _MbVerticalTerm(
            kind="ay",
            x=float(ra_pos),
            dist=ay_dist,
            force_txt="Ay",
            vertical_down=False,
        )
    )

    if isinstance(loads, list):
        for ld in loads:
            if not isinstance(ld, dict):
                continue
            t = str(ld.get("type", "")).lower()
            if t == "moment":
                continue
            if t == "distributed":
                w_abs, length = _distributed_equivalent_force_ton(ld, beam)
                if w_abs < 1e-12 or length < 1e-12:
                    continue
                x1, x2 = distributed_span_from_left(ld, beam)
                x_centroid = (float(x1) + float(x2)) / 2.0
                force = w_abs * length
                w_raw = float(ld.get("w", ld.get("q", 0.0)) or 0.0)
                terms.append(
                    _MbVerticalTerm(
                        kind="distributed",
                        x=x_centroid,
                        dist=abs(rb_pos - x_centroid),
                        force_txt=_fmt_num(force),
                        vertical_down=w_raw >= 0,
                        ld=ld,
                    )
                )
                continue
            if t == "inclined":
                fy = _inclined_fy_ton(ld)
                if fy < 1e-12:
                    continue
                x = float(ld.get("x", 0.0))
                terms.append(
                    _MbVerticalTerm(
                        kind="inclined",
                        x=x,
                        dist=abs(rb_pos - x),
                        force_txt=_fmt_num(fy),
                        vertical_down=True,
                        ld=ld,
                    )
                )
                continue
            if t == "point":
                try:
                    fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
                except (TypeError, ValueError):
                    fy = 0.0
                if abs(fy) < 1e-12:
                    continue
                x = float(ld.get("x", 0.0))
                terms.append(
                    _MbVerticalTerm(
                        kind="point",
                        x=x,
                        dist=abs(rb_pos - x),
                        force_txt=_fmt_num(abs(fy)),
                        vertical_down=fy > 0,
                        ld=ld,
                    )
                )

    terms.sort(key=lambda item: item.x)
    return terms, float(ra_pos), float(rb_pos)


def _describe_mb_vertical_term_hebrew(term: _MbVerticalTerm, rb_pos: float, *, first: bool) -> str:
    rot, sign = _moment_rotation_about_b_hebrew(
        rb_pos, term.x, vertical_down=term.vertical_down
    )
    dist_txt = _fmt_num(term.dist)

    if term.kind == "ay":
        prod = _mb_ay_product_expr(sign, dist_txt)
        body = (
            f"הריאקציה Ay, המרחק שלה מB הוא {dist_txt} והיא מסתובבת {rot} כיוון השעון "
            f"ולכן היא תיכנס למשוואה כ{prod}."
        )
    elif term.kind == "distributed":
        prod = _mb_product_expr(sign, dist_txt, term.force_txt)
        body = (
            f"עומס מפורס שמצאנו שהכח השקול שלו הוא {term.force_txt} נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון, הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )
    elif term.kind == "inclined":
        prod = _mb_product_expr(sign, dist_txt, term.force_txt)
        body = (
            f"עומס אלכסוני שמצאנו שהכח האנכי שלו הוא {term.force_txt}, נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )
    else:
        prod = _mb_product_expr(sign, dist_txt, term.force_txt)
        body = (
            f"עומס נקודתי במשקל {term.force_txt}, נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )

    if first:
        return f"נתחיל בכח הראשון משמאל, {body}"
    return body


def build_ay_mb_equation_message_hebrew(extracted: dict, *, prefix: str = "") -> str:
    terms, _ra_pos, rb_pos = _collect_mb_vertical_terms(extracted)
    vertical_load_count = sum(1 for t in terms if t.kind != "ay")

    lines: list[str] = []
    opener = f"{prefix} כמו שאמרנו, " if prefix else "כמו שאמרנו, "
    lines.append(
        opener
        + "אנחנו מחפשים את Ay, ולכן המשוואה תיהיה ΣMB = 0 - שזה אומר שסכום כל הכוחות "
        "(גם עומסים וגם ריאקציות) שפועלים במשוואת שיווי משקל סביב הנקודה B יהיו שווים ל0."
    )
    lines.append(
        "כל עומס שנוסיף, נכפיל אותו במרחק שלו מנקודה B, ונבדוק אם הוא מסתובב סביבה עם/נגד כיוון השעון."
    )
    lines.append(
        "*שים לב שבעומס מפורס, הנוסחה היא להכפיל את העומס השקול שלו "
        "במרחק מהאמצע של העומס עד לנקודה.*"
    )
    lines.append("*מומנט טהור ועומס צירי לא ייכנסו למשוואה הזאת.*")
    lines.append(f"בתרגיל שלנו יש {vertical_load_count} עומסים אנכיים.")

    if not terms:
        lines.append("אין כאן עומסים אנכיים לבניית המשוואה.")
        return "\n".join(lines)

    for i, term in enumerate(terms):
        desc = _describe_mb_vertical_term_hebrew(term, rb_pos, first=(i == 0))
        if i == 0:
            lines.append(desc)
        else:
            lines.append(f"הכח הבא הוא {desc}")

    lines.append("תרצה לראות איך כל זה נכנס למשוואה אחת עד הגעה לפתרון?")
    return "\n".join(lines)


def build_ay_mb_assembled_equation_hebrew(extracted: dict) -> str:
    """משוואה מורכבת מאיברי ΣMB לפי אותו סדר כמו בהודעת ההסבר."""
    terms, _ra_pos, rb_pos = _collect_mb_vertical_terms(extracted)
    parts: list[str] = []
    opened_parts: list[str] = []
    ay_coeff = 0.0
    known_moment = 0.0
    for term in terms:
        _rot, sign = _moment_rotation_about_b_hebrew(
            rb_pos, term.x, vertical_down=term.vertical_down
        )
        s = 1.0 if sign == "+" else -1.0
        dist_txt = _fmt_num(term.dist)
        if term.kind == "ay":
            ay_expr = _mb_ay_product_expr(sign, dist_txt)
            parts.append(ay_expr)
            opened_parts.append(ay_expr)
            ay_coeff = s * float(term.dist)
        else:
            parts.append(_mb_product_expr(sign, dist_txt, term.force_txt))
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            opened_parts.append(_mb_product_expr_opened(sign, term.dist, force))
            known_moment += s * float(term.dist) * force
    equation = "".join(parts) + "=0"
    opened = "".join(opened_parts) + "=0"
    ay = (-known_moment / ay_coeff) if abs(ay_coeff) >= 1e-12 else 0.0
    ay_txt = _fmt_num(ay)
    return (
        "ככה נראית המשוואה שלנו:\n"
        f"{equation}\n"
        "כשפותחים את כל האיברים המשוואה תיראה ככה:\n"
        f"{opened}\n"
        "והתוצאה:\n"
        f"Ay = {ay_txt}t"
    )


def explain_distributed_load_hebrew(ld: dict, beam: dict) -> str:
    w_abs, length = _distributed_equivalent_force_ton(ld, beam)
    w_txt = _fmt_num(w_abs)
    length_txt = _fmt_num(length)
    return (
        "בשביל למצוא את הכח השקול של העומס המפורס, אנחנו צריכים את שתי הנתונים שיש לנו על "
        "העומס - הכח טון/מטר שלו, והאורך.\n"
        f"במקרה שלנו זה ({w_txt}t/m, {length_txt}m).\n"
        "הנוסחה היא להכפיל את האורך בכח הקיים, והתוצאה היא הכח השקול.\n"
        "איך תרצה להמשיך?"
    )


def explain_step_procedure_hebrew(step: AssistantStep) -> str:
    return _STEP_PROCEDURE_EXPLAIN.get(
        step.title,
        f"בשלב הזה נתמקד ב{step.title.lower()} — נעבוד צעד-אחר-צעד בלי לדלג על החישוב.",
    )


def explain_current_decomposition_item(progress: AssistantProgress) -> str:
    beam = _beam_from_extracted(progress.extracted)
    loads = beam.get("loads") or []
    if progress.sub_index >= len(progress.decomposition_indices):
        return "אין כאן עוד עומס לפרוק."
    load_idx = progress.decomposition_indices[progress.sub_index]
    if not isinstance(loads, list) or load_idx >= len(loads):
        return "לא מצאנו את העומס הזה."
    ld = loads[load_idx]
    t = str(ld.get("type", "")).lower()
    if t == "inclined":
        return explain_inclined_load_hebrew(ld)
    if t == "distributed":
        return explain_distributed_load_hebrew(ld, beam)
    return "עדיין אין הסבר לעומס הזה."


def _current_decomposition_load(progress: AssistantProgress) -> tuple[dict, dict] | None:
    """מחזיר (ld, beam) של העומס הנוכחי בשלב הפרוק."""
    if progress.step_index != 0:
        return None
    beam = _beam_from_extracted(progress.extracted)
    loads = beam.get("loads") or []
    if progress.sub_index >= len(progress.decomposition_indices):
        return None
    load_idx = progress.decomposition_indices[progress.sub_index]
    if not isinstance(loads, list) or load_idx >= len(loads):
        return None
    ld = loads[load_idx]
    return (ld if isinstance(ld, dict) else {}), beam


def explain_current_step_hebrew(progress: AssistantProgress) -> str:
    if progress.step_index == 0:
        return explain_current_decomposition_item(progress)
    if progress.step_index == 1 and progress.reaction_sub_index == 0:
        return (
            "בשביל למצוא את Ax, אנחנו נייצר משוואה פשוטה שנכניס לתוכה את כל העומסים שהולכים ימינה ושמאלה על הקורה.\n"
            "אם עומס כזה הולך לכיוון שמאל, הוא ייכנס כמינוס. ואם לימין, הוא ייכנס כפלוס.\n"
            "המשוואה תתחיל בAx, ותמשיך בעומסים שתכניס משמאל לימין (בשביל הסדר).\n"
            "כשסיימנו להכניס את כל העומסים למשוואה, נשווה אותה ל0.\n"
            "נמשיך למשוואה בתרגיל שלנו?"
        )
    if progress.step_index == 1 and progress.reaction_sub_index == 1:
        kind = AssistantBeamKind(progress.beam_kind)
        if kind == AssistantBeamKind.SIMPLY_SUPPORTED:
            return (
                "מכיוון שיש לנו 2 ריאקציות, שזה 2 נעלמים שחסרים לנו, בשביל למצוא את אחד מהם "
                "אנחנו נצטרך לייצר משוואת שיווי משקל סביב אחת מהנקודות A או B, בשביל למצוא את הריאקציות.\n"
                "במקרה שלנו בשביל למצוא את Ay, אנחנו נצטרך לשים את המשוואה סביב הנקודה B, ככה שבמשוואה שתיווצר לנו "
                "לנו, הנעלם By מתבטל ונישאר עם נעלם אחד שזה Ay.\n"
                "שנמשיך לראות איך זה קורה בפועל בתרגיל שלנו?"
            )
    kind = AssistantBeamKind(progress.beam_kind)
    steps = assistant_steps_for_kind(kind)
    if progress.step_index < len(steps):
        return explain_step_procedure_hebrew(steps[progress.step_index])
    return "סיימנו יחד את מה שזמין כרגע."


def _step_header_hebrew(progress: AssistantProgress, *, friendly: bool = True) -> str:
    kind = AssistantBeamKind(progress.beam_kind)
    steps = assistant_steps_for_kind(kind)
    step_no = progress.step_index + 1
    total = len(steps)
    title = steps[progress.step_index].title if progress.step_index < len(steps) else "שלב"
    step_phrase = step_phrase_hebrew(step_no, total=total)
    if step_no == 1:
        body = f"עכשיו אנחנו נעבור על {step_phrase} — {title}."
    else:
        body = f"עכשיו אנחנו ב{step_phrase} — {title}."
    return apply_friendly_opener(body, friendly=friendly)


def build_decomposition_prompt_hebrew(
    progress: AssistantProgress, *, friendly: bool = True
) -> str:
    """תאימות לאחור — מפנה למסך הנוכחי של שלב הפרוק."""
    del friendly  # המסך המאוחד לא משתמש בכותרת הידידותית הישנה
    return build_current_screen_hebrew(progress, prefix="", friendly=False)


def build_reaction_substep_screen_hebrew(
    progress: AssistantProgress, *, prefix: str = ""
) -> str:
    """הודעת כניסה יחידה לתת-שלב ריאקציות (Ax/Ay/By או Ax/Ma/Ay)."""
    kind = AssistantBeamKind(progress.beam_kind)
    substeps = _reaction_substeps_for_kind(kind)
    idx = max(0, min(progress.reaction_sub_index, len(substeps) - 1))
    sub = substeps[idx]
    head = f"{prefix} " if prefix else ""
    continue_prompt = collaborative_continue_prompt()
    if idx == 0:
        return (
            f"{head}הגענו לשלב השני - מציאת הריאקציות.\n"
            f"נתחיל מ{sub}.\n\n"
            f"{continue_prompt}"
        )
    return (
        f"{head}נמצא עכשיו את הריאקציה הבאה בתור - {sub}.\n"
        f"{continue_prompt}"
    )


def build_current_screen_hebrew(
    progress: AssistantProgress,
    *,
    prefix: str = "",
    friendly: bool = False,
) -> str:
    """הודעת הכניסה היחידה למצב הנוכחי — כל נתיבי הניווט קוראים לכאן."""
    kind = AssistantBeamKind(progress.beam_kind)
    steps = assistant_steps_for_kind(kind)

    if progress.step_index == 0:
        if not progress.decomposition_indices:
            return (
                f"{_step_header_hebrew(progress, friendly=friendly)}\n\n"
                "אין כאן עומסים מפורסים או אלכסוניים לפרוק — נדלג יחד לשלב הבא."
            )
        if progress.sub_index <= 0:
            body = build_first_decomposition_item_message_hebrew(progress)
            return f"{prefix} {body}".strip() if prefix else body
        return build_next_decomposition_item_message_hebrew(
            progress, prefix=prefix
        )

    if progress.step_index == 1:
        return build_reaction_substep_screen_hebrew(progress, prefix=prefix)

    if progress.step_index >= len(steps):
        head = f"{prefix} " if prefix else ""
        return f"{head}סיימנו את מה שזמין כרגע."

    head = f"{prefix} " if prefix else ""
    return (
        f"{head}{_step_header_hebrew(progress, friendly=False)}\n\n"
        f"{collaborative_continue_prompt()}"
    )


def build_step_prompt_hebrew(progress: AssistantProgress, *, friendly: bool = True) -> str:
    """תאימות לאחור — מפנה לבונה המסך המאוחד."""
    return build_current_screen_hebrew(progress, prefix="", friendly=friendly)


def build_assistant_plan_message_hebrew(extracted: dict) -> tuple[str, AssistantBeamKind]:
    kind = detect_assistant_beam_kind(extracted)
    entries = decomposition_load_entries(extracted)
    count = len(entries)
    short_kind = assistant_beam_kind_short_label_hebrew(kind)
    lines = [
        f"מעולה, מדובר בתרגיל {short_kind}.",
        "",
        "בשלב הראשון אנחנו נפרק עומסים בעייתיים כמו עומסים מפורסים או אלכסוניים.",
        f"במקרה שלנו יש {count} עומסים שנצטרך לפרק אותם.",
        "נפתור אותם אחד אחרי השני משמאל לימין.",
    ]
    return "\n".join(lines), kind


def _decomposition_load_type_label_hebrew(ld: dict) -> str:
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        return "מפורס"
    if t == "inclined":
        return "אלכסוני"
    return "עומס"


def build_next_decomposition_item_message_hebrew(
    progress: AssistantProgress, *, prefix: str = ""
) -> str:
    """הודעת מעבר לעומס הבא בשלב הפרוק (אחרי «המשך»)."""
    beam = _beam_from_extracted(progress.extracted)
    loads = beam.get("loads") or []
    if progress.sub_index >= len(progress.decomposition_indices):
        head = f"{prefix} " if prefix else ""
        return f"{head}סיימנו את פירוק העומסים הבעייתיים."

    load_idx = progress.decomposition_indices[progress.sub_index]
    ld = loads[load_idx] if isinstance(loads, list) and load_idx < len(loads) else {}
    label = _decomposition_load_type_label_hebrew(ld)

    seen_types: set[str] = set()
    for j in range(0, progress.sub_index):
        idx_prev = progress.decomposition_indices[j]
        prev = (
            loads[idx_prev]
            if isinstance(loads, list) and 0 <= idx_prev < len(loads)
            else {}
        )
        if isinstance(prev, dict):
            seen_types.add(str(prev.get("type", "")).lower())
    cur_type = str(ld.get("type", "")).lower()
    seen_before = cur_type in seen_types

    type_phrase = f"שוב {label}" if seen_before else label
    opener = (
        f"{prefix} עברנו לפירוק של הכח הבעייתי הבא, והפעם {type_phrase}."
        if prefix
        else f"עברנו לפירוק של הכח הבעייתי הבא, והפעם {type_phrase}."
    )
    lines = [opener]
    if not seen_before:
        lines.extend(["", decomposition_context_hebrew(ld)])
    lines.extend(
        [
            "",
            _load_summary_hebrew(ld, beam),
            "",
            decomposition_continue_prompt(),
        ]
    )
    return "\n".join(lines)

def build_first_decomposition_item_message_hebrew(progress: AssistantProgress) -> str:
    """הודעת הפרוק הראשונה אחרי הודעת הפתיחה."""
    beam = _beam_from_extracted(progress.extracted)
    loads = beam.get("loads") or []
    if not progress.decomposition_indices:
        return (
            "בתרגיל הזה אין עומסים מפורסים או אלכסוניים לפרוק.\n"
            "אפשר להמשיך ישירות לשלב הבא."
        )
    load_idx = progress.decomposition_indices[0]
    ld = loads[load_idx] if isinstance(loads, list) and load_idx < len(loads) else {}
    label = _decomposition_load_type_label_hebrew(ld)
    lines = [
        f"העומס הראשון ברשימה הוא {label}.",
        "",
        decomposition_context_hebrew(ld),
        "",
        _load_summary_hebrew(ld, beam),
        "",
        decomposition_continue_prompt(),
    ]
    return "\n".join(lines)


def start_assistant_progress(
    chat_id: int,
    extracted: dict,
    beam_kind: AssistantBeamKind,
) -> AssistantProgress:
    entries = decomposition_load_entries(extracted)
    progress = AssistantProgress(
        beam_kind=beam_kind.value,
        extracted=extracted,
        step_index=0,
        sub_index=0,
        reaction_sub_index=0,
        decomposition_indices=[idx for idx, _ in entries],
    )
    set_assistant_progress(chat_id, progress)
    set_assistant_beam_kind(chat_id, beam_kind.value)
    return progress


def is_assistant_mode(chat_id: int) -> bool:
    return get_solve_mode(chat_id) == SolveMode.ASSISTANT


def jump_to_assistant_step(progress: AssistantProgress, step_number: int) -> AssistantProgress | None:
    """קפיצה לשלב לפי מספר תצוגה (1-based)."""
    kind = AssistantBeamKind(progress.beam_kind)
    steps = assistant_steps_for_kind(kind)
    if step_number < 1 or step_number > len(steps):
        return None
    progress.step_index = step_number - 1
    progress.sub_index = 0
    progress.reaction_sub_index = 0
    return progress


async def show_assistant_step_picker(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    send_text: SendTextFn,
    reply_message=None,
) -> None:
    progress = get_assistant_progress(chat_id)
    if progress is None:
        return
    text = "לאיזה שלב נרצה לעבור?"
    keyboard = build_assistant_step_picker_keyboard(progress)
    if reply_message is not None:
        try:
            await reply_message.edit_text(text, reply_markup=keyboard)
            return
        except BadRequest:
            pass
    sent = await send_text(context, chat_id, text, reply_markup=keyboard)
    try:
        append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
    except Exception:
        pass


async def _send_step_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    send_text: SendTextFn,
    reply_message=None,
    include_explain: bool = True,
    include_show_solution: bool = False,
    reply_markup_override: InlineKeyboardMarkup | None = None,
    include_prev: bool = False,
) -> None:
    step_kb = reply_markup_override or build_assistant_step_keyboard(
        include_explain=include_explain,
        include_show_solution=include_show_solution,
        include_prev=include_prev,
    )
    if reply_message is not None:
        try:
            sent = await reply_message.reply_text(
                text,
                reply_markup=step_kb,
                parse_mode="Markdown",
            )
            try:
                append_assistant_message_id(chat_id, int(sent.message_id))
            except Exception:
                pass
            return
        except BadRequest:
            pass
    sent = await send_text(context, chat_id, text, reply_markup=step_kb)
    try:
        append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
    except Exception:
        pass
    # snapshot for ↩️: remember exact sent text + keyboard type
    progress = get_assistant_progress(chat_id)
    if progress is not None:
        kb_meta: dict | None = None
        if reply_markup_override is not None and progress.step_index == 1:
            texts = [
                btn.text for row in reply_markup_override.inline_keyboard for btn in row
            ]
            kb_meta = {
                "kind": "reactions",
                "include_yes": ("כן" in texts),
                "include_show_solution": ("הצג פתרון" in texts),
                "include_explain": ("הסבר לי" in texts),
            }
        else:
            kb_meta = {
                "kind": "step",
                "include_explain": bool(include_explain),
                "include_show_solution": bool(include_show_solution),
            }
        set_assistant_last_screen(
            chat_id,
            {
                "step_index": int(progress.step_index),
                "sub_index": int(progress.sub_index),
                "reaction_sub_index": int(getattr(progress, "reaction_sub_index", 0)),
                "text": str(text),
                "kb": kb_meta,
            },
        )


def _reactions_keyboard_for_progress(
    progress: AssistantProgress,
    chat_id: int,
    *,
    include_explain: bool = True,
    include_show_solution: bool = False,
    include_yes: bool = False,
) -> InlineKeyboardMarkup:
    return build_reactions_step_keyboard(
        progress,
        include_explain=include_explain,
        include_prev=has_assistant_prev_state(chat_id),
        include_show_solution=include_show_solution,
        include_yes=include_yes,
    )


async def present_assistant_step(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    send_text: SendTextFn,
    reply_message=None,
    friendly_opener: bool = True,
    prefix: str = "",
) -> None:
    """מציג את מסך המצב הנוכחי — תמיד דרך build_current_screen_hebrew."""
    progress = get_assistant_progress(chat_id)
    if progress is None:
        return

    text = build_current_screen_hebrew(
        progress, prefix=prefix, friendly=friendly_opener
    )
    markup = None
    if progress.step_index == 1:
        markup = _reactions_keyboard_for_progress(progress, chat_id)

    await _send_step_prompt(
        context,
        chat_id,
        text,
        send_text=send_text,
        reply_message=reply_message,
        reply_markup_override=markup,
        include_prev=has_assistant_prev_state(chat_id),
    )


async def advance_assistant_step(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    send_text: SendTextFn,
    reply_message=None,
) -> None:
    progress = get_assistant_progress(chat_id)
    if progress is None:
        return

    prefix = encouragement_prefix_hebrew()
    kind = AssistantBeamKind(progress.beam_kind)
    steps = assistant_steps_for_kind(kind)

    if progress.step_index == 0:
        if progress.decomposition_indices and progress.sub_index + 1 < len(
            progress.decomposition_indices
        ):
            progress.sub_index += 1
            set_assistant_progress(chat_id, progress)
            await present_assistant_step(
                context,
                chat_id,
                send_text=send_text,
                reply_message=reply_message,
                friendly_opener=False,
                prefix=prefix,
            )
            return
        progress.step_index = 1
        progress.sub_index = 0
        progress.reaction_sub_index = 0
        set_assistant_progress(chat_id, progress)
        if progress.step_index >= len(steps):
            sent = await send_text(
                context,
                chat_id,
                build_current_screen_hebrew(progress, prefix=prefix),
            )
            try:
                append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
            except Exception:
                pass
            return
        await present_assistant_step(
            context,
            chat_id,
            send_text=send_text,
            reply_message=reply_message,
            friendly_opener=False,
            prefix=prefix,
        )
        return

    if progress.step_index == 1:
        substeps = _reaction_substeps_for_kind(kind)
        if progress.reaction_sub_index + 1 < len(substeps):
            progress.reaction_sub_index += 1
            set_assistant_progress(chat_id, progress)
            await present_assistant_step(
                context,
                chat_id,
                send_text=send_text,
                reply_message=reply_message,
                friendly_opener=False,
                prefix=prefix,
            )
            return

        progress.step_index = 2
        progress.reaction_sub_index = 0
        set_assistant_progress(chat_id, progress)
        text = (
            f"{prefix} סיימנו את מציאת הריאקציות.\n\n"
            f"{build_current_screen_hebrew(progress, friendly=False)}"
        )
        await _send_step_prompt(
            context,
            chat_id,
            text,
            send_text=send_text,
            reply_message=reply_message,
            include_prev=has_assistant_prev_state(chat_id),
        )
        return

    sent = await send_text(
        context,
        chat_id,
        f"{prefix} עוד שלבים בדרך — נמשיך בקרוב.",
    )
    try:
        append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
    except Exception:
        pass


async def handle_assistant_action(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    action: str,
    *,
    send_text: SendTextFn,
    reply_message=None,
) -> None:
    progress = get_assistant_progress(chat_id)
    if progress is None:
        return

    if action == _ASSISTANT_PREV:
        ids = pop_assistant_message_ids(chat_id)
        for mid in ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=int(mid))
            except Exception:
                pass
        prev = pop_assistant_prev_state(chat_id)
        if prev is None:
            await send_text(context, chat_id, "אין הודעה קודמת לחזור אליה.")
            return
        progress.step_index = int(prev.get("step_index", progress.step_index))
        progress.sub_index = int(prev.get("sub_index", progress.sub_index))
        progress.reaction_sub_index = int(
            prev.get("reaction_sub_index", progress.reaction_sub_index)
        )
        set_assistant_progress(chat_id, progress)
        text = str(prev.get("text") or build_current_screen_hebrew(progress, friendly=False))
        kb = prev.get("kb") or {}
        markup: InlineKeyboardMarkup | None = None
        if kb.get("kind") == "reactions":
            markup = build_reactions_step_keyboard(
                progress,
                include_prev=has_assistant_prev_state(chat_id),
                include_explain=bool(kb.get("include_explain", False)),
                include_show_solution=bool(kb.get("include_show_solution", False)),
                include_yes=bool(kb.get("include_yes", False)),
            )
        elif progress.step_index == 1:
            markup = build_reactions_step_keyboard(
                progress, include_prev=has_assistant_prev_state(chat_id)
            )
        await _send_step_prompt(
            context,
            chat_id,
            text,
            send_text=send_text,
            reply_message=None,
            reply_markup_override=markup,
            include_prev=has_assistant_prev_state(chat_id),
        )
        return

    # מוחק את כל הודעות המסלול מאז אישור הטיוטה לפני כל פעולה.
    # (כדי למנוע תלות ב-reply_message שנמחק, נשלח אחר כך הודעה חדשה בלבד.)
    last = get_assistant_last_screen(chat_id)
    if last is not None:
        # keep exact snapshot; not just indices
        from bot.solution_session import get_solution_session

        sess = get_solution_session(chat_id)
        if sess is not None:
            sess.assistant_prev_stack.append(dict(last))
    ids = pop_assistant_message_ids(chat_id)
    for mid in ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=int(mid))
        except Exception:
            pass
    reply_message = None

    # NOTE: snapshot push handled via assistant_last_screen above.

    if action == _ASSISTANT_EXPLAIN:
        text = explain_current_step_hebrew(progress)
        show_solution = False
        cur = _current_decomposition_load(progress)
        if cur is not None:
            ld, _beam = cur
            if str(ld.get("type", "")).lower() == "distributed":
                show_solution = True
        markup = None
        if progress.step_index == 1:
            show_solution = progress.reaction_sub_index == 0
            kind = AssistantBeamKind(progress.beam_kind)
            markup = build_reactions_step_keyboard(
                progress,
                include_explain=False,
                include_prev=has_assistant_prev_state(chat_id),
                include_show_solution=show_solution,
                include_yes=(
                    progress.reaction_sub_index == 0
                    or (kind == AssistantBeamKind.SIMPLY_SUPPORTED and progress.reaction_sub_index == 1)
                ),
            )
        await _send_step_prompt(
            context,
            chat_id,
            text,
            send_text=send_text,
            reply_message=reply_message,
            include_explain=False,
            include_show_solution=show_solution,
            reply_markup_override=markup,
            include_prev=has_assistant_prev_state(chat_id),
        )
        return

    if action == _ASSISTANT_YES:
        if progress.step_index != 1:
            await send_text(context, chat_id, "הפעולה הזו זמינה רק בשלב הריאקציות.")
            return
        kind = AssistantBeamKind(progress.beam_kind)
        if progress.reaction_sub_index == 0:
            await _send_step_prompt(
                context,
                chat_id,
                build_ax_equation_message_hebrew(progress.extracted),
                send_text=send_text,
                reply_message=reply_message,
                include_explain=False,
                include_show_solution=True,
                reply_markup_override=build_reactions_step_keyboard(
                    progress,
                    include_explain=False,
                    include_prev=has_assistant_prev_state(chat_id),
                    include_show_solution=True,
                    include_yes=False,
                ),
                include_prev=has_assistant_prev_state(chat_id),
            )
            return
        if kind == AssistantBeamKind.SIMPLY_SUPPORTED and progress.reaction_sub_index == 1:
            await _send_step_prompt(
                context,
                chat_id,
                build_ay_mb_equation_message_hebrew(
                    progress.extracted, prefix=encouragement_prefix_hebrew()
                ),
                send_text=send_text,
                reply_message=reply_message,
                include_explain=False,
                include_show_solution=True,
                reply_markup_override=build_reactions_step_keyboard(
                    progress,
                    include_explain=False,
                    include_prev=has_assistant_prev_state(chat_id),
                    include_show_solution=True,
                    include_yes=False,
                ),
                include_prev=has_assistant_prev_state(chat_id),
            )
            return
        await send_text(context, chat_id, "הכפתור «כן» זמין כרגע רק ב-Ax וב-Ay (בתרגיל 2 סמכים).")
        return

    if action == _ASSISTANT_SHOW:
        if progress.step_index == 1 and progress.reaction_sub_index == 0:
            ax = compute_Ax_from_extracted(progress.extracted)
            ax_txt = _fmt_num(ax)
            await _send_step_prompt(
                context,
                chat_id,
                f"Ax = {ax_txt}t",
                send_text=send_text,
                reply_message=reply_message,
                include_explain=False,
                include_show_solution=False,
                reply_markup_override=build_reactions_step_keyboard(
                    progress,
                    include_explain=True,
                    include_prev=has_assistant_prev_state(chat_id),
                    include_show_solution=False,
                ),
                include_prev=has_assistant_prev_state(chat_id),
            )
            return
        if (
            progress.step_index == 1
            and progress.reaction_sub_index == 1
            and AssistantBeamKind(progress.beam_kind) == AssistantBeamKind.SIMPLY_SUPPORTED
        ):
            await _send_step_prompt(
                context,
                chat_id,
                build_ay_mb_assembled_equation_hebrew(progress.extracted),
                send_text=send_text,
                reply_message=reply_message,
                include_explain=False,
                include_show_solution=False,
                reply_markup_override=build_reactions_step_keyboard(
                    progress,
                    include_explain=True,
                    include_prev=has_assistant_prev_state(chat_id),
                    include_show_solution=False,
                ),
                include_prev=has_assistant_prev_state(chat_id),
            )
            return

        cur = _current_decomposition_load(progress)
        if cur is None:
            await send_text(context, chat_id, "אין כאן פתרון להצגה כרגע.")
            return
        ld, beam = cur
        if str(ld.get("type", "")).lower() != "distributed":
            await send_text(context, chat_id, "הצגת פתרון זמינה כרגע רק לעומס מפורס.")
            return
        w_abs, length = _distributed_equivalent_force_ton(ld, beam)
        force_ton = w_abs * length
        force_txt = _fmt_num(force_ton)
        await _send_step_prompt(
            context,
            chat_id,
            f"הכח השקול הוא: {force_txt} t",
            send_text=send_text,
            reply_message=reply_message,
            include_explain=False,
            include_show_solution=False,
            include_prev=has_assistant_prev_state(chat_id),
        )
        return

    if action == _ASSISTANT_NEXT:
        await advance_assistant_step(
            context, chat_id, send_text=send_text, reply_message=reply_message
        )
        return

    if action.startswith("sub:"):
        if progress.step_index != 1:
            await send_text(context, chat_id, "תת-שלב לא זמין כרגע.")
            return
        idx = int(action.split(":", 1)[-1])
        progress.reaction_sub_index = max(0, min(idx, 2))
        set_assistant_progress(chat_id, progress)
        await present_assistant_step(
            context,
            chat_id,
            send_text=send_text,
            reply_message=reply_message,
            friendly_opener=False,
        )
        return

    if action == _ASSISTANT_CHOOSE:
        await show_assistant_step_picker(
            context, chat_id, send_text=send_text, reply_message=reply_message
        )
        return

    if action == _ASSISTANT_BACK:
        await present_assistant_step(
            context, chat_id, send_text=send_text, reply_message=reply_message
        )
        return

    if action.startswith("goto:"):
        step_number = int(action.split(":", 1)[-1])
        updated = jump_to_assistant_step(progress, step_number)
        if updated is None:
            await send_text(context, chat_id, "מספר שלב לא תקין.")
            return
        set_assistant_progress(chat_id, updated)
        await present_assistant_step(
            context, chat_id, send_text=send_text, reply_message=reply_message
        )
        return


async def deliver_assistant_after_approve(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    extracted: dict,
    reply: str,
    solved: dict,
    draft_msg_id: int | None,
    send_text: SendTextFn,
    edit_draft_message: EditDraftFn,
) -> None:
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

    plan_text, beam_kind = build_assistant_plan_message_hebrew(extracted)
    clear_assistant_prev_stack(chat_id)
    progress = start_assistant_progress(chat_id, extracted, beam_kind)
    sent = await send_text(context, chat_id, plan_text)
    try:
        append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
    except Exception:
        pass

    advice = (
        "המלצה אישית שלי, כשניגשים לתרגיל קודם כל מפרקים בצד את העומסים הבעייתיים אם יש "
        "(שזה אלכסוניים ומפורסים), וכשיש לנו אותם מוכנים נתחיל לסרטט במחברת את הקורה עם כל העומסים "
        "מוכנים לעבודה.\n"
        "*אני אישית יותר נח לי לסרטט את הקורה עם העומסים בדיוק כמו שהיא בתרגיל ובצד של המחברת לרשום לי את הפירוק שלהם, "
        "אבל כל אחד שיתרגל למה שנח לו."
    )
    sent_advice = await send_text(context, chat_id, advice)
    try:
        append_assistant_message_id(chat_id, int(getattr(sent_advice, "message_id", 0)))
    except Exception:
        pass
    if draft_msg_id is not None:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=draft_msg_id)
        except BadRequest:
            pass
    # הודעה שנייה: העומס הראשון לפרוק (בלי כותרת "עכשיו אנחנו...")
    text2 = build_first_decomposition_item_message_hebrew(progress)
    await _send_step_prompt(
        context,
        chat_id,
        text2,
        send_text=send_text,
        reply_message=None,
        include_explain=True,
        include_show_solution=False,
    )


async def deliver_after_draft_approve(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    extracted: dict,
    reply: str,
    solved: dict,
    draft_msg_id: int | None,
    deliver_notebook: DeliverNotebookFn,
    send_text: SendTextFn,
    edit_draft_message: EditDraftFn,
) -> None:
    if is_assistant_mode(chat_id):
        await deliver_assistant_after_approve(
            context,
            chat_id,
            extracted=extracted,
            reply=reply,
            solved=solved,
            draft_msg_id=draft_msg_id,
            send_text=send_text,
            edit_draft_message=edit_draft_message,
        )
        return
    await deliver_notebook(
        context,
        chat_id,
        extracted=extracted,
        reply=reply,
        solved=solved,
        draft_msg_id=draft_msg_id,
    )
