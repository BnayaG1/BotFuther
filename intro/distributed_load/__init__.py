# -*- coding: utf-8 -*-
"""מבוא — עומס מפורס."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


_BODY = (
    "עכשיו נעבור על עומס מפורס ונבין מה הוא.\n"
    "בתרגיל הבא יש עומס מפורס, ובשביל שזה יישב טוב בראש תדמיין את התרגיל ככה - הקורה זה הרצפה של מרפסת, והעומס המפורס הוא בריכה שיושבת עליו.\n"
    "\n"
    "בסטטיקה, אנחנו צריכים למצוא את הריאקציות על ידי משוואות שיוו משקל שמתאפסות ל-0 בשביל שהמבנה יהיה יציב.\n"
    "הכל מתאזן.\n"
    "עומס מפורס לא כל כך ברור איך להכניס אותו כמו שהוא למשוואה למציאת הריאקציות ולכן מה שנעשה איתו בשביל להכניס אותו למשוואה זה למצוא את הכח השקול שלו.\n"
    "\n"
    "איך עושים את זה? בתרגילים העומס המפורס מגיע עם משקל של טון למטר, והמרחק שלו במטרים, וזה כל מה שאנחנו צריכים.\n"
    "\n"
    "הנוסחא היא להכפיל את המרחק במשקל טון מטר, וככה נמצא את הכח השקול שלו, ונתייחס אליו כאילו זה כח אנכי שנמצא בדיוק באמצע שלו.\n"
    "\n"
    "קח דוגמא:"
)


def body_hebrew() -> str:
    return _BODY


def build_distributed_explanation_text(extracted: dict) -> str:
    """בונה את ההסבר הדינמי המולבש על תרגיל עומס מפורס שנשלח."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    loads = beam.get("loads") if isinstance(beam.get("loads"), list) else []

    dist_load = next(
        (ld for ld in loads if isinstance(ld, dict) and ld.get("type") == "distributed"),
        None,
    )
    if not dist_load:
        w = 4.0
        dist = 4.0
    else:
        w = float(dist_load.get("w", 4.0))
        x1 = float(dist_load.get("x1", 2.0))
        x2 = float(dist_load.get("x2", 6.0))
        dist = abs(x2 - x1)

    w_str = f"{int(w)}" if w.is_integer() else f"{w:.2f}"
    dist_str = f"{int(dist)}" if dist.is_integer() else f"{dist:.2f}"

    total = w * dist
    total_str = f"{int(round(total))}" if round(total, 2).is_integer() else f"{round(total, 2):g}"

    return (
        f"בתרגיל שיצא לנו יש עומס מפורס במשקל של {w_str}t/m, שמתפרס על מרחק של {dist_str} מטרים.\n"
        "\n"
        f"הכח השקול יהיה המשקל ({w_str}) כפול המרחק שהוא מתפרס עליו ({dist_str}).\n"
        "\n"
        f"במקרה שלו זה יהיה ככה - \u200e{w_str}*{dist_str}={total_str}t\n"
        "\n"
        "כשנמצא את זה נתייחס במציאת הריאקציות לעומס הזה כאילו הוא נראה ככה:"
    )


