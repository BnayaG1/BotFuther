# -*- coding: utf-8 -*-
"""לא להפוך עומס אנכי לאלכסוני בפוסט־עיבוד."""
from __future__ import annotations

from bot.vision import (
    _demote_near_vertical_inclined_loads,
    _fix_paired_cd_inclined_loads,
    _promote_diagonal_point_loads,
)


def test_promote_keeps_near_vertical_point():
    loads = _promote_diagonal_point_loads(
        [{"type": "point", "x": 1.0, "Fy": 10.0, "Fx": 0.5}]
    )
    assert loads[0]["type"] == "point"


def test_promote_true_diagonal_point_to_inclined():
    loads = _promote_diagonal_point_loads(
        [{"type": "point", "x": 1.0, "Fy": 5.0, "Fx": 5.0}]
    )
    assert loads[0]["type"] == "inclined"


def test_demote_near_vertical_inclined_to_point():
    loads = _demote_near_vertical_inclined_loads(
        [
            {
                "type": "inclined",
                "x": 4.0,
                "magnitude_ton": 10.0,
                "angle_deg": 85.0,
                "incl_dir": "dr",
                "Fx": 0.8,
                "Fy": 10.0,
                "label_at": "D",
            }
        ]
    )
    assert loads[0]["type"] == "point"
    assert float(loads[0]["Fy"]) == 10.0
    assert float(loads[0]["Fx"]) == 0.0


def test_demote_keeps_true_inclined():
    loads = _demote_near_vertical_inclined_loads(
        [
            {
                "type": "inclined",
                "x": 4.0,
                "magnitude_ton": 10.0,
                "angle_deg": 30.0,
                "incl_dir": "dr",
                "Fx": 8.66,
                "Fy": 5.0,
            }
        ]
    )
    assert loads[0]["type"] == "inclined"


def test_fix_paired_cd_does_not_convert_vertical_d_to_inclined():
    beam = {
        "L": 10.0,
        "labeled_points": [
            {"label": "C", "x": 1.0},
            {"label": "D", "x": 2.0},
        ],
    }
    loads = [
        {
            "type": "inclined",
            "x": 1.0,
            "magnitude_ton": 5.0,
            "angle_deg": 30.0,
            "incl_dir": "dr",
            "Fx": 4.33,
            "Fy": 2.5,
            "label_at": "C",
        },
        {"type": "point", "x": 2.0, "Fy": 5.0, "Fx": 0.0, "label_at": "D"},
    ]
    out = _fix_paired_cd_inclined_loads(beam, [dict(ld) for ld in loads])
    assert out[1]["type"] == "point"
    assert float(out[1]["Fy"]) == 5.0
