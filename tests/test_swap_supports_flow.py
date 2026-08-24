# -*- coding: utf-8 -*-
"""בדיקות ללחצן החלפת סמכים ולנרמול סמכים מבוסס תוויות מפורשות."""
from __future__ import annotations

import pytest
from bot.draft_editor import swap_supports
from bot.draft_keyboard import build_draft_keyboard, parse_draft_callback
from bot.vision import _ensure_simply_supported_pin_roller_pair


def test_swap_supports_button_in_main_menu():
    extracted = {
        "beam": {
            "L": 10.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [],
        }
    }

    kb = build_draft_keyboard(extracted, menu_view="main")
    # Row containing supports
    support_row = [row for row in kb.inline_keyboard if any(b.callback_data == "d:swS" for b in row)][0]
    row_buttons = [(b.text, b.callback_data) for b in support_row]
    assert len(row_buttons) == 3
    assert row_buttons[0] == ("סמך נייד", "d:mS2")
    assert row_buttons[1] == ("החלף סמכים", "d:swS")
    assert row_buttons[2] == ("סמך קבוע", "d:mS1")

    kb_sub = build_draft_keyboard(extracted, menu_view="support_1")
    sub_buttons = [(b.text, b.callback_data) for row in kb_sub.inline_keyboard for b in row]
    assert len(sub_buttons) == 2
    assert sub_buttons[0] == ("שינוי מיקום", "d:eS1")
    assert sub_buttons[1] == ("חזור", "d:m_main")


def test_parse_swap_supports_callback():
    cb = parse_draft_callback("d:swS")
    assert cb is not None
    assert cb.action == "swap_supports"


def test_swap_supports_function_swaps_types_and_labels():
    extracted = {
        "beam": {
            "L": 10.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0, "hatch_count": 2, "has_full_wall_hatch": False},
                {"label": "B", "type": "roller", "x": 10.0, "hatch_count": 0},
            ],
            "loads": [],
        }
    }

    swapped = swap_supports(extracted)
    supports = swapped["beam"]["supports"]
    assert supports[0]["type"] == "roller"
    assert supports[1]["type"] == "pin"
    assert "hatch_count" not in supports[0]
    assert "has_full_wall_hatch" not in supports[0]
    assert "hatch_count" not in supports[1]
    assert swapped["beam"]["pin_support_label"] == "B"
    assert swapped["beam"]["roller_support_label"] == "A"


def test_ensure_simply_supported_respects_explicit_labels():
    supports = [
        {"label": "A", "type": "fixed", "x": 0.0},
        {"label": "B", "type": "fixed", "x": 10.0},
    ]
    beam = {
        "pin_support_label": "B",
        "roller_support_label": "A",
        "supports": supports,
    }

    _ensure_simply_supported_pin_roller_pair(supports, beam)
    assert supports[0]["label"] == "A" and supports[0]["type"] == "roller"
    assert supports[1]["label"] == "B" and supports[1]["type"] == "pin"
