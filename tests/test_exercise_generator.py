# -*- coding: utf-8 -*-
"""בדיקות מחולל תרגילי קורות."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from exercise_generator.pipeline import generate_batch, generate_exercise
from exercise_generator.templates.registry import build_family, list_families
from exercise_generator.validate import require_valid, validate_exercise


ALL_FAMILIES = list_families()


@pytest.mark.parametrize("family_id", ALL_FAMILIES)
def test_each_family_builds_and_validates(family_id: str):
    ex = build_family(family_id, seed=42)
    assert ex.family == family_id
    assert ex.seed == 42
    require_valid(ex)
    extracted = ex.to_extracted()
    assert extracted["exercise_type"] == "beam"
    assert extracted["beam"]["L"] == ex.L
    assert extracted["meta"]["family"] == family_id
    assert "supports" in extracted["beam"]
    assert "loads" in extracted["beam"]


def test_distributed_dual_format():
    ex = build_family("overhang_stepped_udl", seed=1)
    extracted = ex.to_extracted()
    dist_in_loads = [ld for ld in extracted["beam"]["loads"] if ld["type"] == "distributed"]
    assert dist_in_loads
    assert "distributed_loads" in extracted["beam"]
    assert len(extracted["beam"]["distributed_loads"]) == len(dist_in_loads)


def test_deterministic_export(tmp_path: Path):
    a = generate_exercise(
        family="overhang_stepped_udl",
        seed=12345,
        out_dir=tmp_path / "a",
        stem="ex_0001",
    )
    b = generate_exercise(
        family="overhang_stepped_udl",
        seed=12345,
        out_dir=tmp_path / "b",
        stem="ex_0001",
    )
    ja = json.loads(a.json_path.read_text(encoding="utf-8"))
    jb = json.loads(b.json_path.read_text(encoding="utf-8"))
    assert ja == jb
    assert a.png_path.is_file() and a.png_path.stat().st_size > 0
    assert b.png_path.is_file() and b.png_path.stat().st_size > 0
    assert a.png_path.read_bytes() == b.png_path.read_bytes()


def test_batch_count(tmp_path: Path):
    arts = generate_batch(
        count=3,
        family="span_point_stepped_udl",
        seed=7,
        out_dir=tmp_path,
    )
    assert len(arts) == 3
    for i, art in enumerate(arts, start=1):
        assert art.json_path.name == f"ex_{i:04d}.json"
        assert art.png_path.is_file()


def test_validate_rejects_bad_udl():
    ex = build_family("overhang_stepped_udl", seed=1)
    # שבור end<=start
    from exercise_generator.schema import DistributedLoad

    ex.loads.append(DistributedLoad(x1=5.0, x2=3.0, w=1.0))
    errs = validate_exercise(ex)
    assert any("end<=start" in e for e in errs)


def test_list_families_complete():
    assert set(ALL_FAMILIES) == {
        "overhang_stepped_udl",
        "span_point_stepped_udl",
        "roller_pin_overhang",
        "double_overhang_mixed",
        "rich_combo",
    }


def test_default_generate_uses_locked_family(tmp_path: Path):
    from exercise_generator.templates.registry import LOCKED_FAMILY

    arts = generate_batch(count=5, seed=99, out_dir=tmp_path)
    assert all(a.exercise.family == LOCKED_FAMILY for a in arts)
    assert LOCKED_FAMILY == "overhang_stepped_udl"


def test_random_beam_length_rules():
    from exercise_generator.randomize import L_MAX, L_MIN, make_rng, random_beam_length

    rng = make_rng(0)
    samples = [random_beam_length(rng) for _ in range(500)]
    assert all(L_MIN - 1e-9 <= L <= L_MAX + 1e-9 for L in samples)

    integers = [L for L in samples if abs(L - round(L)) < 1e-9]
    decimals = [L for L in samples if abs(L - round(L)) >= 1e-9]
    # ~80/20 עם סטייה סבירה על 500 דגימות
    assert 0.70 <= len(integers) / len(samples) <= 0.90
    assert 0.10 <= len(decimals) / len(samples) <= 0.30
    for L in decimals:
        tenths = round(L * 10)
        assert abs(L * 10 - tenths) < 1e-9
        assert tenths % 10 != 0


def test_random_point_spacings_rules():
    from exercise_generator.randomize import (
        L_MAX,
        L_MIN,
        make_rng,
        random_point_spacings,
    )

    rng = make_rng(1)
    all_gaps: list[float] = []
    for _ in range(200):
        segs, L = random_point_spacings(rng, n_segments=4)
        assert len(segs) == 4
        assert abs(sum(segs) - L) < 1e-9
        assert L_MIN - 1e-9 <= L <= L_MAX + 1e-9
        all_gaps.extend(segs)

    integers = [g for g in all_gaps if abs(g - round(g)) < 1e-9]
    decimals = [g for g in all_gaps if abs(g - round(g)) >= 1e-9]
    assert 0.70 <= len(integers) / len(all_gaps) <= 0.90
    assert 0.10 <= len(decimals) / len(all_gaps) <= 0.30
    for g in decimals:
        tenths = round(g * 10)
        assert abs(g * 10 - tenths) < 1e-9
        assert tenths % 10 != 0


def test_locked_family_length_in_range():
    from exercise_generator.randomize import L_MAX, L_MIN

    for seed in range(30):
        ex = build_family("overhang_stepped_udl", seed=seed)
        assert L_MIN <= ex.L <= L_MAX
        require_valid(ex)
        # מרווחי שורת המידות העליונה מסתכמים ל־L
        span = sum(abs(s.x2 - s.x1) for s in ex.dim_row_top.segments)
        assert abs(span - ex.L) < 1e-6