def build_distributed_on_support_explanation_text(extracted: dict) -> str:
    """בונה את ההסבר הדינמי המולבש על תרגיל עומס מפורס על סמך."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    loads = beam.get("loads") if isinstance(beam.get("loads"), list) else []
    supports = beam.get("supports") if isinstance(beam.get("supports"), list) else []

    dist_load = next(
        (ld for ld in loads if isinstance(ld, dict) and ld.get("type") == "distributed"),
        None,
    )
    if not dist_load:
        w = 3.0
        x1 = 1.0
        x2 = 5.0
    else:
        w = float(dist_load.get("w", 3.0))
        x1 = float(dist_load.get("x1", 1.0))
        x2 = float(dist_load.get("x2", 5.0))

    sup_A = next((s for s in supports if isinstance(s, dict) and s.get("label") == "A"), None)
    sup_B = next((s for s in supports if isinstance(s, dict) and s.get("label") == "B"), None)

    xA = float(sup_A.get("x", 0.0)) if sup_A else 0.0
    xB = float(sup_B.get("x", 10.0)) if sup_B else 10.0

    if xA > 0.0:
        moved_side_target = "הימני"
        support_x = xA
    else:
        moved_side_target = "השמאלי"
        support_x = xB

    left_dist = abs(support_x - x1)
    right_dist = abs(x2 - support_x)

    w_str = f"{int(w)}" if w.is_integer() else f"{w:.2f}"
    left_dist_str = f"{int(left_dist)}" if left_dist.is_integer() else f"{left_dist:.2f}"
    right_dist_str = f"{int(right_dist)}" if right_dist.is_integer() else f"{right_dist:.2f}"

    return (
        "כשיש לנו בתרגיל 2 סמכים, בשביל למצוא כל אחת מהריאקציות אנחנו נעשה משוואת שיווי משקל על הסמך השני. "
        "זאת אומרת שמתוך שתי משוואות, באחת מהם אנחנו נצטרך לחלק את העומס הזה ל-2 ובשניה נשאיר את המפורס כמו שהוא.\n"
        "\n"
        f"ככה נראה עומס מפורס שמתפרס על סמך. בשביל למצוא את הריאקציה של הסמך {moved_side_target}, "
        "אנחנו נצטרך לחלק את העומס הזה ל-2, החלק שמימין לסמך והחלק שמשמאלו.\n"
        "\n"
        "בתרגיל שיצא לנו זה יראה ככה:\n"
        "\n"
        f"המשקל בשתי החלקים של העומס יישאר זהה - ({w_str}t/m)\n"
        f"המרחק מתחלק ל2. החלק השמאל הוא - {left_dist_str} מטרים, והחלק הימני הוא {right_dist_str} מטרים\n"
        "\n"
        "וכשסיימנו את זה יש לנו 2 עומסים מפורסים שאתה משתמש בכל אחד מהם בהתאם לצורך בהמשך התרגיל."
    )


def build_distributed_load_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("תרגול", callback_data="intro:practice_distributed")],
        [InlineKeyboardButton("מפורס על סמך", callback_data="intro:distributed_on_support")],
    ]
    return InlineKeyboardMarkup(rows)


_PRACTICE_PROMPT = "תרצה לתרגל את זה, או שנראה מה עושים כשעומס מפורס מתפרס על סמך?"


def practice_prompt_hebrew() -> str:
    return _PRACTICE_PROMPT


_PRACTICE_QUESTION_PROMPT = (
    "בתרגיל שנשלח פה למעלה יש עומס מפורס. תשלח לי כמספרים את הכח השקול שלו ואת המרחק שלו מהחלק השמאלי של הקורה.\n"
    "לא משנה באיזה סדר אתה שולח, תשלח את זה כשני מספרים עם פסיק בלי רווח בניהם. לדוגמא - 5,4.5"
)


def practice_question_prompt_hebrew() -> str:
    return _PRACTICE_QUESTION_PROMPT


_TRY_AGAIN_PROMPT = (
    "בוא ננסה שוב.\n"
    "תשלח לי את הפתרונות כמספרים, עם פסיק באמצע לא משנה הסדר.\n"
    "(לדגומא: 4.87,5.65)"
)


def try_again_prompt_hebrew() -> str:
    return _TRY_AGAIN_PROMPT


_INVALID_FORMAT_PROMPT = (
    "בשביל שאצליח להבין את התשובות שרשמת, זה צריך להיראות בנוסח הבא - מספר,מספר.\n"
    "לדוגמא - 4.67,5"
)


def invalid_format_prompt_hebrew() -> str:
    return _INVALID_FORMAT_PROMPT


__all__ = [
    "body_hebrew",
    "build_distributed_explanation_text",
    "build_distributed_load_keyboard",
    "invalid_format_prompt_hebrew",
    "practice_prompt_hebrew",
    "practice_question_prompt_hebrew",
    "try_again_prompt_hebrew",
]






