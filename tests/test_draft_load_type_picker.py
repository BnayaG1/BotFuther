# -*- coding: utf-8 -*-
"""תפריט בחירת סוג עומס בטיוטה — כולל עומס צירי וזרימת «הוסף עומס»."""
from __future__ import annotations

from bot.draft_editor import add_load_of_type, is_axial_point_load, load_picker_kind, set_load_type
from bot.draft_keyboard import (
    ADD_LOAD_TYPE_PICKER_IDX,
    _build_load_type_picker_rows,
    build_draft_keyboard,
    draft_display_text,
    parse_draft_callback,
)

EXTRACTED = {
    "beam": {
        "L": 10.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
        "loads": [{"type": "point", "x": 4.0, "Fy": 3.0}],
    }
}


def test_load_type_picker_has_axial_instead_of_back():
    rows = _build_load_type_picker_rows(1, {"type": "point", "Fy": 0.0, "_draft_new": True})
    flat = [btn.text for row in rows for btn in row]
    assert any("צירי" in label for label in flat)
    assert not any("חזרה" in label for label in flat)


def test_parse_axial_load_type_callback():
    cb = parse_draft_callback("d:y2a")
    assert cb is not None
    assert cb.action == "set_load_type"
    assert cb.index == 2
    assert cb.dir == "axial"


def test_set_load_type_axial_creates_fx_only_point():
    extracted = {
        "beam": {
            "L": 10.0,
            "loads": [{"type": "point", "x": 2.0, "Fy": 5.0, "_draft_new": True}],
        }
    }
    updated = set_load_type(extracted, 1, "axial")
    ld = updated["beam"]["loads"][0]
    assert float(ld["Fy"]) == 0.0
    assert float(ld["Fx"]) == 5.0
    assert is_axial_point_load(ld)


def test_set_load_type_point_clears_axial_marker():
    extracted = {
        "beam": {
            "L": 10.0,
            "loads": [
                {
                    "type": "point",
                    "x": 2.0,
                    "Fy": 0.0,
                    "Fx": 4.0,
                    "_draft_axial": True,
                }
            ],
        }
    }
    updated = set_load_type(extracted, 1, "point")
    ld = updated["beam"]["loads"][0]
    assert float(ld["Fy"]) == 4.0
    assert float(ld.get("Fx", 0.0)) == 0.0
    assert load_picker_kind(ld) == "point"


def test_add_load_button_opens_type_picker_before_adding():
    keyboard = build_draft_keyboard(EXTRACTED, type_picker_idx=ADD_LOAD_TYPE_PICKER_IDX)
    flat = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert any("נקודתי" in label for label in flat)
    assert any("מומנט" in label for label in flat)
    assert not any(label.strip() == "➕" for label in flat)
    assert len(EXTRACTED["beam"]["loads"]) == 1


def test_add_load_of_type_appends_empty_load_row():
    updated = add_load_of_type(EXTRACTED, "moment")
    assert len(updated["beam"]["loads"]) == 2
    ld = updated["beam"]["loads"][-1]
    assert ld["type"] == "moment"
    assert ld.get("_draft_new") is True
    assert float(ld.get("M", 0.0)) == 0.0


def test_add_point_load_appears_even_when_existing_load_at_x0():
    """רגרסיה: מיזוג עומסים באותו x בלע עומס טיוטה חדש ליד הקצה."""
    extracted = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [{"type": "point", "x": 0.0, "Fy": 5.0}],
        }
    }
    updated = add_load_of_type(extracted, "point")
    loads = updated["beam"]["loads"]
    assert len(loads) == 2
    assert float(loads[0]["Fy"]) == 5.0
    assert loads[1].get("_draft_new") is True
    assert float(loads[1].get("Fy", 0.0)) == 0.0


def test_add_axial_load_appears_even_when_existing_load_at_x0():
    extracted = {
        "beam": {
            "L": 8.0,
            "loads": [{"type": "point", "x": 0.2, "Fy": 2.0}],
        }
    }
    updated = add_load_of_type(extracted, "axial")
    loads = updated["beam"]["loads"]
    assert len(loads) == 2
    assert loads[-1].get("_draft_new") is True
    assert loads[-1].get("_draft_axial") is True


