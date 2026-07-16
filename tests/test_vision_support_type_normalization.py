# -*- coding: utf-8 -*-
"""בדיקות לנרמול סוגי סמכים בקורה על 2 סמכים — «fixed» לא תקף, בלי הנחת ימין/שמאל."""
from __future__ import annotations

from bot.vision import _apply_support_hatch_evidence, _normalize_support_types


def test_left_support_misread_as_fixed_becomes_pin_when_other_is_roller():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "fixed", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
    }
    _normalize_support_types(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_right_support_misread_as_fixed_becomes_roller_when_other_is_pin():
    """המקרה שהמשתמש דיווח עליו: A=נעץ (נכון), B טעה ל-fixed במקום roller."""
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "fixed", "x": 10.0},
        ],
    }
    _normalize_support_types(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_correct_pin_and_roller_are_left_untouched():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
    }
    _normalize_support_types(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_cantilever_mode_is_never_touched():
    beam = {
        "support_mode": "cantilever",
        "supports": [{"label": "A", "type": "fixed", "x": 0.0}],
    }
    _normalize_support_types(beam)
    assert beam["supports"][0]["type"] == "fixed"


def test_both_supports_fixed_becomes_pin_and_roller_by_labels():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "fixed", "x": 0.0},
            {"label": "B", "type": "fixed", "x": 10.0},
        ],
    }
    _normalize_support_types(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_both_supports_pin_becomes_pin_and_roller():
    """רגרסיה: שני «קבוע» בטיוטה — חייב אחד קבוע ואחד נייד."""
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "pin", "x": 10.0},
        ],
    }
    _normalize_support_types(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_both_supports_roller_becomes_pin_and_roller_by_position():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "C", "type": "roller", "x": 1.0},
            {"label": "D", "type": "roller", "x": 9.0},
        ],
    }
    _normalize_support_types(beam)
    by_x = sorted(beam["supports"], key=lambda s: float(s["x"]))
    assert by_x[0]["type"] == "pin"
    assert by_x[1]["type"] == "roller"


def test_more_than_two_supports_is_left_untouched():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "C", "type": "fixed", "x": 5.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
    }
    _normalize_support_types(beam)
    assert beam["supports"][1]["type"] == "fixed"


def test_hatch_evidence_corrects_roller_mislabeled_as_pin_on_left():
    """הסמך הנייד (0 קווי hatch) נשאר מסומן «pin» בטעות — למרות שהוא בצד שמאל."""
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0, "hatch_count": 0},
            {"label": "B", "type": "roller", "x": 10.0, "hatch_count": 3},
        ],
    }
    _apply_support_hatch_evidence(beam)
    assert beam["supports"][0]["type"] == "roller"
    assert beam["supports"][1]["type"] == "pin"


def test_hatch_evidence_corrects_pin_mislabeled_as_roller_on_right():
    """הסמך הקבוע (3 קווי hatch) נשאר מסומן «roller» בטעות — למרות שהוא בצד ימין."""
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "roller", "x": 0.0, "hatch_count": 4},
            {"label": "B", "type": "pin", "x": 10.0, "hatch_count": 0},
        ],
    }
    _apply_support_hatch_evidence(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_hatch_evidence_agrees_with_type_leaves_untouched():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0, "hatch_count": 2},
            {"label": "B", "type": "roller", "x": 10.0, "hatch_count": 0},
        ],
    }
    _apply_support_hatch_evidence(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_hatch_evidence_missing_field_leaves_type_untouched():
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
    }
    _apply_support_hatch_evidence(beam)
    assert beam["supports"][0]["type"] == "pin"
    assert beam["supports"][1]["type"] == "roller"


def test_hatch_evidence_corrects_fixed_mislabel_using_count_not_other_support():
    """«fixed» שגוי מתוקן ישירות מ-hatch_count, בלי להסתמך על הסמך השני."""
    beam = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "fixed", "x": 0.0, "hatch_count": 0},
            {"label": "B", "type": "roller", "x": 10.0, "hatch_count": 0},
        ],
    }
    _apply_support_hatch_evidence(beam)
    assert beam["supports"][0]["type"] == "roller"


def test_hatch_evidence_ignored_for_cantilever():
    beam = {
        "support_mode": "cantilever",
        "supports": [{"label": "A", "type": "fixed", "x": 0.0, "hatch_count": 0}],
    }
    _apply_support_hatch_evidence(beam)
    assert beam["supports"][0]["type"] == "fixed"


def test_hatch_evidence_then_normalize_full_pipeline_fixes_both_left_and_right_roller_cases():
    """רצף מלא כמו ב-normalize_beam_model: עדות hatch לפני נרמול fixed — ללא הנחת שמאל/ימין."""
    beam_roller_left = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "fixed", "x": 0.0, "hatch_count": 0},
            {"label": "B", "type": "pin", "x": 10.0, "hatch_count": 3},
        ],
    }
    _apply_support_hatch_evidence(beam_roller_left)
    _normalize_support_types(beam_roller_left)
    assert beam_roller_left["supports"][0]["type"] == "roller"
    assert beam_roller_left["supports"][1]["type"] == "pin"

    beam_roller_right = {
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0, "hatch_count": 3},
            {"label": "B", "type": "fixed", "x": 10.0, "hatch_count": 0},
        ],
    }
    _apply_support_hatch_evidence(beam_roller_right)
    _normalize_support_types(beam_roller_right)
    assert beam_roller_right["supports"][0]["type"] == "pin"
    assert beam_roller_right["supports"][1]["type"] == "roller"
