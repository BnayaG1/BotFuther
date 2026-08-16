# -*- coding: utf-8 -*-
"""קובץ פתיחה — הודעת מבוא לסטטיקה + כפתורי נושאים."""
from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from pathlib import Path

from exercise_generator.geometry import row_from_breaks
from exercise_generator.schema import (
    Exercise,
    LabeledPoint,
    PointLoad,
    Support,
)
from intro.distributed_load import body_hebrew as distributed_load_body_hebrew
from intro.fixed_support_exercises import body_hebrew as fixed_support_body_hebrew
from intro.inclined_load import body_hebrew as inclined_load_body_hebrew
from intro.support_exercises import body_hebrew as support_body_hebrew

_OPENING_TEXT = "לאן תרצה לקחת את זה?"

_HOW_TO_APPROACH_TEXT = (
    "בסטטיקה, העיקרון המנחה הוא שבסופו של דבר הכל מתאפס ל-0, ובחודשים הראשונים של הלמידה התרגילים ייראו ככה:\n"
    "קורה + 2 סמכים\\ריתום + עומסים.\n"
    "\n"
    "זה הכל.\n"
    "\n"
    "תבחר סמכים או ריתום בהתאם למה שאתה רוצה שנעבור עליו ביחד עד לפתרון."
)

_INTRO_MAIN_BUTTONS = [
    ("how_to_approach", "מבוא"),
    ("distributed_load", "עומס מפורס"),
    ("inclined_load", "עומס אלכסוני"),
]

_HOW_TO_APPROACH_BUTTONS = [
    ("support_exercises", "סמכים"),
    ("fixed_support_exercises", "ריתום"),
]

_INTRO_TOPIC_BODIES: dict[str, Callable[[], str]] = {
    "distributed_load": distributed_load_body_hebrew,
    "inclined_load": inclined_load_body_hebrew,
    "support_exercises": support_body_hebrew,
    "fixed_support_exercises": fixed_support_body_hebrew,
}


def opening_message_hebrew() -> str:
    return _OPENING_TEXT


def how_to_approach_message_hebrew() -> str:
    return _HOW_TO_APPROACH_TEXT


def build_opening_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(title, callback_data=f"intro:{topic_id}")]
        for topic_id, title in _INTRO_MAIN_BUTTONS
    ]
    return InlineKeyboardMarkup(rows)


def build_how_to_approach_keyboard() -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(title, callback_data=f"intro:{topic_id}")
        for topic_id, title in _HOW_TO_APPROACH_BUTTONS
    ]
    return InlineKeyboardMarkup([row])


def build_mavo_continue_keyboard() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton("המשך", callback_data="intro:mavo_continue")]
    return InlineKeyboardMarkup([row])


def mavo_followup_message_hebrew(exercise_type: str = "סמכים") -> str:
    return (
        f"מעולה, ככה נראה תרגיל {exercise_type} פשוט.\n"
        "\n"
        "כשאתה ניגש לתרגיל, דבר ראשון אתה מעתיק למחברת את התרגיל בצורה מסודרת עם קווי המדידות. אם יש עומסים מפורסים או אלכסוניים, אתה מפרק אותם לפני שמתחילים לפתור את התרגיל.\n"
        "\n"
        "לחץ המשך ונמשיך"
    )


def intro_topic_body_hebrew(topic_id: str) -> str | None:
    func = _INTRO_TOPIC_BODIES.get(topic_id)
    if func is None:
        return None
    return func()


def parse_intro_callback(data: str) -> str | None:
    """
    intro:<topic_id>
    → topic_id, or None if not an intro callback.
    """
    if not data.startswith("intro:"):
        return None
    topic_id = data.split(":", 1)[-1]
    valid_ids = {
        "how_to_approach",
        "main",
        "mavo_continue",
        "practice_inclined",
        "practice_distributed",
        "distributed_on_support",
        "inclined_try_again",
        "inclined_show_solution",
        "distributed_try_again",
        "distributed_show_solution",
        *_INTRO_TOPIC_BODIES.keys(),
    }
    if topic_id in valid_ids:
        return topic_id
    return None


def build_mavo_exercise() -> Exercise:
    return Exercise(
        L=10.0,
        support_mode="simply_supported",
        supports=[
            Support(label="A", type="pin", x=0.0),
            Support(label="B", type="roller", x=10.0),
        ],
        loads=[
            PointLoad(type="point", x=3.0, Fy=10.0, Fx=0.0),
            PointLoad(type="point", x=8.0, Fy=0.0, Fx=5.0),
        ],
        labeled_points=[
            LabeledPoint(label="C", x=3.0),
            LabeledPoint(label="D", x=8.0),
        ],
        dim_row_top=row_from_breaks([0.0, 3.0, 8.0, 10.0]),
        dim_row_bottom=row_from_breaks([0.0, 10.0]),
        family="intro_mavo",
    )


def generate_mavo_exercise_png(out_dir: Path, stem: str = "mavo_exercise") -> Path:
    from exercise_generator.render.export import render_exercise_png

    ex = build_mavo_exercise()
    out_path = out_dir / f"{stem}.png"
    return render_exercise_png(ex, out_path)


def build_fixed_mavo_exercise() -> Exercise:
    return Exercise(
        L=10.0,
        support_mode="cantilever",
        supports=[
            Support(label="A", type="fixed", x=0.0),
        ],
        loads=[
            PointLoad(type="point", x=3.0, Fy=10.0, Fx=0.0),
            PointLoad(type="point", x=8.0, Fy=0.0, Fx=5.0),
        ],
        labeled_points=[
            LabeledPoint(label="B", x=3.0),
            LabeledPoint(label="C", x=8.0),
            LabeledPoint(label="D", x=10.0),
        ],
        dim_row_top=row_from_breaks([0.0, 3.0, 8.0, 10.0]),
        dim_row_bottom=row_from_breaks([0.0, 10.0]),
        family="intro_fixed_mavo",
    )


def generate_fixed_mavo_exercise_png(out_dir: Path, stem: str = "fixed_mavo_exercise") -> Path:
    from exercise_generator.render.export import render_exercise_png

    ex = build_fixed_mavo_exercise()
    out_path = out_dir / f"{stem}.png"
    return render_exercise_png(ex, out_path)
