# -*- coding: utf-8 -*-
"""תיקון טיוטה בשפה חופשית — בדיקות ל-Gemini classifier + executor."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bot.draft_keyboard import build_draft_approve_keyboard
from bot.draft_nl_edit import (
    _execute_action,
    apply_nl_draft_edit,
    convert_inclined_loads_to_vertical,
)

EXTRACTED = {
    "exercise_type": "beam",
    "beam": {
        "L": 10.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
        "loads": [
            {"type": "point", "x": 5.0, "Fy": 3.0},
        ],
    },
}


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def test_build_draft_approve_keyboard_only_approve():
    markup = build_draft_approve_keyboard()
    buttons = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert buttons == ["d:a"]
    assert markup.inline_keyboard[0][0].text == "אישור"


# ---------------------------------------------------------------------------
# apply_nl_draft_edit — edge cases
# ---------------------------------------------------------------------------

def test_apply_nl_draft_edit_empty_instruction():
    updated, errors = apply_nl_draft_edit(EXTRACTED, "   ")
    assert updated is None
    assert errors


def test_apply_nl_draft_edit_gemini_failure():
    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "bot.draft_nl_edit.friendly_gemini_error",
            return_value="שגיאת בדיקה",
        ),
    ):
        updated, errors = apply_nl_draft_edit(EXTRACTED, "שנה עומס ל-5")

    assert updated is None
    assert errors == ["שגיאת בדיקה"]


# ---------------------------------------------------------------------------
# convert_inclined_loads_to_vertical
# ---------------------------------------------------------------------------

def test_convert_inclined_keeps_magnitude_as_fy():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {
                    "type": "inclined",
                    "x": 4.0,
                    "magnitude_ton": 7.5,
                    "angle_deg": 30.0,
                    "incl_dir": "dr",
                    "Fx": 6.495,
                    "Fy": 3.75,
                },
                {"type": "point", "x": 1.0, "Fy": 2.0},
            ],
        },
    }
    out = convert_inclined_loads_to_vertical(extracted)
    loads = out["beam"]["loads"]
    assert loads[0]["type"] == "point"
    assert float(loads[0]["Fy"]) == 7.5
    assert float(loads[0]["Fx"]) == 0.0
    assert "magnitude_ton" not in loads[0]
    assert loads[1]["type"] == "point"
    assert float(loads[1]["Fy"]) == 2.0


# ---------------------------------------------------------------------------
# _execute_action — set_beam_length
# ---------------------------------------------------------------------------

def test_exec_set_beam_length_absolute():
    action = {"action": "set_beam_length", "value": 12.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    assert float(out["beam"]["L"]) == 12.0
    assert out["beam"].get("_user_L") is True


def test_exec_set_beam_length_delta_positive():
    action = {"action": "set_beam_length", "delta": 2.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    assert float(out["beam"]["L"]) == 12.0


def test_exec_set_beam_length_delta_negative():
    action = {"action": "set_beam_length", "delta": -3.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    assert float(out["beam"]["L"]) == 7.0


# ---------------------------------------------------------------------------
# _execute_action — move_support
# ---------------------------------------------------------------------------

def test_exec_move_support_pin_right():
    action = {"action": "move_support", "support_type": "pin", "delta_x": 1.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    assert float(out["beam"]["supports"][0]["x"]) == 1.0
    assert out["beam"]["supports"][0].get("_user_x") is True
    assert float(out["beam"]["loads"][0]["x"]) == 5.0  # עומס לא זז


def test_exec_move_support_to_abs_x():
    action = {"action": "move_support", "support_type": "roller", "target_x": 8.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    assert float(out["beam"]["supports"][1]["x"]) == 8.0


# ---------------------------------------------------------------------------
# _execute_action — move_load
# ---------------------------------------------------------------------------

def test_exec_move_load_moment_to_abs_x():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "moment", "x": 2.0, "M": 5.0},
                {"type": "point", "x": 5.0, "Fy": 3.0},
            ],
        },
    }
    action = {"action": "move_load", "load_type": "moment", "target_x": 6.0}
    out = _execute_action(extracted, action)
    assert out is not None
    assert float(out["beam"]["loads"][0]["x"]) == 6.0
    assert out["beam"]["loads"][0].get("_user_x") is True
    assert float(out["beam"]["loads"][1]["x"]) == 5.0  # עומס שני לא זז


def test_exec_move_load_right_moment():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 12.0,
            "loads": [
                {"type": "moment", "x": 2.0, "M": 10.0},
                {"type": "moment", "x": 8.0, "M": 15.0},
            ],
        },
    }
    action = {"action": "move_load", "load_type": "moment", "side": "right", "target_x": 12.0}
    out = _execute_action(extracted, action)
    assert out is not None
    assert float(out["beam"]["loads"][0]["x"]) == 2.0   # שמאלי לא זז
    assert float(out["beam"]["loads"][1]["x"]) == 12.0  # ימני זז


def test_exec_move_load_delta():
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 10.0, "loads": [{"type": "point", "x": 3.0, "Fy": 2.0}]},
    }
    action = {"action": "move_load", "load_type": "point", "delta_x": 1.0}
    out = _execute_action(extracted, action)
    assert out is not None
    assert float(out["beam"]["loads"][0]["x"]) == 4.0


# ---------------------------------------------------------------------------
# _execute_action — resize_distributed
# ---------------------------------------------------------------------------

def _dist_extracted(x1: float = 0.0, x2: float = 4.0, L: float = 10.0) -> dict:
    return {
        "exercise_type": "beam",
        "beam": {
            "L": L,
            "loads": [
                {
                    "type": "distributed",
                    "x1": x1,
                    "x2": x2,
                    "w": 3.0,
                    "shape": "rectangular",
                }
            ],
        },
    }


def test_exec_resize_distributed_abs_x1_x2():
    action = {"action": "resize_distributed", "x1": 2.0, "x2": 6.0}
    out = _execute_action(_dist_extracted(0.0, 4.0), action)
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert float(ld["x1"]) == 2.0
    assert float(ld["x2"]) == 6.0
    assert ld.get("_user_span") is True


def test_exec_resize_distributed_extend_right_edge():
    action = {"action": "resize_distributed", "edge": "right", "delta": 2.0}
    out = _execute_action(_dist_extracted(0.0, 4.0), action)
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert float(ld["x1"]) == 0.0
    assert float(ld["x2"]) == 6.0


def test_exec_resize_two_distributed_picks_right():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "distributed", "x1": 0.0, "x2": 3.0, "w": 2.0, "shape": "rectangular"},
                {"type": "distributed", "x1": 6.0, "x2": 8.0, "w": 2.0, "shape": "rectangular"},
            ],
        },
    }
    action = {"action": "resize_distributed", "side": "right", "edge": "right", "delta": 1.0}
    out = _execute_action(extracted, action)
    assert out is not None
    left, right = out["beam"]["loads"][0], out["beam"]["loads"][1]
    assert float(left["x2"]) == 3.0   # שמאלי לא זז
    assert float(right["x2"]) == 9.0  # ימני התארך


# ---------------------------------------------------------------------------
# _execute_action — set_angle
# ---------------------------------------------------------------------------

def test_exec_set_angle():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {
                    "type": "inclined",
                    "x": 5.0,
                    "magnitude_ton": 6.0,
                    "angle_deg": 30.0,
                    "incl_dir": "dr",
                    "Fx": 5.196,
                    "Fy": 3.0,
                }
            ],
        },
    }
    action = {"action": "set_angle", "angle_deg": 45.0}
    out = _execute_action(extracted, action)
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert float(ld["angle_deg"]) == 45.0
    assert abs(float(ld["Fx"]) - abs(float(ld["Fy"]))) < 0.05


# ---------------------------------------------------------------------------
# _execute_action — flip_direction
# ---------------------------------------------------------------------------

def test_exec_flip_inclined_to_dl():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {
                    "type": "inclined",
                    "x": 5.0,
                    "magnitude_ton": 6.0,
                    "angle_deg": 45.0,
                    "incl_dir": "dr",
                    "Fx": 4.24,
                    "Fy": 4.24,
                }
            ],
        },
    }
    action = {"action": "flip_direction", "load_type": "inclined", "direction": "dl"}
    out = _execute_action(extracted, action)
    assert out is not None
    assert out["beam"]["loads"][0]["incl_dir"] == "dl"
    assert float(out["beam"]["loads"][0]["Fx"]) < 0


def test_exec_flip_axial_toggle():
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 10.0, "loads": [{"type": "point", "x": 4.0, "Fy": 0.0, "Fx": 5.0}]},
    }
    action = {"action": "flip_direction", "load_type": "axial"}
    out = _execute_action(extracted, action)
    assert out is not None
    assert float(out["beam"]["loads"][0]["Fx"]) == -5.0


# ---------------------------------------------------------------------------
# _execute_action — change_load_type
# ---------------------------------------------------------------------------

def test_exec_change_inclined_to_point():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "inclined", "x": 5.0, "magnitude_ton": 6.0,
                 "angle_deg": 30.0, "incl_dir": "dr"}
            ],
        },
    }
    action = {"action": "change_load_type", "from_type": "inclined", "to_type": "point"}
    out = _execute_action(extracted, action)
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert ld["type"] == "point"
    assert float(ld["Fy"]) == 6.0
    assert float(ld.get("Fx", 0.0)) == 0.0


def test_exec_change_all_inclined_to_vertical():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "inclined", "x": 2.0, "magnitude_ton": 4.0, "angle_deg": 30.0, "incl_dir": "dr"},
                {"type": "inclined", "x": 7.0, "magnitude_ton": 5.0, "angle_deg": 45.0, "incl_dir": "dl"},
            ],
        },
    }
    action = {"action": "change_load_type", "from_type": "inclined", "to_type": "point", "all": True}
    out = _execute_action(extracted, action)
    assert out is not None
    for ld in out["beam"]["loads"]:
        assert ld["type"] == "point"


def test_exec_change_point_to_moment():
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 10.0, "loads": [{"type": "point", "x": 4.0, "Fy": 8.0, "Fx": 0.0}]},
    }
    action = {"action": "change_load_type", "from_type": "point", "to_type": "moment"}
    out = _execute_action(extracted, action)
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert ld["type"] == "moment"
    assert float(ld["M"]) == 8.0


# ---------------------------------------------------------------------------
# _execute_action — add_load
# ---------------------------------------------------------------------------

def test_exec_add_axial_load():
    action = {"action": "add_load", "load_type": "axial", "x": 5.0, "magnitude": 5.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    ld = out["beam"]["loads"][-1]
    assert ld["type"] == "point"
    assert float(ld["Fy"]) == 0.0
    assert float(ld["Fx"]) == 5.0


def test_exec_add_vertical_load_with_magnitude():
    action = {"action": "add_load", "load_type": "point", "x": 3.0, "magnitude": 8.0, "direction": "down"}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    ld = out["beam"]["loads"][-1]
    assert float(ld["Fy"]) == 8.0
    assert float(ld["x"]) == 3.0


def test_exec_add_moment_load():
    action = {"action": "add_load", "load_type": "moment", "x": 2.0, "magnitude": 10.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    ld = out["beam"]["loads"][-1]
    assert ld["type"] == "moment"
    assert float(ld["M"]) == 10.0
    assert float(ld["x"]) == 2.0


# ---------------------------------------------------------------------------
# _execute_action — delete_load
# ---------------------------------------------------------------------------

def test_exec_delete_load():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "moment", "x": 2.0, "M": 5.0},
                {"type": "point", "x": 5.0, "Fy": 3.0},
            ],
        },
    }
    action = {"action": "delete_load", "load_type": "moment"}
    out = _execute_action(extracted, action)
    assert out is not None
    assert len(out["beam"]["loads"]) == 1
    assert out["beam"]["loads"][0]["type"] == "point"


# ---------------------------------------------------------------------------
# _execute_action — set_magnitude
# ---------------------------------------------------------------------------

def test_exec_set_magnitude_vertical():
    action = {"action": "set_magnitude", "load_type": "point", "magnitude": 8.0}
    out = _execute_action(EXTRACTED, action)
    assert out is not None
    assert float(out["beam"]["loads"][0]["Fy"]) == 8.0


def test_exec_set_magnitude_moment():
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 10.0, "loads": [{"type": "moment", "x": 3.0, "M": 5.0}]},
    }
    action = {"action": "set_magnitude", "load_type": "moment", "magnitude": 12.0}
    out = _execute_action(extracted, action)
    assert out is not None
    assert float(out["beam"]["loads"][0]["M"]) == 12.0


# ---------------------------------------------------------------------------
# apply_nl_draft_edit integration — Gemini returns action dict
# ---------------------------------------------------------------------------

def _mock_gemini_action(action: dict):
    """Helper: מחזיר mock ש-Gemini מחזיר action JSON."""
    import json
    fake_response = MagicMock()
    fake_response.text = json.dumps(action)
    return fake_response


def test_apply_nl_via_gemini_set_beam_length():
    action = {"action": "set_beam_length", "value": 12.0}
    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            return_value=_mock_gemini_action(action),
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(EXTRACTED, "שנה אורך הקורה ל-12")

    assert errors == []
    assert float(updated["beam"]["L"]) == 12.0


def test_apply_nl_via_gemini_move_support():
    action = {"action": "move_support", "support_type": "pin", "delta_x": 1.0}
    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            return_value=_mock_gemini_action(action),
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(EXTRACTED, "הזיז את הסמך הקבוע מטר ימינה")

    assert errors == []
    assert float(updated["beam"]["supports"][0]["x"]) == 1.0
    assert float(updated["beam"]["loads"][0]["x"]) == 5.0  # עומס לא זז


def test_apply_nl_via_gemini_change_type_inclined_to_point():
    action = {"action": "change_load_type", "from_type": "inclined", "to_type": "point"}
    inclined = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "inclined", "x": 5.0, "magnitude_ton": 6.0,
                 "angle_deg": 45.0, "incl_dir": "dl"}
            ],
        },
    }
    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            return_value=_mock_gemini_action(action),
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(inclined, "שנה את האלכסוני לאנכי")

    assert errors == []
    ld = updated["beam"]["loads"][0]
    assert ld["type"] == "point"
    assert float(ld["Fy"]) == 6.0
    assert float(ld.get("Fx", 0.0)) == 0.0


def test_apply_nl_unknown_action_returns_error():
    action = {"action": "fly_to_moon"}
    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            return_value=_mock_gemini_action(action),
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(EXTRACTED, "עשה משהו מוזר")

    assert updated is None
    assert errors
