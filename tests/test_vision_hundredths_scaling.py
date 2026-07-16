# -*- coding: utf-8 -*-
"""בדיקות להמרת אורכים במאות/ס"מ למטרים (÷100) — למשל אורך קורה 700 → 7 מ'."""
from __future__ import annotations

from bot.vision import (
    _geometry_uses_hundredth_meters,
    _scale_beam_geometry_from_hundredths,
    normalize_beam_model,
)


def test_beam_length_700_becomes_7_meters():
    """התרחיש שהמשתמש דיווח עליו: אורך קורה 700 → 7 מ', וכל האורכים האחרים איתו."""
    beam = {
        "support_mode": "simply_supported",
        "L": 700,
        "supports": [
            {"label": "A", "type": "pin", "x": 0},
            {"label": "B", "type": "roller", "x": 700},
        ],
        "loads": [{"type": "point", "x": 300, "Fy": 5}],
        "key_points_m": [0, 300, 700],
    }
    out = normalize_beam_model(beam)
    assert out["L"] == 7.0
    assert out["supports"][0]["x"] == 0.0
    assert out["supports"][1]["x"] == 7.0
    assert out["loads"][0]["x"] == 3.0
    assert out["key_points_m"] == [0.0, 3.0, 7.0]
    # מגניטודת כוח (Fy) היא לא אורך — לא מתחלקת ב-100.
    assert out["loads"][0]["Fy"] == 5.0


def test_scaling_derives_length_from_segments_when_L_missing_directly():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 420},
            {"label": "B", "type": "roller", "x": 1620},
        ],
        "segments": [
            {"from_x": 0, "to_x": 420, "length_m": 420},
            {"from_x": 420, "to_x": 1420, "length_m": 1000},
            {"from_x": 1420, "to_x": 1620, "length_m": 200},
        ],
        "labeled_points": [
            {"label": "C", "x": 0},
            {"label": "A", "x": 420},
            {"label": "F", "x": 1420},
            {"label": "B", "x": 1620},
        ],
        "loads": [],
    }
    out = normalize_beam_model(beam)
    assert out["L"] == 16.2
    assert out["supports"][0]["x"] == 4.2
    assert out["supports"][1]["x"] == 16.2
    assert [p["x"] for p in out["labeled_points"]] == [0.0, 4.2, 14.200000000000001, 16.2]


def test_distributed_loads_and_internal_hinges_are_scaled():
    beam = {
        "support_mode": "simply_supported",
        "L": 1620,
        "supports": [
            {"label": "A", "type": "pin", "x": 0},
            {"label": "B", "type": "roller", "x": 1620},
        ],
        "distributed_loads": [{"start_x": 400, "end_x": 1200, "magnitude": 2}],
        "internal_hinges": [{"x": 800, "label": None}],
        "loads": [],
    }
    out = normalize_beam_model(beam)
    assert out["internal_hinges"][0]["x"] == 8.0
    dist_loads = [ld for ld in out["loads"] if ld.get("type") == "distributed"]
    assert dist_loads
    assert dist_loads[0]["x1"] == 4.0
    assert dist_loads[0]["x2"] == 12.0
    # מגניטודת עומס מפוזר (ton/m) היא לא אורך — לא מתחלקת ב-100.
    assert dist_loads[0]["w"] == 2.0


def test_small_realistic_beam_length_is_not_scaled():
    """קורה קטנה וריאלית (L=8) לא נחשבת «במאות» — לא נוגעים בה."""
    beam = {
        "support_mode": "simply_supported",
        "L": 8,
        "supports": [
            {"label": "A", "type": "pin", "x": 0},
            {"label": "B", "type": "roller", "x": 8},
        ],
        "loads": [],
    }
    out = normalize_beam_model(beam)
    assert out["L"] == 8.0
    assert out["supports"][1]["x"] == 8.0


def test_scaling_is_idempotent_and_does_not_double_divide():
    beam = {
        "support_mode": "simply_supported",
        "L": 700,
        "supports": [
            {"label": "A", "type": "pin", "x": 0},
            {"label": "B", "type": "roller", "x": 700},
        ],
        "loads": [],
    }
    _scale_beam_geometry_from_hundredths(beam)
    assert beam["L"] == 7.0
    # קריאה שנייה לא צריכה לחלק שוב (הדגל _scaled_from_hundredths חוסם).
    changed_again = _scale_beam_geometry_from_hundredths(beam)
    assert changed_again is False
    assert beam["L"] == 7.0


def test_user_locked_length_is_never_auto_scaled():
    beam = {
        "support_mode": "simply_supported",
        "L": 700,
        "_user_L": True,
        "supports": [
            {"label": "A", "type": "pin", "x": 0},
            {"label": "B", "type": "roller", "x": 700},
        ],
        "loads": [],
    }
    changed = _scale_beam_geometry_from_hundredths(beam)
    assert changed is False
    assert beam["L"] == 700


def test_user_edited_support_position_is_not_rescaled():
    """סמך שהמשתמש ערך ידנית (_user_x) לא מוזז ע"י ההמרה האוטומטית ל-÷100."""
    beam = {
        "support_mode": "simply_supported",
        "L": 700,
        "supports": [
            {"label": "A", "type": "pin", "x": 0},
            {"label": "B", "type": "roller", "x": 700, "_user_x": True},
        ],
        "loads": [],
    }
    _scale_beam_geometry_from_hundredths(beam)
    assert beam["L"] == 7.0
    assert beam["supports"][1]["x"] == 700


def test_geometry_uses_hundredth_meters_detects_and_rejects_correctly():
    assert _geometry_uses_hundredth_meters({"L": 700}) is True
    assert _geometry_uses_hundredth_meters({"L": 8}) is False
    assert _geometry_uses_hundredth_meters({"L": 0}) is False
