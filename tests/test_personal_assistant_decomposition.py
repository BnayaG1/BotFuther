# -*- coding: utf-8 -*-
"""שלב פרוק עומסים בעייתיים בעוזר האישי."""

from personal_assistant.screens import build_current_screen_hebrew
from personal_assistant.decomposition import (
    DecompositionState,
    advance_decomposition,
    decomposition_load_entries,
    enter_decomposition,
    next_action_goes_to_reactions,
)


EXTRACTED = {
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
            {"type": "moment", "x": 5.0, "M": 4.0},
            {"type": "point", "x": 6.0, "Fy": 2.0},
            {
                "type": "inclined",
                "x": 7.0,
                "magnitude_ton": 5.0,
                "angle_deg": 30.0,
                "incl_dir": "dr",
            },
            {"type": "distributed", "x1": 5.0, "x2": 9.0, "w": 1.0},
        ],
    },
}


def test_decomposition_load_entries_sorted_left_to_right():
    entries = decomposition_load_entries(EXTRACTED)
    assert [idx for idx, _ in entries] == [0, 4, 3]
    types = [str(ld["type"]) for _, ld in entries]
    assert types == ["distributed", "distributed", "inclined"]


def test_combined_screen_then_next_load():
    progress = enter_decomposition(EXTRACTED)
    assert progress.state == DecompositionState.ACTIVE
    assert progress.load_count == 3

    first = build_current_screen_hebrew(progress)
    assert "יש 3 עומסים בעייתיים" in first
    assert "מפורס" in first
    assert "הכח השקול = 3 × 5" in first
    assert "והתוצאה - 15t" in first
    assert "טון/מ'" not in first.split("הכח השקול =", 1)[-1].split("\n")[0]
    assert progress.has_more_loads is True
    assert next_action_goes_to_reactions(progress) is False

    advance_decomposition(progress)
    assert progress.load_cursor == 1
    second = build_current_screen_hebrew(progress)
    assert "עברנו לעומס הבא" in second
    assert "שוב" not in second or "מפורס" in second


def test_empty_skip_goes_to_reactions_flag():
    empty = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 1.0}],
        },
    }
    skip = enter_decomposition(empty)
    assert skip.is_skip is True
    assert skip.state == DecompositionState.DONE
    assert next_action_goes_to_reactions(skip) is True
    text = build_current_screen_hebrew(skip)
    assert "אין עומסים מפורסים או אלכסוניים" in text
    assert "ריאקציות" in text


def test_single_load_solution_goes_to_reactions():
    one = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [
                {
                    "type": "inclined",
                    "x": 2.0,
                    "magnitude_ton": 4.0,
                    "angle_deg": 30.0,
                    "incl_dir": "dr",
                }
            ],
        },
    }
    progress = enter_decomposition(one)
    assert progress.load_count == 1
    screen = build_current_screen_hebrew(progress)
    assert "יש עומס בעייתי אחד" in screen
    assert "אלכסוני" in screen
    assert "לפרק את העומס הזה מאלכסוני" in screen
    assert "Fx =" in screen and "Fy =" in screen
    assert next_action_goes_to_reactions(progress) is True
    assert progress.has_more_loads is False
