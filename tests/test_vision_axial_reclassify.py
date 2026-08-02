# -*- coding: utf-8 -*-
"""עומס צירי שנקלט כ-Fy / magnitude — חייב להפוך ל-Fx (גם באמצע הקורה)."""
from __future__ import annotations

from bot.vision import (
    _coerce_solver_load_schema,
    _merge_extracted_axial_loads,
    _merge_point_loads_at_same_x,
    _normalize_load_magnitudes_ton,
    _reclassify_axial_mislabeled_as_fy,
    _stations_needing_interior_axial,
    normalize_beam_model,
)


def test_reclassify_direction_left_fy_to_fx_midspan():
    ld = _reclassify_axial_mislabeled_as_fy(
        {"type": "point", "x": 4.0, "Fy": 8.0, "Fx": 0.0, "direction": "left"}
    )
    assert abs(float(ld["Fy"])) < 1e-9
    assert float(ld["Fx"]) == -8.0


def test_coerce_axial_magnitude_ton_not_to_fy():
    loads = _coerce_solver_load_schema(
        [
            {
                "type": "point",
                "x": 3.0,
                "magnitude_ton": 5.0,
                "direction": "right",
                "label_at": "D",
            }
        ]
    )
    assert abs(float(loads[0].get("Fy", 0) or 0)) < 1e-9
    assert float(loads[0]["Fx"]) == 5.0


def test_normalize_keeps_midspan_axial():
    beam = normalize_beam_model(
        {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {"type": "point", "x": 2.0, "Fy": 12.0, "Fx": 0.0, "direction": "down"},
                {
                    "type": "point",
                    "x": 5.0,
                    "Fy": 6.0,
                    "Fx": 0.0,
                    "direction": "left",
                    "label_at": "C",
                },
            ],
        },
        merge_nearby_point_loads=True,
    )
    loads = beam["loads"]
    axial = [
        ld
        for ld in loads
        if abs(float(ld.get("Fx", 0) or 0)) >= 1e-9
        and abs(float(ld.get("Fy", 0) or 0)) < 1e-9
    ]
    assert len(axial) == 1
    assert abs(float(axial[0]["x"]) - 5.0) < 0.3
    assert float(axial[0]["Fx"]) == -6.0


def test_normalize_load_magnitudes_reclassifies_axial_kind():
    loads = _normalize_load_magnitudes_ton(
        [
            {
                "type": "point",
                "x": 2.0,
                "Fy": 4.0,
                "Fx": 0.0,
                "load_kind": "axial",
                "arrow_direction": "right",
            }
        ]
    )
    assert abs(float(loads[0]["Fy"])) < 1e-9
    assert float(loads[0]["Fx"]) == 4.0


def test_stations_needing_interior_axial_cd_pattern():
    """כמו בתרגיל: אנכיים ב-C/D, צירי רק ב-A — חסרים ציריים פנימיים."""
    beam = {
        "L": 6.0,
        "loads": [
            {"type": "point", "x": 0.0, "Fy": 0.0, "Fx": -5.0},
            {"type": "point", "x": 2.0, "Fy": 20.0, "Fx": 0.0},
            {"type": "point", "x": 4.0, "Fy": 20.0, "Fx": 0.0},
            {"type": "moment", "x": 0.0, "M": 24.0},
            {"type": "moment", "x": 6.0, "M": -24.0},
        ],
    }
    missing = _stations_needing_interior_axial(beam)
    assert sorted(missing) == [2.0, 4.0]


def test_merge_keeps_vertical_and_axial_separate():
    loads = _merge_point_loads_at_same_x(
        [
            {"type": "point", "x": 2.0, "Fy": 20.0, "Fx": 0.0},
            {"type": "point", "x": 2.0, "Fy": 0.0, "Fx": 15.0},
        ]
    )
    assert len(loads) == 2
    assert any(_abs_fx(ld) == 15.0 and _abs_fy(ld) < 1e-9 for ld in loads)
    assert any(_abs_fy(ld) == 20.0 and _abs_fx(ld) < 1e-9 for ld in loads)


def test_merge_extracted_axial_loads_adds_cd():
    beam = {
        "L": 6.0,
        "loads": [
            {"type": "point", "x": 0.0, "Fy": 0.0, "Fx": -5.0},
            {"type": "point", "x": 2.0, "Fy": 20.0, "Fx": 0.0},
            {"type": "point", "x": 4.0, "Fy": 19.4, "Fx": 0.0},
        ],
    }
    added = _merge_extracted_axial_loads(
        beam,
        [
            {"x": 2.0, "Fx": 15.0, "direction": "right", "label_at": "C"},
            {"x": 4.0, "Fx": 10.0, "direction": "right", "label_at": "D"},
        ],
    )
    assert added == 2
    assert _stations_needing_interior_axial(beam) == []


def _abs_fx(ld: dict) -> float:
    return abs(float(ld.get("Fx", 0) or 0))


def _abs_fy(ld: dict) -> float:
    return abs(float(ld.get("Fy", 0) or 0))
