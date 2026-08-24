# -*- coding: utf-8 -*-
"""בדיקות לזרימת תפריט סמכים ואימות הזנת מרחק מהקצה השמאלי."""
from __future__ import annotations

import pytest
from bot.draft_editor import apply_field_edit
from bot.draft_keyboard import build_draft_keyboard, edit_prompt, parse_draft_callback


def test_support_buttons_display_and_callbacks():
    extracted = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [],
        }
    }

    # בדיקת לחצנים בתפריט הראשי של הטיוטה
    kb_main = build_draft_keyboard(extracted, menu_view="main")
    buttons_main = [b for row in kb_main.inline_keyboard for b in row]
    main_texts = [b.text for b in buttons_main]

    assert "סמך קבוע" in main_texts
    assert "סמך נייד" in main_texts

    cb_pin = parse_draft_callback("d:mS1")
    assert cb_pin is not None and cb_pin.action == "menu_support" and cb_pin.index == 1

    cb_roller = parse_draft_callback("d:mS2")
    assert cb_roller is not None and cb_roller.action == "menu_support" and cb_roller.index == 2

    # בדיקת תפריט משנה לסמך
    kb_sup = build_draft_keyboard(extracted, menu_view="support_1")
    sup_buttons = [(b.text, b.callback_data) for row in kb_sup.inline_keyboard for b in row]
    assert len(sup_buttons) == 2
    assert sup_buttons[0] == ("שינוי מיקום", "d:eS1")
    assert sup_buttons[1] == ("חזור", "d:m_main")


def test_support_edit_prompt_text():
    prompt = edit_prompt({"kind": "support", "index": 1}, {})
    assert prompt == "תכתוב את המרחק במטרים של הסמך מהקצה השמאלי של הקורה"


def test_support_input_validation():
    extracted = {
        "beam": {
            "L": 10.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
            ],
            "loads": [],
        }
    }
    edit = {"kind": "support", "index": 1}

    # קלט עד 25 -> מקבל ומעדכן
    updated, errors = apply_field_edit(extracted, edit, "12.5")
    assert not errors
    assert updated["beam"]["supports"][0]["x"] == 12.5

    # קלט מעל 25 -> הודעת שגיאה
    _, errors_over = apply_field_edit(extracted, edit, "26")
    assert errors_over == ["מספר לא תקין, אנא הזן שוב."]

    # קלט 30 -> הודעת שגיאה
    _, errors_30 = apply_field_edit(extracted, edit, "30")
    assert errors_30 == ["מספר לא תקין, אנא הזן שוב."]

    # קלט שאינו מספר בלבד (תווים) -> הודעת שגיאה
    _, errors_text = apply_field_edit(extracted, edit, "abc")
    assert errors_text == ["אנא הזן מספר תקין של המרחק של הסמך מהקצה השמאלי של הקורה"]

    _, errors_mixed = apply_field_edit(extracted, edit, "12m")
    assert errors_mixed == ["אנא הזן מספר תקין של המרחק של הסמך מהקצה השמאלי של הקורה"]
