# -*- coding: utf-8 -*-
"""פיצול עומס מפורס סביב נקודת מומנט — עזרה משותפת + מדריך."""
from __future__ import annotations

from core.distributed_moments import (
    UDL_SPLIT_ABOUT_PIVOT_HE,
    distributed_crosses_pivot,
    distributed_moment_segments_about,
)
from core.statics_calculator import compute_reactions
from personal_assistant.reactions.simply_supported import sigma_ma as ss_sigma_ma
from personal_assistant.reactions.simply_supported import sigma_mb as ss_sigma_mb


def _overhang_udl_extracted(*, L=10.0, xa=2.0, xb=8.0, w=3.0):
    """מפורס לכל האורך — חוצה את A ואת B."""
    return {
        "exercise_type": "beam",
        "beam": {
            "L": L,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": xa},
                {"label": "B", "type": "roller", "x": xb},
            ],
            "loads": [
                {
                    "type": "distributed",
                    "x1": 0.0,
                    "x2": L,
                    "w": w,
                    "shape": "rectangular",
                }
            ],
        },
    }


def test_helper_splits_when_crossing_pivot():
    segs = distributed_moment_segments_about(4.0, 0.0, 10.0, 3.0)
    assert len(segs) == 2
    assert abs(segs[0].x2 - 3.0) < 1e-9
    assert abs(segs[1].x1 - 3.0) < 1e-9
    assert abs(segs[0].force - 12.0) < 1e-9  # 4*3
    assert abs(segs[1].force - 28.0) < 1e-9  # 4*7
    assert distributed_crosses_pivot(0.0, 10.0, 3.0)
    assert not distributed_crosses_pivot(0.0, 2.0, 3.0)


def test_helper_no_split_when_entirely_on_one_side():
    segs = distributed_moment_segments_about(2.0, 4.0, 7.0, 3.0)
    assert len(segs) == 1
    assert abs(segs[0].force - 6.0) < 1e-9
    assert abs(segs[0].centroid - 5.5) < 1e-9


def test_guide_ma_splits_crossing_udl_with_intro():
    extracted = _overhang_udl_extracted()
    terms, ra_pos, _rb = ss_sigma_ma._collect_ma_vertical_terms(extracted)
    dist_terms = [t for t in terms if t.kind == "distributed"]
    assert len(dist_terms) == 2
    assert any(t.split_intro for t in dist_terms)
    assert sum(1 for t in dist_terms if t.split_intro) == 1

    text = ss_sigma_ma.build_by_ma_equation_message_hebrew(extracted)
    assert UDL_SPLIT_ABOUT_PIVOT_HE in text
    # שני שקולים נפרדים בהסבר
    assert text.count("עומס מפורס שמצאנו שהכח השקול שלו הוא") == 2


def test_guide_mb_splits_crossing_udl_with_intro():
    extracted = _overhang_udl_extracted()
    terms, _ra, rb_pos = ss_sigma_mb._collect_mb_vertical_terms(extracted)
    dist_terms = [t for t in terms if t.kind == "distributed"]
    assert len(dist_terms) == 2
    text = ss_sigma_mb.build_ay_mb_equation_message_hebrew(extracted)
    assert UDL_SPLIT_ABOUT_PIVOT_HE in text


def test_guide_no_split_when_udl_does_not_cross_a():
    extracted = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {
                    "type": "distributed",
                    "x1": 2.0,
                    "x2": 5.0,
                    "w": 4.0,
                    "shape": "rectangular",
                }
            ],
        }
    }
    terms, _ra, _rb = ss_sigma_ma._collect_ma_vertical_terms(extracted)
    dist_terms = [t for t in terms if t.kind == "distributed"]
    assert len(dist_terms) == 1
    assert not dist_terms[0].split_intro
    text = ss_sigma_ma.build_by_ma_equation_message_hebrew(extracted)
    assert UDL_SPLIT_ABOUT_PIVOT_HE not in text


def test_reactions_unchanged_with_split_display():
    """פיצול לתצוגה שקול מספרית לסולבר (וריניון)."""
    import re

    extracted = _overhang_udl_extracted(L=12.0, xa=3.0, xb=9.0, w=2.0)
    beam = extracted["beam"]
    _ra_x, _ra_y, _rb_x, rb_y = compute_reactions(
        beam["loads"], L=beam["L"], ra_pos=3.0, rb_pos=9.0
    )
    text = ss_sigma_ma.build_by_ma_assembled_equation_hebrew(extracted)
    m = re.search(r"By = (-?[0-9.]+)", text)
    assert m is not None
    by_guide = float(m.group(1))
    # אותה מוסכמה כמו test_personal_assistant_reactions_physics
    assert abs(by_guide - (-rb_y)) < 0.02


def test_notebook_distributed_terms_use_shared_split():
    from notebook.facade import _distributed_moment_terms_about, _udl_split_note_html_for_pivot

    terms = _distributed_moment_terms_about(3.0, 0.0, 10.0, 2.0)
    assert len(terms) == 2
    note = _udl_split_note_html_for_pivot(
        [{"type": "distributed", "x1": 0.0, "x2": 10.0, "w": 3.0}],
        2.0,
    )
    assert note
    assert "נחלק אותו ל2" in note
    empty = _udl_split_note_html_for_pivot(
        [{"type": "distributed", "x1": 3.0, "x2": 5.0, "w": 3.0}],
        2.0,
    )
    assert empty == ""