def test_setting_distance_on_new_load_keeps_draft_new_and_shows_x():
    from bot.draft_editor import apply_field_edit
    from bot.draft_keyboard import _build_load_row_buttons, draft_display_text

    extracted = add_load_of_type(EXTRACTED, "point")
    idx = len(extracted["beam"]["loads"])
    updated, errors = apply_field_edit(
        extracted,
        {"kind": "load_x", "index": idx},
        "4",
    )
    assert not errors
    ld = updated["beam"]["loads"][-1]
    assert ld.get("_draft_new") is True
    assert ld.get("_user_x") is True
    assert float(ld["x"]) == 4.0
    assert float(ld.get("Fy", 0.0)) == 0.0

    text = draft_display_text(updated)
    assert "x = 4" in text

    buttons = _build_load_row_buttons(updated["beam"], idx, ld)
    # כיוון | כח | מרחק | ...
    assert "4" in buttons[2].text
    assert buttons[0].text.strip() == "↓"
    assert "·" in buttons[1].text  # כח עדיין ריק


def test_draft_finalize_does_not_merge_nearby_point_loads():
    """בטיוטה עומסים נקודתיים קרובים נשארים נפרדים (בלי מיזוג 0.35m)."""
    from bot.draft_editor import _finalize_draft, apply_field_edit

    extracted = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {"type": "point", "x": 2.0, "Fy": 3.0},
                {"type": "point", "x": 2.2, "Fy": 1.0},
            ],
        }
    }
    finalized = _finalize_draft(extracted)
    assert len(finalized["beam"]["loads"]) == 2

    # גם אחרי עריכת מרחק — לא מתמזגים
    updated, errors = apply_field_edit(
        extracted,
        {"kind": "load_x", "index": 2},
        "2.1",
    )
    assert not errors
    updated = _finalize_draft(updated)
    assert len(updated["beam"]["loads"]) == 2
    xs = sorted(float(ld["x"]) for ld in updated["beam"]["loads"])
    assert xs[0] == 2.0
    assert abs(xs[1] - 2.1) < 1e-9


def test_parse_add_load_type_callback():
    cb = parse_draft_callback("d:y0m")
    assert cb is not None
    assert cb.action == "set_load_type"
    assert cb.index == 0
    assert cb.dir == "moment"


def test_add_load_picker_hides_flip_direction_row():
    rows = _build_load_type_picker_rows(0, {}, adding_new=True)
    flat = [btn.text for row in rows for btn in row]
    assert not any("היפוך" in label for label in flat)


def test_new_point_load_direction_icon_is_down_arrow():
    from bot.draft_editor import add_load_of_type
    from bot.draft_keyboard import _build_load_row_buttons, _draft_new_dir_icon

    extracted = add_load_of_type(EXTRACTED, "point")
    ld = extracted["beam"]["loads"][-1]
    assert _draft_new_dir_icon(ld) == "↓"
    buttons = _build_load_row_buttons(extracted["beam"], len(extracted["beam"]["loads"]), ld)
    assert buttons[0].text.strip() == "↓"


def test_axial_load_mag_edit_keeps_axial_not_vertical_point():
    from bot.draft_editor import apply_field_edit
    from bot.draft_keyboard import draft_display_text

    extracted = add_load_of_type(EXTRACTED, "axial")
    idx = len(extracted["beam"]["loads"])
    updated, errors = apply_field_edit(
        extracted,
        {"kind": "load_mag", "index": idx},
        "6",
    )
    assert not errors
    ld = updated["beam"]["loads"][-1]
    assert float(ld.get("Fy", 0.0)) == 0.0
    assert float(ld.get("Fx", 0.0)) == 6.0
    assert is_axial_point_load(ld)
    text = draft_display_text(updated)
    assert "צירי" in text
    assert "→ 6" in text


def test_axial_mag_edit_preserves_left_direction():
    from bot.draft_editor import apply_field_edit, toggle_any_load_direction
    from bot.vision import finalize_beam_extraction

    extracted = add_load_of_type(EXTRACTED, "axial")
    idx = len(extracted["beam"]["loads"])
    extracted = toggle_any_load_direction(extracted, idx)
    updated, errors = apply_field_edit(
        extracted,
        {"kind": "load_mag", "index": idx},
        "6",
    )
    assert not errors
    updated = finalize_beam_extraction(updated)
    ld = updated["beam"]["loads"][-1]
    assert float(ld["Fx"]) == -6.0
    assert float(ld.get("Fy", 0.0)) == 0.0
    assert "direction" not in ld


def test_draft_display_labels_axial_load():
    extracted = {
        "beam": {
            "L": 10.0,
            "loads": [{"type": "point", "x": 3.0, "Fy": 0.0, "Fx": 7.0}],
        }
    }
    text = draft_display_text(extracted)
    assert "צירי" in text
    assert "→ 7" in text
