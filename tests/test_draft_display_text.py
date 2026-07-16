# -*- coding: utf-8 -*-
"""הודעת טיוטה — רק נתונים, בלי הערות או אזהרות."""
from __future__ import annotations

from bot.draft_keyboard import draft_data_only_text, draft_display_text
from bot.vision import package_extraction_response

EXTRACTED = {
    "beam": {
        "L": 7.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 7.0},
        ],
        "loads": [
            {"type": "point", "x": 3.0, "Fy": 5.0},
            {"type": "point", "x": 0.0, "Fy": 0.0, "_draft_new": True},
        ],
    }
}


def test_draft_display_has_no_approval_header():
    text = draft_display_text(EXTRACTED)
    assert "אימות נתונים" not in text


def test_draft_display_has_no_validation_warnings():
    extracted = package_extraction_response(
        EXTRACTED,
        partial=True,
        validation_issues=["אורך הקורה לא תואם לסמכים"],
    )
    text = draft_display_text(extracted)
    assert "סתירות" not in text
    assert "אורך הקורה לא תואם" not in text


def test_draft_display_ignores_errors_param():
    text = draft_display_text(EXTRACTED, errors=["שגיאת בדיקה"])
    assert "שגיאת בדיקה" not in text
    assert "⚠️" not in text


def test_draft_display_ignores_type_picker_prompt():
    text = draft_display_text(EXTRACTED, type_picker_idx=2)
    assert "בחר סוג" not in text
    assert "לחיצה על" not in text


def test_draft_display_empty_load_is_label_only():
    text = draft_display_text(EXTRACTED)
    assert "2. חדש" in text
    assert "לחץ" not in text
    assert "מלא כיוון" not in text


def test_draft_display_shows_distance_after_user_sets_x_on_empty_load():
    extracted = {
        "beam": {
            "L": 7.0,
            "loads": [
                {
                    "type": "point",
                    "x": 4.0,
                    "Fy": 0.0,
                    "Fx": 0.0,
                    "_draft_new": True,
                    "_user_x": True,
                }
            ],
        }
    }
    text = draft_display_text(extracted)
    assert "נקודתי" in text
    assert "x = 4" in text
    assert "חדש" not in text or "x = 4" in text


def test_draft_message_and_keyboard_show_same_load_distance():
    """רגרסיה: טקסט ההודעה לא יריץ finalize נפרד מהמקלדת."""
    from bot.draft_keyboard import _build_load_row_buttons, _load_summary_he

    extracted = {
        "beam": {
            "L": 12.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 12.0},
            ],
            "labeled_points": [
                {"label": "A", "x": 0.0},
                {"label": "C", "x": 4.0},
                {"label": "B", "x": 12.0},
            ],
            # x פנימי שונה מתווית — כמו אחרי חילוץ לפני/אחרי נורמליזציה חלקית.
            "loads": [
                {"type": "point", "x": 3.5, "Fy": 5.0, "label_at": "C"},
            ],
        }
    }
    beam = extracted["beam"]
    ld = beam["loads"][0]
    summary = _load_summary_he(beam, 1, ld)
    buttons = _build_load_row_buttons(beam, 1, ld)
    dist_btn = buttons[2].text.replace(" ", "")
    assert "x = 4" in summary
    assert "4" in dist_btn

    text = draft_display_text(extracted)
    assert "x = 4" in text
    # וידוא שלא «תיקנו» שקטה ל-x אחר בטקסט בלבד.
    assert "x = 3.5" not in text


def test_draft_data_only_includes_structural_fields():
    text = draft_data_only_text(EXTRACTED)
    assert "7" in text
    assert "A" in text
    assert "B" in text
    assert "5" in text
    assert "אורך הקורה" in text
    assert "סמכים" in text
    assert "עומסים" in text
