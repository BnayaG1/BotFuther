# -*- coding: utf-8 -*-
"""בדיקות התאמה מספרית בין נוסחי הריאקציות (העוזר האישי) לפותר האמיתי.

לכל אחת מ-4 המשוואות (Ay, By, Ma, Ay-בריתום) יש כאן בדיקה שמשווה את התוצאה
שהעוזר האישי "מלמד" את המשתמש לתוצאה של core/statics_calculator.py (שהוא
מקור האמת המתמטי), כולל מקרים עם עומס מומנט טהור.
"""

from __future__ import annotations

import math
import re

import pytest

from core.statics_calculator import compute_reactions, solve_cantilever_beam
from personal_assistant.reactions.cantilever import sigma_ma as cant_sigma_ma
from personal_assistant.reactions.cantilever import sigma_m_tip as cant_sigma_m_tip
from personal_assistant.reactions.simply_supported import sigma_ma as ss_sigma_ma
from personal_assistant.reactions.simply_supported import sigma_mb as ss_sigma_mb


def _simply_extracted(loads: list[dict]) -> dict:
    return {
        "beam": {
            "L": 9.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 2.0},
                {"label": "B", "type": "roller", "x": 9.0},
            ],
            "loads": loads,
        }
    }


def _cantilever_extracted(loads: list[dict]) -> dict:
    return {
        "beam": {
            "L": 8.0,
            "support_mode": "cantilever",
            "supports": [{"label": "A", "type": "fixed", "x": 0.0}],
            "loads": loads,
        }
    }


_SIMPLY_BASE_PED = [
    {"type": "distributed", "x1": 0.0, "x2": 5.0, "w": 3.0},
    {"type": "point", "x": 6.0, "Fy": 2.0},
    {"type": "inclined", "x": 4.0, "magnitude_ton": 5.0, "angle_deg": 30.0, "incl_dir": "dr"},
]
_INCLINED_FX = 5.0 * math.cos(math.radians(30.0))
_INCLINED_FY = 5.0 * math.sin(math.radians(30.0))
_SIMPLY_BASE_GT = [
    {"type": "distributed", "x1": 0.0, "x2": 5.0, "w": 3.0},
    {"type": "point", "x": 6.0, "Fy": 2.0},
    {"type": "inclined", "x": 4.0, "Fx": _INCLINED_FX, "Fy": _INCLINED_FY},
]

_MOMENT_CASES = [
    ("no_moment", [], []),
    ("plus_moment", [{"type": "moment", "x": 3.0, "M": 4.0}], [{"type": "moment", "x": 3.0, "M": 4.0}]),
    ("minus_moment", [{"type": "moment", "x": 3.0, "M": -4.0}], [{"type": "moment", "x": 3.0, "M": -4.0}]),
    ("moment_other_x", [{"type": "moment", "x": 8.0, "M": 7.0}], [{"type": "moment", "x": 8.0, "M": 7.0}]),
]


def _extract_signed_number(text: str, label: str) -> float:
    m = re.search(rf"{label} = (-?[0-9.]+)", text)
    assert m is not None, f"couldn't find {label} in:\n{text}"
    return float(m.group(1))


@pytest.mark.parametrize("label,extra_ped,extra_gt", _MOMENT_CASES)
def test_ay_matches_ground_truth(label, extra_ped, extra_gt):
    text = ss_sigma_mb.build_ay_mb_assembled_equation_hebrew(
        _simply_extracted(_SIMPLY_BASE_PED + extra_ped)
    )
    ay_ped = _extract_signed_number(text, "Ay")
    ra_x, ra_y, rb_x, rb_y = compute_reactions(
        _SIMPLY_BASE_GT + extra_gt, L=9.0, ra_pos=2.0, rb_pos=9.0
    )
    assert abs(ay_ped - (-ra_y)) < 0.02


@pytest.mark.parametrize("label,extra_ped,extra_gt", _MOMENT_CASES)
def test_by_matches_ground_truth(label, extra_ped, extra_gt):
    text = ss_sigma_ma.build_by_ma_assembled_equation_hebrew(
        _simply_extracted(_SIMPLY_BASE_PED + extra_ped)
    )
    by_ped = _extract_signed_number(text, "By")
    ra_x, ra_y, rb_x, rb_y = compute_reactions(
        _SIMPLY_BASE_GT + extra_gt, L=9.0, ra_pos=2.0, rb_pos=9.0
    )
    assert abs(by_ped - (-rb_y)) < 0.02


_CANTILEVER_MAG = 4.0
_CANTILEVER_ANGLE = 45.0
_CANT_FY = _CANTILEVER_MAG * math.sin(math.radians(_CANTILEVER_ANGLE))
_CANT_FX = -_CANTILEVER_MAG * math.cos(math.radians(_CANTILEVER_ANGLE))

_CANTILEVER_CASES = [
    (
        "point_only",
        [{"type": "point", "x": 5.0, "Fy": 6.0}],
        [{"type": "point", "x": 5.0, "Fy": 6.0, "Fx": 0.0}],
    ),
    (
        "distributed_only",
        [{"type": "distributed", "x1": 1.0, "x2": 4.0, "w": 2.0}],
        [{"type": "distributed", "x1": 1.0, "x2": 4.0, "w": 2.0}],
    ),
    (
        "inclined",
        [{"type": "inclined", "x": 3.0, "magnitude_ton": _CANTILEVER_MAG, "angle_deg": _CANTILEVER_ANGLE, "incl_dir": "dl"}],
        [{"type": "inclined", "x": 3.0, "Fx": _CANT_FX, "Fy": _CANT_FY}],
    ),
    (
        "plus_moment",
        [{"type": "moment", "x": 2.0, "M": 5.0}],
        [{"type": "moment", "x": 2.0, "M": 5.0}],
    ),
    (
        "minus_moment",
        [{"type": "moment", "x": 2.0, "M": -5.0}],
        [{"type": "moment", "x": 2.0, "M": -5.0}],
    ),
    (
        "mixed",
        [
            {"type": "point", "x": 5.0, "Fy": 6.0},
            {"type": "moment", "x": 2.0, "M": 5.0},
            {"type": "distributed", "x1": 1.0, "x2": 4.0, "w": 2.0},
        ],
        [
            {"type": "point", "x": 5.0, "Fy": 6.0, "Fx": 0.0},
            {"type": "moment", "x": 2.0, "M": 5.0},
            {"type": "distributed", "x1": 1.0, "x2": 4.0, "w": 2.0},
        ],
    ),
]


@pytest.mark.parametrize("label,loads_ped,loads_gt", _CANTILEVER_CASES)
def test_ma_matches_ground_truth(label, loads_ped, loads_gt):
    text = cant_sigma_ma.build_ma_assembled_equation_hebrew(
        _cantilever_extracted(loads_ped)
    )
    ma_ped = _extract_signed_number(text, "Ma")
    gt = solve_cantilever_beam(loads_gt, L=8.0)
    assert abs(ma_ped - gt["M_A"]) < 0.05


@pytest.mark.parametrize("label,loads_ped,loads_gt", _CANTILEVER_CASES)
def test_ay_tip_matches_ground_truth(label, loads_ped, loads_gt):
    text = cant_sigma_m_tip.build_ay_tip_assembled_equation_hebrew(
        _cantilever_extracted(loads_ped)
    )
    ay_ped = _extract_signed_number(text, "Ay")
    gt = solve_cantilever_beam(loads_gt, L=8.0)
    assert abs(ay_ped - (-gt["R_Ay"])) < 0.05
