# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import pytest

from core.statics_calculator import (
    cantilever_bending_moment,
    cantilever_shear_force,
    solve_cantilever_beam,
)
from bot.vision import resolve_beam_support_geometry
import notebook as nb
from personal_assistant.reactions.cantilever import sigma_ma as cant_sigma_ma
from personal_assistant.reactions.cantilever import sigma_m_tip as cant_sigma_m_tip


def test_resolve_beam_support_geometry_left_vs_right():
    beam_left = {
        "L": 10.0,
        "support_mode": "cantilever",
        "supports": [{"label": "A", "type": "fixed", "x": 0.0}],
    }
    mode_l, wall_l, tip_l = resolve_beam_support_geometry(beam_left)
    assert mode_l == "cantilever"
    assert wall_l == 0.0
    assert tip_l == 10.0

    beam_right = {
        "L": 10.0,
        "support_mode": "cantilever",
        "supports": [{"label": "A", "type": "fixed", "x": 10.0}],
    }
    mode_r, wall_r, tip_r = resolve_beam_support_geometry(beam_right)
    assert mode_r == "cantilever"
    assert wall_r == 10.0
    assert tip_r == 0.0


def test_solve_cantilever_right_wall_point_load():
    L = 8.0
    loads = [{"type": "point", "x": 2.0, "Fy": 10.0}]
    result = solve_cantilever_beam(loads, L, wall_pos=8.0)

    assert result["wall_pos"] == 8.0
    assert result["R_Ay"] == -10.0
    assert result["M_A"] == 60.0  # 10 * (8 - 2)

    # Before load (x=0, x=1): shear=0, moment=0
    assert abs(cantilever_shear_force(0.0, loads, result["R_Ay"], wall_pos=8.0)) < 1e-9
    assert abs(cantilever_shear_force(1.0, loads, result["R_Ay"], wall_pos=8.0)) < 1e-9
    assert abs(cantilever_bending_moment(0.0, loads, result["R_Ay"], result["M_A"], wall_pos=8.0)) < 1e-9
    assert abs(cantilever_bending_moment(1.0, loads, result["R_Ay"], result["M_A"], wall_pos=8.0)) < 1e-9

    # At x=4 (between load and wall): shear=10, moment=10*(4-2)=20
    assert abs(cantilever_shear_force(4.0, loads, result["R_Ay"], wall_pos=8.0) - 10.0) < 1e-9
    assert abs(cantilever_bending_moment(4.0, loads, result["R_Ay"], result["M_A"], wall_pos=8.0) - 20.0) < 1e-9

    # At x=8 (wall): moment=60
    assert abs(cantilever_bending_moment(8.0, loads, result["R_Ay"], result["M_A"], wall_pos=8.0) - 60.0) < 1e-9


def test_solve_cantilever_right_wall_distributed_load():
    L = 6.0
    loads = [{"type": "distributed", "x1": 0.0, "x2": 3.0, "w": 2.0}]
    result = solve_cantilever_beam(loads, L, wall_pos=6.0)

    assert result["wall_pos"] == 6.0
    assert result["R_Ay"] == -6.0
    assert abs(result["M_A"] - 27.0) < 1e-9

    assert abs(cantilever_bending_moment(0.0, loads, result["R_Ay"], result["M_A"], wall_pos=6.0)) < 1e-9
    assert abs(cantilever_bending_moment(6.0, loads, result["R_Ay"], result["M_A"], wall_pos=6.0) - 27.0) < 1e-9


def test_cantilever_notebook_html_and_pdf_right_wall():
    L = 8.0
    loads = [
        {"type": "point", "x": 2.0, "Fy": 5.0},
        {"type": "distributed", "x1": 0.0, "x2": 4.0, "w": 3.0},
    ]
    result = solve_cantilever_beam(loads, L, wall_pos=8.0)
    html, png_bytes, pdf_bytes = nb.build_cantilever_page_html(
        loads, L, result, wide_layout=True
    )
    assert html is not None
    assert len(png_bytes) > 0
    assert len(pdf_bytes) > 0


def test_personal_assistant_right_wall_sigma_ma():
    L = 8.0
    loads = [{"type": "point", "x": 2.0, "Fy": 4.0}]
    extracted = {
        "beam": {
            "L": L,
            "support_mode": "cantilever",
            "supports": [{"label": "A", "type": "fixed", "x": 8.0}],
            "loads": loads,
        }
    }
    ma_val = cant_sigma_ma.compute_Ma_from_extracted(extracted)
    assert abs(abs(ma_val) - 24.0) < 0.01

    text = cant_sigma_ma.build_ma_assembled_equation_hebrew(extracted)
    assert "Ma" in text
    assert "6" in text or "6.0" in text
