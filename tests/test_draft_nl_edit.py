# -*- coding: utf-8 -*-
"""תיקון טיוטה בשפה חופשית + מקלדת אישור."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from bot.draft_keyboard import build_draft_approve_keyboard
from bot.draft_nl_edit import (
    apply_nl_draft_edit,
    convert_inclined_loads_to_vertical,
    try_add_load,
    try_move_load_to_beam_end,
    try_resize_distributed_load,
    wants_inclined_to_vertical,
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


def test_build_draft_approve_keyboard_only_approve():
    markup = build_draft_approve_keyboard()
    buttons = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert buttons == ["d:a"]
    assert markup.inline_keyboard[0][0].text == "אישור"


def test_apply_nl_draft_edit_empty_instruction():
    updated, errors = apply_nl_draft_edit(EXTRACTED, "   ")
    assert updated is None
    assert errors


def test_apply_nl_draft_edit_updates_L_via_mock_gemini():
    updated_payload = {
        "exercise_type": "beam",
        "beam": {
            "L": 12.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 12.0},
            ],
            "loads": [
                {"type": "point", "x": 5.0, "Fy": 3.0},
            ],
        },
    }
    fake_response = MagicMock()
    fake_response.text = (
        '{"exercise_type":"beam","beam":{"L":12.0,'
        '"supports":[{"label":"A","type":"pin","x":0.0},'
        '{"label":"B","type":"roller","x":12.0}],'
        '"loads":[{"type":"point","x":5.0,"Fy":3.0}]}}'
    )

    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            return_value=fake_response,
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(EXTRACTED, "האורך הוא 12 מטר")

    assert errors == []
    assert updated is not None
    assert float(updated["beam"]["L"]) == 12.0
    # sanity: mock payload shape still usable
    assert updated_payload["beam"]["L"] == 12.0


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


def test_wants_inclined_to_vertical_hebrew():
    assert wants_inclined_to_vertical("שנה את העומסים האלכסוניים לאנכיים")
    assert wants_inclined_to_vertical("תעשה את המשופע לנקודתי אנכי")
    assert not wants_inclined_to_vertical("שנה את L ל-12")


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


def test_apply_nl_forces_inclined_to_vertical_even_if_gemini_keeps_inclined():
    inclined = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {
                    "type": "inclined",
                    "x": 5.0,
                    "magnitude_ton": 6.0,
                    "angle_deg": 45.0,
                    "incl_dir": "dl",
                }
            ],
        },
    }
    # Gemini "failed" to convert — still returns inclined
    fake_response = MagicMock()
    fake_response.text = (
        '{"exercise_type":"beam","beam":{"L":10.0,"loads":[{'
        '"type":"inclined","x":5.0,"magnitude_ton":6.0,'
        '"angle_deg":90.0,"incl_dir":"dr"}]}}'
    )

    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            return_value=fake_response,
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(
            inclined, "שנה את העומס האלכסוני לאנכי"
        )

    assert errors == []
    assert updated is not None
    ld = updated["beam"]["loads"][0]
    assert ld["type"] == "point"
    assert float(ld["Fy"]) == 6.0
    assert float(ld.get("Fx", 0.0)) == 0.0


def test_move_right_moment_to_right_end_keeps_left_moment():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 12.0,
            "loads": [
                {"type": "moment", "x": 2.0, "M": 10.0, "label_at": "A"},
                {"type": "moment", "x": 8.0, "M": 15.0, "label_at": "B"},
                {"type": "point", "x": 5.0, "Fy": 3.0},
            ],
        },
    }
    out = try_move_load_to_beam_end(
        extracted, "תעביר מומנט ימני לקצה ימני של הקורה"
    )
    assert out is not None
    moments = [ld for ld in out["beam"]["loads"] if ld["type"] == "moment"]
    assert float(moments[0]["x"]) == 2.0
    assert float(moments[1]["x"]) == 12.0
    assert moments[1].get("_user_x") is True
    assert "label_at" not in moments[1]
    assert float(out["beam"]["loads"][2]["x"]) == 5.0


def test_move_left_moment_to_right_end():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "moment", "x": 1.0, "M": 5.0},
                {"type": "moment", "x": 7.0, "M": 9.0},
            ],
        },
    }
    out = try_move_load_to_beam_end(
        extracted, "תעביר את המומנט השמאלי לקצה הימני"
    )
    assert out is not None
    assert float(out["beam"]["loads"][0]["x"]) == 10.0
    assert float(out["beam"]["loads"][1]["x"]) == 7.0


def test_add_axial_load_default_visible_fx():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [{"type": "point", "x": 3.0, "Fy": 2.0}],
        },
    }
    out = try_add_load(extracted, "תוסיף עומס צירי")
    assert out is not None
    ld = out["beam"]["loads"][-1]
    assert ld["type"] == "point"
    assert float(ld["Fy"]) == 0.0
    assert float(ld["Fx"]) == 5.0
    assert abs(float(ld["x"]) - 5.0) < 1e-9


def test_add_axial_load_with_mag_and_x():
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 12.0, "loads": []},
    }
    out = try_add_load(extracted, "הוסף עומס צירי 8 טון ב-x=3")
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert float(ld["Fx"]) == 8.0
    assert float(ld["x"]) == 3.0
    assert float(ld["Fy"]) == 0.0


def test_apply_nl_add_axial_skips_gemini():
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 10.0, "loads": [{"type": "moment", "x": 1.0, "M": 2.0}]},
    }
    with patch(
        "bot.draft_nl_edit.generate_content_with_retries",
        side_effect=AssertionError("Gemini should not be called"),
    ), patch(
        "bot.draft_nl_edit.finalize_beam_extraction",
        side_effect=lambda data, **_kw: data,
    ):
        updated, errors = apply_nl_draft_edit(extracted, "תוסיף עומס צירי")
    assert errors == []
    assert len(updated["beam"]["loads"]) == 2
    assert float(updated["beam"]["loads"][-1]["Fx"]) == 5.0


def test_apply_nl_move_moment_skips_gemini():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {"type": "moment", "x": 2.0, "M": 5.0},
                {"type": "moment", "x": 6.0, "M": 8.0},
            ],
        },
    }
    with patch(
        "bot.draft_nl_edit.generate_content_with_retries",
        side_effect=AssertionError("Gemini should not be called"),
    ), patch(
        "bot.draft_nl_edit.finalize_beam_extraction",
        side_effect=lambda data, **_kw: data,
    ):
        updated, errors = apply_nl_draft_edit(
            extracted, "תעביר מומנט ימני לקצה ימני של הקורה"
        )
    assert errors == []
    assert float(updated["beam"]["loads"][1]["x"]) == 10.0
    assert float(updated["beam"]["loads"][0]["x"]) == 2.0


def test_apply_nl_verticalize_fallback_when_gemini_fails():
    inclined = {
        "exercise_type": "beam",
        "beam": {
            "L": 8.0,
            "loads": [
                {
                    "type": "inclined",
                    "x": 3.0,
                    "magnitude_ton": 4.0,
                    "angle_deg": 30.0,
                    "incl_dir": "dr",
                }
            ],
        },
    }
    with (
        patch("bot.draft_nl_edit.gemini_runtime", return_value=(MagicMock(), "m")),
        patch(
            "bot.draft_nl_edit.generate_content_with_retries",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "bot.draft_nl_edit.finalize_beam_extraction",
            side_effect=lambda data, **_kw: data,
        ),
    ):
        updated, errors = apply_nl_draft_edit(
            inclined, "שנה אלכסוניים לאנכיים"
        )

    assert errors == []
    assert updated is not None
    assert updated["beam"]["loads"][0]["type"] == "point"
    assert float(updated["beam"]["loads"][0]["Fy"]) == 4.0


def _dist_extracted(x1: float = 0.0, x2: float = 4.0, L: float = 10.0) -> dict:
    return {
        "exercise_type": "beam",
        "beam": {
            "L": L,
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": L},
            ],
            "loads": [
                {
                    "type": "distributed",
                    "x1": x1,
                    "x2": x2,
                    "w": 3.0,
                    "shape": "rectangular",
                }
            ],
            "distributed_loads": [
                {"start_x": x1, "end_x": x2, "magnitude": 3.0, "shape": "rectangular"}
            ],
        },
    }


def test_try_resize_distributed_length_keeps_start():
    out = try_resize_distributed_load(
        _dist_extracted(0.0, 4.0),
        "שנה אורך של עומס מפורס ל-3 מטר",
    )
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert float(ld["x1"]) == 0.0
    assert float(ld["x2"]) == 3.0
    assert ld.get("_user_span") is True


def test_try_resize_distributed_from_to_x():
    out = try_resize_distributed_load(
        _dist_extracted(1.0, 5.0),
        "שנה את המפורס מ-x=2 עד x=6",
    )
    assert out is not None
    ld = out["beam"]["loads"][0]
    assert float(ld["x1"]) == 2.0
    assert float(ld["x2"]) == 6.0


def test_apply_nl_resize_distributed_without_gemini():
    with patch(
        "bot.draft_nl_edit.finalize_beam_extraction",
        side_effect=lambda data, **_kw: data,
    ):
        updated, errors = apply_nl_draft_edit(
            _dist_extracted(0.0, 5.0),
            "שנה אורך של עומס מפורס ל-2",
        )
    assert errors == []
    assert float(updated["beam"]["loads"][0]["x2"]) == 2.0


def test_extend_right_distributed_not_left():
    """«תאריך מפורס ימני» חייב לגעת רק בטווח הימני (max x2)."""
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {
                    "type": "distributed",
                    "x1": 0.0,
                    "x2": 3.0,
                    "w": 2.0,
                    "shape": "rectangular",
                },
                {
                    "type": "distributed",
                    "x1": 6.0,
                    "x2": 8.0,
                    "w": 2.0,
                    "shape": "rectangular",
                },
            ],
        },
    }
    out = try_resize_distributed_load(extracted, "תאריך את המפורס הימני")
    assert out is not None
    left, right = out["beam"]["loads"][0], out["beam"]["loads"][1]
    assert float(left["x1"]) == 0.0 and float(left["x2"]) == 3.0
    assert float(right["x1"]) == 6.0
    assert float(right["x2"]) == 9.0  # +1m default


def test_length_right_distributed_keeps_right_edge():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "loads": [
                {
                    "type": "distributed",
                    "x1": 0.0,
                    "x2": 3.0,
                    "w": 2.0,
                    "shape": "rectangular",
                },
                {
                    "type": "distributed",
                    "x1": 6.0,
                    "x2": 9.0,
                    "w": 2.0,
                    "shape": "rectangular",
                },
            ],
        },
    }
    out = try_resize_distributed_load(
        extracted, "שנה אורך של המפורס הימני ל-2 מטר"
    )
    assert out is not None
    left, right = out["beam"]["loads"][0], out["beam"]["loads"][1]
    assert float(left["x1"]) == 0.0 and float(left["x2"]) == 3.0
    assert float(right["x2"]) == 9.0
    assert float(right["x1"]) == 7.0


def test_extend_left_edge_of_right_distributed_by_2m():
    """«תאריך קצה שמאלי של מפורס ימני ב-2 מטר» — x1-=2, x2 נשאר; לא כופים אורך=2."""
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 12.0,
            "loads": [
                {
                    "type": "distributed",
                    "x1": 0.0,
                    "x2": 3.0,
                    "w": 2.0,
                    "shape": "rectangular",
                },
                {
                    "type": "distributed",
                    "x1": 8.0,
                    "x2": 10.0,
                    "w": 2.0,
                    "shape": "rectangular",
                },
            ],
        },
    }
    out = try_resize_distributed_load(
        extracted,
        "תאריך את הקצה השמאלי של המפורס הימני ב-2 מטרים",
    )
    assert out is not None
    left, right = out["beam"]["loads"][0], out["beam"]["loads"][1]
    assert float(left["x1"]) == 0.0 and float(left["x2"]) == 3.0
    assert float(right["x1"]) == 6.0
    assert float(right["x2"]) == 10.0
